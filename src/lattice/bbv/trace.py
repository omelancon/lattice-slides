"""Turn the events of a specializer into animation frames (spec section 9).

A frame holds the reachable versions (with a display state and a highlight mark), the edges between
them, an automatic caption and a panel. Static text (contexts, code) lives once in ``tables``.
"""
from __future__ import annotations

from ..anim import Trace
from .ir import RESULT, Program
from .lv import LambdaVersioning
from .paths import OVERFLOW, PathError, PathWalker
from .rich import SEP, binding, code, context, join, op, tag, ty, var, ver
from .sbbv import Specializer, Version
from .types import Type

EVENTS = ["start", "dequeue", "must-merge", "merge", "specialize", "instruction", "entry", "exit", "return-points",
          "generic-entries", "done"]
BLOCK_EVENTS = [e for e in EVENTS if e != "instruction"]
# The operation badge of an instruction frame, by the kind of instruction specialized
INSTRUCTION_OPS = {"assign": "assign", "if": "test kept", "if-true": "test removed", "if-false": "test removed",
                   "goto": "goto", "call": "call", "return": "exit", "fail": "fail"}

# Lines of the bundled pseudo-code listings (``lattice:bbv/pseudocode/sbbv.txt`` and ``lv.txt``) executed
# at each event, so that a ``code`` block showing the listing can follow the animation.
ALGO_LINES = {
    "sbbv": {"start": [2], "dequeue": [3, 4], "must-merge": [5], "merge": list(range(53, 58)),
             "specialize": [6] + list(range(22, 32)), "done": [3],
             "instruction": {"goto": list(range(33, 37)), "if": list(range(48, 52)), "if-true": list(range(45, 48)),
                             "if-false": list(range(42, 45)), "other": [28, 29]}},
    "lv": {"start": [2, 3], "dequeue": [4, 5], "must-merge": [6], "merge": list(range(69, 77)),
           "specialize": [7] + list(range(9, 20)), "entry": list(range(33, 40)), "exit": list(range(28, 32)),
           "return-points": list(range(49, 58)), "return-points-removed": list(range(59, 68)),
           "generic-entries": [1, 2, 3], "done": [4],
           "instruction": {"goto": list(range(21, 27)), "if": [16, 17], "if-true": [16, 17], "if-false": [16, 17],
                           "call": list(range(33, 48)), "return": list(range(28, 32)), "other": [16, 17]}},
}


