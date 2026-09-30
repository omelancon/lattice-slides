"""Turn the events of a specializer into animation frames (spec section 9).

A frame holds the reachable versions (with a display state and a highlight mark), the edges between
them, an automatic caption and a panel. Static text (contexts, code) lives once in ``tables``.
"""
from __future__ import annotations

from ..anim import Trace
from .ir import RESULT, Program
from .lv import LambdaVersioning
from .sbbv import Specializer, Version

EVENTS = ["start", "dequeue", "must-merge", "merge", "specialize", "instruction", "entry", "exit", "return-points",
          "generic-entries", "done"]
BLOCK_EVENTS = [e for e in EVENTS if e != "instruction"]

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
                 max_steps: int = 5000, granularity: str = "block"):
        super().__init__({})
        self.program = program
        self.algorithm = algorithm
        cls = LambdaVersioning if algorithm == "lv" else Specializer
        self.spec = cls(program, limit, heuristic, entry=entry, limits=limits, seed=seed, max_steps=max_steps,
                        emit=self._on_event)
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
                if not line.removed and line.text.startswith("if ") and "?(" in line.text:
                    n += 1
        return n

    # ------------------------------------------------------------ captions and meta
    def _v(self, vid: int) -> Version:
        return self.spec.by_id[vid]

    def _name(self, vid: int, ctx: bool = True) -> str:
        v = self._v(vid)
        return f"{v.label} ({v.context})" if ctx else v.label

    @staticmethod
    def _join(names: list[str]) -> str:
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + " and " + names[-1]

    def _caption(self, kind: str, info: dict, gone: list[str]) -> str:
        v = self._v
        text = ""
        if kind == "start":
            ids = info.get("versions", [])
            text = f"Queue the generic entr{'y' if len(ids) == 1 else 'ies'} {self._join([self._name(i) for i in ids])}."
        elif kind == "dequeue":
            text = f"Dequeue {self._name(info['version'])}."
        elif kind == "must-merge":
            b = self.program.block(info["block"])
            lim = info["limit"]
            text = (f"Block {b.name} has {len(info['versions'])} reachable versions "
                    f"({self._join([v(i).label for i in info['versions']])}); the limit is "
                    f"{'none' if lim == float('inf') else int(lim)}.")
        elif kind == "merge":
            into = info["into"]
            olds = [i for i in info["merged"] if i != into]
            if len(olds) == len(info["merged"]):
                text = f"Merge {self._join([v(i).label for i in olds])} into the new version {self._name(into)}."
            else:
                text = f"Merge {self._join([v(i).label for i in olds])} into {self._name(into)}, whose context is their union."
            if info.get("queued"):
                text += f" {v(into).label} is queued."
        elif kind == "specialize":
            vid = info["version"]
            text = f"Specialize {v(vid).label}"
            parts = []
            if info.get("removed"):
                parts.append(f"{info['removed']} test{'s' if info['removed'] > 1 else ''} removed")
            q = [v(i).label for i in info.get("queued", []) if self._visible(i)]
            if q:
                parts.append(f"queue {self._join(q)}")
            reused = [v(i).label for i in info.get("targets", []) if i not in info.get("queued", []) and self._visible(i)]
            if reused:
                parts.append(f"jump to existing {self._join(reused)}")
            text += ": " + "; ".join(parts) + "." if parts else "."
        elif kind == "instruction":
            text = f"{v(info['version']).label}, {info['text']}: {info['note']}."
        elif kind == "entry":
            cs, e = v(info["call_site"]), v(info["entry"])
            what = "creates" if info.get("created") else "uses"
            text = f"{cs.label} calls {e.function}: it {what} entry point {self._name(info['entry'])}."
        elif kind == "exit":
            x = v(info["version"])
            text = f"{x.label} is an exit site: {RESULT}: {x.context_after.get(RESULT)}."
        elif kind == "return-points":
            cs = v(info["call_site"])
            e = v(info["entry"])
            added = [f"{self._name(rp)} for exit {v(x).label}" for rp, x in info.get("added", [])]
            removed = [v(rp).label for rp, _ in info.get("removed", [])]
            parts = []
            if added:
                parts.append(f"return point{'s' if len(added) > 1 else ''} {self._join(added)} added")
            if removed:
                parts.append(f"return point{'s' if len(removed) > 1 else ''} {self._join(removed)} removed")
            text = f"Call site {cs.label} of entry {e.label}: " + "; ".join(parts) + "."
        elif kind == "generic-entries":
            created = [self._name(i) for i in info.get("created", []) if self._visible(i)]
            text = f"Queue the generic entr{'y' if len(created) == 1 else 'ies'} {self._join(created)}."
        elif kind == "done":
            spec = self.spec
            n = sum(1 for x in spec.final_versions() if self._visible(x.id))
            where = " in the functions drawn" if len(self.visible) < len(self.program.functions) else ""
            text = (f"Done: {n} versions, {spec.merges} merge{'s' if spec.merges != 1 else ''}, "
                    f"{self._tests(self.prev_nodes)} type tests left{where}.")
            if spec.truncated:
                text = "Stopped after the maximum number of steps. " + text
        gone_labels = [v(int(i)).label for i in gone]
        if gone_labels and kind in ("merge", "specialize", "return-points"):
            text += f" Unreachable: {self._join(gone_labels)}."
        return text

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

    def _program_table(self) -> dict:
        prog = self.program
        out = {"functions": []}
        for name in self.visible:
            fn = prog.function(name)
            blocks = []
            for b in fn.blocks.values():
                edges = []
                last = b.instrs[-1]
                for t in b.successors():
                    kind = "goto"
                    if last.__class__.__name__ == "If":
                        kind = "true" if t == last.then else "false"
                    elif last.__class__.__name__ == "Call":
                        kind = "return"
                    edges.append({"to": t, "kind": kind})
                blocks.append({"key": b.key, "name": b.name, "params": b.params,
                               "code": [{"text": i.text, "line": i.line} for i in b.instrs],
                               "edges": edges, "line": b.line})
            out["functions"].append({"name": name, "params": fn.params, "blocks": blocks})
        return out