class VersioningTrace(Trace):
    """Frames of a basic block versioning run. ``frames[i]`` is a full state (see ``_frame``)."""

    def __init__(self, program: Program, *, algorithm: str = "sbbv", limit: int = 2, heuristic: str = "similarity",
                 entry: str | None = None, limits: dict | None = None, seed: int = 0, functions: list[str] | None = None,
                 events: list[str] | None = None, caption: str = "auto", until: int | None = None,
                 max_steps: int = 5000, granularity: str = "block", intervals: bool = False,
                 thresholds="machine", fixnum_bits: int = 61, vector_bounds: bool = True,
                 paths: list[dict] | None = None):
        super().__init__({})
        self.program = program
        self.algorithm = algorithm
        cls = LambdaVersioning if algorithm == "lv" else Specializer
        self.spec = cls(program, limit, heuristic, entry=entry, limits=limits, seed=seed, max_steps=max_steps,
                        emit=self._on_event, intervals=intervals, thresholds=thresholds, fixnum_bits=fixnum_bits,
                        vector_bounds=vector_bounds)
        self.visible = [f for f in program.functions if not program.functions[f].hidden] if functions is None else list(functions)
        for f in self.visible:
            program.function(f)
        if events is not None:
            self.events = set(events)
        else:
            self.events = set(EVENTS) if granularity == "instruction" else set(BLOCK_EVENTS)
        if granularity == "instruction" and events is None:
            self.events.discard("specialize")  # the instruction frames show the specialization
        self.caption_mode = caption
        self.until = until
        self.prev_nodes: dict[int, dict] = {}
        self.prev_pos: dict[int, list] = {}
        self.pending_active: int | None = None
        self.stopped = False
        self.spec.run()
        if not self.frames:  # every event filtered out: keep the final state
            self._push("done", {})
        if paths:
            self._add_paths(paths)
        self.finalize()

    # ------------------------------------------------------------ events
    def _on_event(self, kind: str, **info) -> None:
        if self.stopped:
            return
        if kind not in self.events and kind not in ("done",):
            if kind == "dequeue":
                self.pending_active = info["version"]
            return
        if not self._concerns_visible(kind, info):
            return
        self._push(kind, info)
        if self.until is not None and len(self.frames) >= self.until:
            self.stopped = True

    def _visible(self, vid: int) -> bool:
        return self.spec.by_id[vid].function in self.visible

    def _concerns_visible(self, kind: str, info: dict) -> bool:
        if kind in ("start", "done", "generic-entries"):
            return kind != "generic-entries" or any(self._visible(i) for i in info.get("created", []))
        ids = []
        for key in ("version", "versions", "merged", "into", "call_site", "entry", "queued"):
            val = info.get(key)
            if isinstance(val, int):
                ids.append(val)
            elif isinstance(val, list):
                ids.extend(i for i in val if isinstance(i, int))
        if kind == "return-points":
            ids = [info["call_site"]]
        if kind == "entry":
            ids = [info["entry"]]
        return any(self._visible(i) for i in ids)

    # ------------------------------------------------------------ frames
    def _push(self, kind: str, info: dict) -> None:
        spec = self.spec
        reach = spec.reachable()
        nodes: dict[str, dict] = {}
        for vid in sorted(reach):
            v = spec.by_id[vid]
            if v.merged is not None or not self._visible(vid):
                continue
            n = {"state": "done" if v.done else "queued"}
            if v.is_entry:
                n["entry"] = True
            if v.is_exit:
                n["exit"] = True
            nodes[str(vid)] = n
        edges: dict[str, dict] = {}
        for vid in nodes:
            for e in spec.by_id[int(vid)].edges:
                if str(e.dst) not in nodes:
                    continue
                key = f"{e.src}->{e.dst}:{e.kind}"
                d = edges.setdefault(key, {"kind": e.kind})
                if e.exit is not None:
                    d.setdefault("exits", []).append(e.exit)
        if kind == "instruction" and str(info["version"]) in nodes:
            nodes[str(info["version"])].update(state="done", shown=info["shown"])
        marks = self._marks(kind, info, nodes, edges)
        for vid, m in marks.items():
            if vid in nodes:
                nodes[vid]["mark"] = m
        # versions that left the graph this frame stay one frame, faded, at their old place
        gone = [vid for vid in self.prev_nodes if vid not in nodes]
        for vid in gone:
            nodes[vid] = {**self.prev_nodes[vid], "mark": "gone"}
        for vid, n in nodes.items():
            if vid not in self.prev_nodes and vid not in gone and n.get("mark") is None:
                n["mark"] = "back" if spec.by_id[int(vid)].id <= self._max_prev_id else "new"
        frame = {"nodes": nodes, "edges": edges, "panel": self._panel(nodes),
                 "caption": self._caption(kind, info, gone) if self.caption_mode == "auto" else ""}
        meta = self._meta(kind, info)
        self.frames.append(frame)
        self.meta.append(meta)
        self.prev_nodes = {k: v for k, v in nodes.items() if v.get("mark") != "gone"}
        self._max_prev_id = max([int(k) for k in self.prev_nodes] + [self._max_prev_id])
        self.pending_active = None

    _max_prev_id = 0

    def _marks(self, kind: str, info: dict, nodes: dict, edges: dict) -> dict[str, str]:
        m: dict[str, str] = {}
        s = str
        if kind == "start":
            for i in info.get("versions", []):
                m[s(i)] = "new"
        elif kind == "dequeue":
            m[s(info["version"])] = "active"
        elif kind == "must-merge":
            for i in info["versions"]:
                m[s(i)] = "merge"
        elif kind == "merge":
            for i in info["merged"]:
                m[s(i)] = "merge"
            m[s(info["into"])] = "merged"
            for key, old in info.get("edges", []):
                src, rest = key.split("->", 1)
                dst, kind_, *_ = rest.split(":")
                k = f"{src}->{dst}:{kind_}"
                if k in edges:
                    edges[k]["state"] = "new"
        elif kind == "instruction":
            m[s(info["version"])] = "active"
            for key in list(edges):
                if key.startswith(f"{info['version']}->"):
                    edges[key]["state"] = "new"
        elif kind == "specialize":
            m[s(info["version"])] = "active"
            for i in info.get("queued", []):
                m[s(i)] = "new"
            for e in edges.values():
                pass
            for key in list(edges):
                if key.startswith(f"{info['version']}->"):
                    edges[key]["state"] = "new"
        elif kind == "entry":
            m[s(info["call_site"])] = "active"
            m[s(info["entry"])] = "new" if info.get("created") else "active"
            k = f"{info['call_site']}->{info['entry']}:call"
            if k in edges:
                edges[k]["state"] = "new"
        elif kind == "exit":
            m[s(info["version"])] = "active"
        elif kind == "return-points":
            m[s(info["call_site"])] = "active"
            for rp, _exit in info.get("added", []):
                m.setdefault(s(rp), "new")
                k = f"{info['call_site']}->{rp}:return"
                if k in edges:
                    edges[k]["state"] = "new"
        elif kind == "generic-entries":
            for i in info.get("created", []):
                m[s(i)] = "new"
        if self.pending_active is not None and kind not in ("dequeue",):
            m.setdefault(s(self.pending_active), "active")
        return m

    def _panel(self, nodes: dict) -> dict:
        spec = self.spec
        queue = [q.label for q in spec.queue if self._visible(q.id) and q.merged is None and not q.done]
        counts: dict[str, int] = {}
        for vid, n in nodes.items():
            if n.get("mark") == "gone":
                continue
            v = spec.by_id[int(vid)]
            name = v.block.name if len(self.visible) == 1 else f"{v.function}/{v.block.name}"
            counts[name] = counts.get(name, 0) + 1
        return {"queue": queue, "versions": counts, "checks": self._tests(nodes), "merges": spec.merges,
                "limit": spec.limit}

    def _tests(self, nodes: dict) -> int:
        n = 0
        for vid, node in nodes.items():
            if node.get("mark") == "gone":
                continue
            v = self.spec.by_id[int(vid)]
            for line in v.body or []:
                if not line.removed and line.text.startswith("if "):
                    n += 1
        return n

    # ------------------------------------------------------------ captions and meta
    def _v(self, vid: int) -> Version:
        return self.spec.by_id[vid]

    def _chip(self, vid: int) -> str:
        v = self._v(vid)
        return ver(v.label, v.block.key)

    def _chips(self, ids) -> str:
        return " ".join(self._chip(i) for i in ids)

    def _named(self, vid: int) -> str:
        """The version's chip followed by its context."""
        v = self._v(vid)
        return f"{self._chip(vid)} {context(v.context)}" if v.context.lines() else self._chip(vid)

    def _caption(self, kind: str, info: dict, gone: list[str]) -> str:
        """One line per frame: the operation first (a badge), then the versions concerned (chips),
        then the details (contexts, tests, queue effects) separated by dots. Spec 9.5."""
        v = self._v
        parts: list[str] = []
        if kind == "start":
            ids = info.get("versions", [])
            parts = [f"{op('queue')} {tag('generic entry' if len(ids) == 1 else 'generic entries')}"] + [self._named(i) for i in ids]
        elif kind == "dequeue":
            parts = [f"{op('dequeue')} {self._named(info['version'])}"]
        elif kind == "must-merge":
            b = self.program.block(info["block"])
            lim = info["limit"]
            parts = [f"{op('limit')} {ver(b.name, b.key)} has {len(info['versions'])} reachable versions "
                     f"{self._chips(info['versions'])}", f"limit {'none' if lim == float('inf') else int(lim)}"]
        elif kind == "merge":
            into = info["into"]
            olds = [i for i in info["merged"] if i != into]
            parts = [f"{op('merge')} {self._chips(olds)} → {self._chip(into)}"]
            parts.append("new version, the union of their contexts" if len(olds) == len(info["merged"]) else "its context is their union")
            widened = info.get("widened") or []
            if widened:
                parts.append(f"{tag('widened')} {', '.join(var(w) for w in widened)}")
            parts.append(context(v(into).context))
            if info.get("queued"):
                parts.append(tag("queued"))
        elif kind == "specialize":
            vid = info["version"]
            parts = [f"{op('specialize')} {self._chip(vid)}"]
            if info.get("removed"):
                parts.append(f"{info['removed']} test{'s' if info['removed'] > 1 else ''} {tag('removed')}")
            q = [i for i in info.get("queued", []) if self._visible(i)]
            if q:
                parts.append(f"{tag('queue')} {self._chips(q)}")
            reused = [i for i in info.get("targets", []) if i not in info.get("queued", []) and self._visible(i)]
            if reused:
                parts.append(f"{tag('jump to')} {self._chips(reused)}")
        elif kind == "instruction":
            what = info["what"]
            parts = [f"{op(INSTRUCTION_OPS.get(what, 'instruction'))} {self._chip(info['version'])}"]
            if what not in ("if-true", "if-false"):  # those notes quote the test themselves, struck through
                parts.append(code(info["text"]))
            parts.append(info["note"])
        elif kind == "entry":
            cs, e = info["call_site"], v(info["entry"])
            parts = [f"{op('entry')} {self._chip(cs)} calls {e.function}",
                     f"{'creates' if info.get('created') else 'uses'} entry point {self._named(info['entry'])}"]
        elif kind == "exit":
            x = v(info["version"])
            parts = [f"{op('exit')} {self._chip(info['version'])}", binding(RESULT, x.context_after.get(RESULT))]
        elif kind == "return-points":
            parts = [f"{op('return points')} call site {self._chip(info['call_site'])} of entry {self._chip(info['entry'])}"]
            for rp, x in info.get("added", []):
                parts.append(f"{tag('added')} {self._named(rp)} for exit {self._chip(x)}")
            removed_ = [rp for rp, _ in info.get("removed", [])]
            if removed_:
                parts.append(f"{tag('removed')} {self._chips(removed_)}")
        elif kind == "generic-entries":
            created = [i for i in info.get("created", []) if self._visible(i)]
            parts = [f"{op('queue')} {tag('generic entry' if len(created) == 1 else 'generic entries')}"] + [self._named(i) for i in created]
        elif kind == "done":
            spec = self.spec
            n = sum(1 for x in spec.final_versions() if self._visible(x.id))
            where = " in the functions drawn" if len(self.visible) < len(self.program.functions) else ""
            parts = [f"{op('done')} {n} version{'s' if n != 1 else ''}", f"{spec.merges} merge{'s' if spec.merges != 1 else ''}",
                     f"{self._tests(self.prev_nodes)} test{'s' if self._tests(self.prev_nodes) != 1 else ''} left{where}"]
            if spec.truncated:
                parts.insert(0, f"{tag('stopped')} after the maximum number of steps")
        if gone and kind in ("merge", "specialize", "return-points"):
            parts.append(f"{tag('unreachable')} {self._chips(int(i) for i in gone)}")
        return join(parts)

    def _meta(self, kind: str, info: dict) -> dict:
        meta: dict = {"event": kind}
        vid = info.get("version") or info.get("into") or info.get("call_site")
        if vid is None and info.get("versions"):
            vid = next((i for i in info["versions"] if self._visible(i)), None)
        if kind == "must-merge":
            meta["block"] = info["block"]
        if vid is not None:
            v = self._v(vid)
            meta["block"] = v.block.key
            meta["function"] = v.function
            lines = [i.line for i in v.block.instrs]
            meta["lines"] = list(range(min(lines), max(lines) + 1)) if lines else []
            meta["line"] = v.block.line
        if kind == "instruction":
            meta["lines"] = [info["line"]]
            meta["line"] = info["line"]
        algo = ALGO_LINES[self.algorithm if self.algorithm == "lv" else "sbbv"]
        if kind == "instruction":
            meta["algo"] = algo["instruction"].get(info["what"], algo["instruction"]["other"])
        elif kind == "return-points" and not info.get("added"):
            meta["algo"] = algo.get("return-points-removed", [])
        else:
            meta["algo"] = algo.get(kind, [])
        return meta

    # ------------------------------------------------------------ paths (spec 9.5)
    PATH_KEYS = {"input", "reads", "reads_exhausted", "overflow", "versions", "caption", "dim"}
    WALK_KEYS = {"input", "reads", "reads_exhausted", "overflow"}

    def _add_paths(self, paths: list[dict]) -> None:
        """One ``path`` frame per entry of ``paths``, after the last frame: the versions a walk from the
        entry goes through (``input``, ``reads``) or the versions listed (``versions``), on the graph
        of the last frame."""
        if self.stopped:
            raise ValueError("paths: the frames stop early (until), so they would not end on the final graph; "
                             "remove until to use paths")
        if not isinstance(paths, list):
            raise ValueError("paths: a list of paths, each a mapping with input, reads or versions")
        last = self.frames[-1]
        drawn = {vid: n for vid, n in last["nodes"].items() if n.get("mark") != "gone"}
        for i, entry in enumerate(paths):
            where = f"paths[{i}]"
            if not isinstance(entry, dict):
                raise ValueError(f"{where}: a path is a mapping with input, reads or versions")
            unknown = set(entry) - self.PATH_KEYS
            if unknown:
                raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}; use input, reads, reads_exhausted, "
                                 f"overflow, versions, caption, dim")
            walked = sorted(set(entry) & self.WALK_KEYS)
            if "versions" in entry and walked:
                raise ValueError(f"{where}: versions lists the path by hand; it does not combine with {', '.join(walked)}")
            if "versions" not in entry and "input" not in entry and "reads" not in entry:
                raise ValueError(f"{where}: give versions (labels), or input (parameter types) and/or reads "
                                 f"(the types returned by read())")
            if "versions" in entry:
                order, edges, lit, chain, what = self._path_by_versions(entry["versions"], drawn, last, where)
            else:
                order, edges, lit, chain, what = self._path_by_walk(entry, drawn, where)
            self._push_path(order, edges, lit, chain, what, drawn, last, entry, where)

    def _types(self, given, what: str, where: str) -> list[Type]:
        if not isinstance(given, list) or not given:
            raise ValueError(f"{where}: {what} lists types, such as [fx, fl]")
        out = []
        for text in given:
            try:
                t = Type.parse(str(text))
            except (ValueError, KeyError) as e:
                raise ValueError(f"{where}: {what}: cannot read the type {text!r} ({e})") from None
            out.append(t if self.spec.intervals else t.without_range())
        return out

    def _path_by_walk(self, entry: dict, drawn: dict, where: str):
        fn = self.spec.entry_function
        given = entry.get("input", {})
        if given is None:
            given = {}
        if not isinstance(given, dict):
            raise ValueError(f"{where}: input maps parameters of {fn.name} to types, such as {{x: fl}}")
        types: dict[str, Type] = {}
        for name, text in given.items():
            name = str(name)
            if name not in fn.params:
                raise ValueError(f"{where}: input: {name!r} is not a parameter of {fn.name} "
                                 f"(its parameters: {', '.join(fn.params) or 'none'})")
            try:
                t = Type.parse(str(text))
            except (ValueError, KeyError) as e:
                raise ValueError(f"{where}: input: {name}: cannot read the type {text!r} ({e})") from None
            types[name] = t if self.spec.intervals else t.without_range()
        reads = self._types(entry["reads"], "reads", where) if entry.get("reads", []) != [] else []
        ex = entry.get("reads_exhausted", "any")
        if ex == "error":
            exhausted = None
        else:
            exhausted = self._types(ex if isinstance(ex, list) else [ex], "reads_exhausted", where)
        overflow = str(entry.get("overflow", "maybe"))
        if overflow not in OVERFLOW:
            raise ValueError(f"{where}: overflow is maybe, never or always")
        walker = PathWalker(self.spec, inputs=types, reads=reads, exhausted=exhausted, overflow=overflow)
        try:
            w = walker.walk()
        except PathError as e:
            raise ValueError(f"{where}: {e}") from None
        order = [str(v) for v in w.order if str(v) in drawn]
        edges = {f"{s}->{d}:{k}" for s, d, k in w.edges}
        lit = {f"{s}->{d}:return": xs for (s, d), xs in w.exits.items()}
        on = set(order)
        moves = [(str(a), str(b)) for a, b in w.transitions if str(a) in on and str(b) in on and a != b]
        chain = all(sum(1 for a, _ in moves if a == v) <= 1 and sum(1 for _, b in moves if b == v) <= 1 for v in order)
        what = [binding(n, t) for n, t in types.items()]
        if reads:
            what.append(f"{code('(read)')} → {', '.join(ty(str(t)) for t in reads)}")
        if overflow != "maybe":
            what.append(f"{tag('overflow')} {overflow}")
        return order, edges, lit, chain, " ".join(what) or "the program"

    def _path_by_versions(self, labels, drawn: dict, last: dict, where: str):
        if not isinstance(labels, list) or not labels:
            raise ValueError(f"{where}: versions lists version labels, such as [A1, D1]")
        by_label: dict[str, list[str]] = {}
        for vid in drawn:
            v = self.spec.by_id[int(vid)]
            by_label.setdefault(v.label, []).append(vid)
            by_label.setdefault(f"{v.function}/{v.label}", []).append(vid)
        order = []
        for label in labels:
            label = str(label)
            if label not in by_label:
                plain_labels = sorted({self.spec.by_id[int(v)].label for v in drawn})
                raise ValueError(f"{where}: versions: {label!r} is not drawn at the end of the run "
                                 f"(drawn: {', '.join(plain_labels)})")
            vids = by_label[label]
            if len(vids) > 1:
                names = " or ".join(f"{self.spec.by_id[int(v)].function}/{label}" for v in vids)
                raise ValueError(f"{where}: versions: several drawn functions have a version {label!r}: write {names}")
            if vids[0] not in order:
                order.append(vids[0])
        on = set(order)
        edges, lit = set(), {}
        for key, e in last["edges"].items():
            src, rest = key.split("->", 1)
            dst = rest.split(":", 1)[0]
            if src in on and dst in on:
                edges.add(key)
                if e.get("exits"):
                    lit[key] = {x for x in e["exits"] if str(x) in on}
        moves = []  # as in a walk, a return edge reads as a move from its listed exits to the return point
        for key in edges:
            src, rest = key.split("->", 1)
            dst = rest.split(":", 1)[0]
            moves.extend((str(x), dst) for x in lit.get(key) or [src])
        chain = all(sum(1 for a, _ in moves if a == v) <= 1 and sum(1 for _, b in moves if b == v) <= 1 for v in order)
        return order, edges, lit, chain, "chosen versions"

    def _push_path(self, order: list[str], on_edges: set, lit: dict, chain: bool, what: str, drawn: dict, last: dict,
                   entry: dict, where: str) -> None:
        dim = entry.get("dim", True)
        if not isinstance(dim, bool):
            raise ValueError(f"{where}: dim is true or false")
        on = set(order)
        nodes = {}
        for vid, n in drawn.items():
            n = {k: v for k, v in n.items() if k != "mark"}
            if vid in on:
                n["mark"] = "path"
            elif dim:
                n["mark"] = "dim"
            nodes[vid] = n
        edges = {}
        for key, e in last["edges"].items():
            src, rest = key.split("->", 1)
            dst = rest.split(":", 1)[0]
            if src not in nodes or dst not in nodes:
                continue
            e = {k: v for k, v in e.items() if k != "state"}
            if key in on_edges:
                e["state"] = "path"
                if lit.get(key):
                    e["lit_exits"] = sorted(lit[key])
            elif dim:
                e["state"] = "dim"
            edges[key] = e
        tests = self._tests({vid: nodes[vid] for vid in order})
        if "caption" in entry:
            caption = str(entry["caption"] or "")
        elif self.caption_mode == "auto":
            caption = join([f"{op('path')} {what}", (" → " if chain else " ").join(self._chip(int(v)) for v in order),
                            f"{tests} test{'s' if tests != 1 else ''}"])
        else:
            caption = ""
        self.frames.append({"nodes": nodes, "edges": edges, "panel": dict(last["panel"]), "caption": caption})
        blocks = []
        for vid in order:
            key = self.spec.by_id[int(vid)].block.key
            if key not in blocks:
                blocks.append(key)
        self.meta.append({"event": "path", "blocks": blocks, "function": self.spec.entry_function.name, "algo": []})

    # ------------------------------------------------------------ static tables
    def finalize(self) -> None:
        """Resolve the labels that are only known at the end (callee entries, return indices)."""
        spec = self.spec
        self.tables = {"program": self._program_table(), "versions": {}}
        for vid, v in spec.by_id.items():
            if not self._visible(vid):
                continue
            code = []
            for line in (v.body or []):
                d = line.as_dict()
                if line.callee is not None:
                    cs = spec.by_id[line.callee]
                    label = spec.resolve(spec.by_id[cs.call.entry]).label if cs.call else "?"
                    d["text"] = line.text.replace("{callee}", label)
                if line.exit is not None and isinstance(spec, LambdaVersioning) and line.exit in spec.return_index:
                    d["text"] = d["text"].replace("return ", f"return [{spec.return_index[line.exit]}] ", 1)
                code.append(d)
            self.tables["versions"][str(vid)] = {
                "label": v.label, "block": v.block.key, "function": v.function, "name": v.block.name,
                "context": v.context.lines(), "code": code,
                "after": v.context_after.lines() if v.context_after is not None else [],
            }
        index = getattr(spec, "return_index", {})
        for f in self.frames:
            for e in f["edges"].values():
                if "exits" in e:
                    labels = sorted({index.get(x, 0) for x in e.pop("exits")}) if index else []
                    if labels:
                        e["label"] = " ".join(f"[{i}]" for i in labels)
                if "lit_exits" in e:  # the indices a path returned through (spec 9.5)
                    lit = sorted({index.get(x, 0) for x in e.pop("lit_exits")}) if index else []
                    if lit:
                        e["lit"] = lit

    def _program_table(self) -> dict:
        prog = self.program
        out = {"functions": []}
        for name in self.visible:
            fn = prog.function(name)
            blocks = []
            for b in fn.blocks.values():
                edges = [{"to": t, "kind": kind} for t, kind in b.edges()]
                blocks.append({"key": b.key, "name": b.name, "params": b.params,
                               "code": [{"text": i.text, "line": i.line} for i in b.instrs],
                               "edges": edges, "line": b.line})
            out["functions"].append({"name": name, "params": fn.params, "blocks": blocks})
        return out


# ====================================================================== abstract interpretation

ABSINT_ALGO = {"start": [2, 3, 4], "dequeue": [5, 6], "done": [5],
               "instruction": {"assign": [18], "if": [19], "goto": [20], "call": [21], "return": [22], "fail": [22]},
               "propagate": {"dead": [9, 10], "unchanged": [11, 12], "first": [11, 12, 13, 14],
                             "union": [11, 12, 13, 14], "widened": [11, 12, 13, 14]}}
ABSINT_EVENTS = ["start", "dequeue", "instruction", "propagate", "done"]
ABSINT_OPS = {"assign": "assign", "if": "test", "goto": "goto", "call": "call", "return": "exit", "fail": "fail"}


def context_lines(ctx) -> list[str]:
    """Context lines for display: any integer (``fx | bg``) with no known interval shows ``(-∞, ∞)``, as
    in the figures (``absint.value_text``)."""
    from .absint import value_text

    out = []
    for line in ctx.lines():
        name, _, _text = line.partition(": ")
        out.append(f"{name}: {value_text(ctx.get(name.split('/')[0]))}")
    return out


class AbstractTrace(Trace):
    """Frames of an abstract interpretation run (thesis 1.1): the CFG stays, its annotations change."""

    def __init__(self, program: Program, *, function: str | None = None, thresholds="machine", narrowing: bool = True,
                 fixnum_bits: int = 61, events: list[str] | None = None, granularity: str = "block",
                 history: list[str] | None = None, caption: str = "auto", until: int | None = None,
                 max_steps: int = 2000, vector_bounds: bool = True):
        from .absint import AbstractInterpreter

        super().__init__({})
        self.program = program
        self.ai = AbstractInterpreter(program, function, thresholds=thresholds, narrowing=narrowing,
                                      fixnum_bits=fixnum_bits, max_steps=max_steps, emit=self._on_event,
                                      vector_bounds=vector_bounds)
        self.fn = self.ai.function
        self.visible = [self.fn.name]
        self.ids = {b.name: str(i + 1) for i, b in enumerate(self.fn.blocks.values())}
        if events is not None:
            self.events = set(events)
        else:
            self.events = set(ABSINT_EVENTS) if granularity == "instruction" else set(ABSINT_EVENTS) - {"instruction"}
        self.tracked = list(history or [])
        for key in self.tracked:
            block, _, var = key.partition(".")
            if block not in self.fn.blocks:
                raise ValueError(f"history: unknown block {block!r}")
        self.caption_mode = caption
        self.until = until
        self.stopped = False
        self.max_lines: dict[str, list[list[str]]] = {}
        self.ai.run()
        if not self.frames:
            self._push("done", {})
        self.finalize()

    # ------------------------------------------------------------ events
    def _on_event(self, kind: str, **info) -> None:
        if self.stopped or (kind not in self.events and kind != "done"):
            return
        self._push(kind, info)
        if self.until is not None and len(self.frames) >= self.until:
            self.stopped = True

    def _push(self, kind: str, info: dict) -> None:
        ai = self.ai
        nodes: dict[str, dict] = {}
        for name, block in self.fn.blocks.items():
            vid = self.ids[name]
            ctx = ai.contexts[name]
            if kind == "instruction" and info.get("block") == name:
                lines = context_lines(info["context"])
            else:
                lines = context_lines(ctx) if ctx is not None else ["⊥"]
            after = context_lines(ai.after[name]) if ai.after[name] is not None else []
            n = {"state": "done" if ctx is not None else "dead", "lines": lines, "after": after}
            if block is self.fn.entry:
                n["entry"] = True
            nodes[vid] = n
            best = self.max_lines.setdefault(vid, [])  # per slot, the longest name and the longest type seen
            for i, text in enumerate(lines):
                name, _, typ = text.partition(": ")
                if i >= len(best):
                    best.append([name, typ])
                else:
                    if len(name) > len(best[i][0]):
                        best[i][0] = name
                    if len(typ) > len(best[i][1]):
                        best[i][1] = typ
        edges: dict[str, dict] = {}
        for name, block in self.fn.blocks.items():
            for t, ek in block.edges():
                key = f"{self.ids[name]}->{self.ids[t]}:{ek}"
                e = {"kind": ek}
                if (name, t, ek) in ai.dead:
                    e["state"] = "gone"
                edges[key] = e
        # marks
        if kind == "start":
            nodes[self.ids[info["block"]]]["mark"] = "new"
        elif kind in ("dequeue", "instruction"):
            nodes[self.ids[info["block"]]]["mark"] = "active"
        elif kind == "propagate":
            nodes[self.ids[info["src"]]]["mark"] = "active"
            dst = self.ids[info["dst"]]
            res = info["result"]
            key = f"{self.ids[info['src']]}->{dst}:{info['edge']}"
            if res == "dead":
                edges[key]["state"] = "gone"
            else:
                edges[key]["state"] = "new" if res != "unchanged" else "active"
            if res == "first":
                nodes[dst]["mark"] = "new"
            elif res == "union":
                nodes[dst]["mark"] = "changed"
            elif res == "widened":
                nodes[dst]["mark"] = "widened"
        frame = {"nodes": nodes, "edges": edges, "panel": self._panel(),
                 "caption": self._caption(kind, info) if self.caption_mode == "auto" else ""}
        self.frames.append(frame)
        self.meta.append(self._meta(kind, info))

    def _panel(self) -> dict:
        ai = self.ai
        panel = {"worklist": list(ai.worklist), "iterations": ai.steps}
        for key in self.tracked:
            chain = []
            for mark, text in ai.history.get(key, []):
                chain.append(f"{mark} {text}".strip())
            panel[key] = chain
        return panel

    def _chip(self, name: str) -> str:
        return ver(name, self.fn.blocks[name].key)

    def _caption(self, kind: str, info: dict) -> str:
        """Same shape as the versioning captions: operation badge, block chips, then details."""
        ai = self.ai
        if kind == "start":
            return join([f"{op('start')} {self._chip(info['block'])}", context(context_lines(ai.contexts[info["block"]]))])
        if kind == "dequeue":
            return join([f"{op('interpret')} {self._chip(info['block'])}", context(context_lines(ai.contexts[info["block"]]))])
        if kind == "instruction":
            return join([f"{op(ABSINT_OPS.get(info['what'], 'instruction'))} {self._chip(info['block'])}", code(info["text"]),
                         info["note"]])
        if kind == "propagate":
            src, dst, res = info["src"], info["dst"], info["result"]
            if res == "dead":
                return join([f"{op('dead edge')} {self._chip(src)} → {self._chip(dst)}", f"{code(info['what'])} cannot hold here"])
            if res == "first":
                return join([f"{op('reached')} {self._chip(dst)}", context(context_lines(ai.contexts[dst])), tag("queued")])
            if res == "unchanged":
                return join([f"{op('unchanged')} {self._chip(dst)}", f"already covers what {self._chip(src)} sends"])
            parts = [f"{op('widen' if res == 'widened' else 'union')} {self._chip(dst)}"]
            for v, old, out, joined, widened in info["changes"][:3]:
                parts.append(f"{var(v)}: {ty(old)} ∪ {ty(out)} {'∇' if widened else '='} {ty(joined)}")
            more = len(info["changes"]) - 3
            if more > 0:
                parts.append(f"and {more} other{'s' if more > 1 else ''}")
            if info.get("queued"):
                parts.append(tag("requeued"))
            return join(parts)
        if kind == "done":
            parts = [f"{op('fixed point')} after {ai.steps} iteration{'s' if ai.steps != 1 else ''}"]
            if ai.truncated:
                parts.insert(0, f"{tag('stopped')} after the maximum number of steps without converging")
            return join(parts)
        return ""

    def _meta(self, kind: str, info: dict) -> dict:
        meta: dict = {"event": kind, "function": self.fn.name}
        name = info.get("block") or info.get("dst")
        if name:
            b = self.fn.blocks[name]
            meta["block"] = b.key
            lines = [i.line for i in b.instrs]
            meta["lines"] = list(range(min(lines), max(lines) + 1)) if lines else []
            meta["line"] = b.line
        if kind == "instruction":
            meta["lines"], meta["line"] = [info["line"]], info["line"]
            meta["algo"] = ABSINT_ALGO["instruction"].get(info["what"], [])
        elif kind == "propagate":
            meta["algo"] = ABSINT_ALGO["propagate"].get(info["result"], [])
        else:
            meta["algo"] = ABSINT_ALGO.get(kind, [])
        return meta

    # ------------------------------------------------------------ tables
    def finalize(self) -> None:
        self.tables = {"program": VersioningTrace._program_table(self), "versions": {}}
        for name, b in self.fn.blocks.items():
            vid = self.ids[name]
            self.tables["versions"][vid] = {
                "label": b.name, "block": b.key, "function": self.fn.name, "name": b.name,
                "context": [f"{n}: {t}" if t else n for n, t in self.max_lines.get(vid, [])],  # widest per slot, for sizing
                "code": [{"text": i.text, "line": i.line} for i in b.instrs], "after": [],
            }
