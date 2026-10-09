"""A merge heuristic at work (spec 9.5, "Merge heuristics"): a set of contexts of one block merged two by
two until the version limit holds, as ``mergeSome`` of SBBV merges them.

The merges are those of :meth:`sbbv.Specializer.merge_some` itself: one version per context, every one a
root, then ``merge_some`` on the block, its ``must-merge`` and ``merge`` events recorded. The frames show
each merge in two steps (the pair the heuristic picks, then the merge), on a complete graph whose edges
carry the heuristic's distance between the contexts they join. Code, when a block of a program is
given, is the block specialized in each context by a separate specializer: it is for the looks only and
never reaches the merges.
"""
from __future__ import annotations

import math
import re

from .heuristics import DISTANCES
from .intervals import using_fixnum_bits, using_vector_bounds
from .ir import Block, Program, ProgramError, parse
from .layout import node_size
from .rich import context as rich_context
from .rich import join, op, tag, var, ver
from .sbbv import Specializer, Version
from .types import Context, Type

PLACEMENTS = ("circle", "distance")
NODE_GAP = 28.0  # least room between two nodes
MARGIN = 16.0  # around the drawing
CIRCLE_ASPECTS = [1.0 + 0.125 * i for i in range(25)]  # ellipse widths (in heights) tried by `circle`
SMACOF_ITERATIONS = 300
SEPARATION = (1.0, 3.0)  # the target distance of the nearest and farthest pairs, in node units (`distance`)
# (scale, horizontal stretch) tried by `distance`, the least distorted first
DISTANCE_FITS = [(1.0, 1.0), (0.8, 1.0), (1.0, 1.25), (0.8, 1.25), (0.65, 1.0), (1.0, 1.5), (0.8, 1.5), (0.65, 1.25),
                 (0.65, 1.5)]
ALGO = {"start": [5], "pick": [53, 54], "merge": [55, 56, 57], "settle": [5], "done": []}  # lines of sbbv.txt

_VAR = re.compile(r"[^\s(),=/:`]+")
_NAME = re.compile(r"[A-Za-z_$][\w$.'-]*")
_ITEM_KEYS = {"context", "label", "code"}


class MergeError(ValueError):
    pass


# ------------------------------------------------------------------ contexts

def _type(text, where: str, intervals: bool) -> Type:
    if isinstance(text, bool) or text is None:
        raise MergeError(f"{where}: {text!r} is not a type (quote types such as \"#t\" in YAML)")
    try:
        t = Type.parse(str(text))
    except (ValueError, KeyError) as e:
        raise MergeError(f"{where}: cannot read the type {text!r} ({e})") from None
    return t.refined() if intervals else t.without_range()


def _bindings(item, where: str) -> list[tuple[str, object]]:
    """``{x: fx, y: fl}`` or ``"x: fx, y: fl"`` as (name, type text) pairs, in order."""
    if isinstance(item, dict):
        return [(str(k), v) for k, v in item.items()]
    if isinstance(item, str):
        out = []
        for part in re.split(r",\s*(?=[^\s,:\[\](){}]+\s*:)", item.strip()):
            name, sep, text = part.partition(":")
            if not sep:
                raise MergeError(f"{where}: expected name: type, got {part!r}")
            out.append((name.strip(), text.strip()))
        return out
    raise MergeError(f"{where}: a context is a mapping such as {{x: fx, y: fl}}")


def parse_context(item, where: str, intervals: bool = False) -> Context:
    """A context of the ``contexts`` list: names (``a/b`` for a class) to types."""
    types: dict[str, Type] = {}
    rep: dict[str, str] = {}
    for key, text in _bindings(item, where):
        names = [n.strip() for n in key.split("/")]
        for n in names:
            if not _VAR.fullmatch(n):
                raise MergeError(f"{where}: {n!r} is not a variable name")
            if n in types:
                raise MergeError(f"{where}: {n} is bound twice")
        t = _type(text, f"{where}: {key}", intervals)
        for n in names:
            types[n] = t
            rep[n] = names[0]
    if not types:
        raise MergeError(f"{where}: an empty context")
    return Context(types, rep)


def _items(contexts, intervals: bool) -> list[tuple[Context, str | None, list[str] | None]]:
    if not isinstance(contexts, list) or len(contexts) < 2:
        raise MergeError("contexts: a list of at least two contexts, such as [{x: fx}, {x: fl}]")
    out = []
    for i, item in enumerate(contexts):
        where = f"contexts[{i}]"
        label = code = None
        if isinstance(item, dict) and "context" in item and set(item) <= _ITEM_KEYS:
            label, code = item.get("label"), item.get("code")
            if label is not None and not _NAME.fullmatch(str(label)):
                raise MergeError(f"{where}: label {label!r} is not a name")
            if code is not None and (not isinstance(code, list) or not all(isinstance(c, str) for c in code)):
                raise MergeError(f"{where}: code is a list of lines")
            item = item["context"]
        out.append((parse_context(item, where, intervals), None if label is None else str(label), code))
    return out


# ------------------------------------------------------------------ the run

class MergeRun:
    """The merges of a set of contexts and the frames showing them (``frames``, ``meta``, ``tables``)."""

    def __init__(self, contexts, *, limit: int = 2, heuristic: str = "similarity", seed: int = 0,
                 program: Program | None = None, block: str | None = None, name: str | None = None,
                 intervals: bool = False, thresholds="machine", fixnum_bits: int = 61, vector_bounds: bool = True,
                 placement: str = "circle", edges: str = "all", edge_width=(1.0, 7.0), log_range=None,
                 show: list[str] | None = None, color_keys: bool = False, room: tuple[float, float] = (1136.0, 430.0),
                 magnitude: bool = False):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise MergeError(f"limit: expected an integer >= 1, got {limit!r}")
        if placement not in PLACEMENTS:
            raise MergeError(f"placement: use {', '.join(PLACEMENTS)}")
        self.distance = DISTANCES.get(heuristic)
        if self.distance is None and placement == "distance":
            raise MergeError(f"placement=distance needs a heuristic with a distance ({', '.join(DISTANCES)}); "
                             f"{heuristic} picks its pairs at random")
        self.heuristic = heuristic
        self.limit = limit
        self.edges_mode = edges if self.distance is not None else "none"
        self.color_keys = color_keys
        self.magnitude = magnitude  # distances shown as their log10 (display only)
        items = _items(contexts, intervals)
        self.program, self.block = self._block(program, block, name, [c for c, _, _ in items])
        self.real_block = program is not None
        fn = self.block.function
        self.spec = Specializer(self.program, limit, heuristic, entry=fn, limits={fn: limit}, seed=seed,
                                intervals=intervals, thresholds=thresholds, fixnum_bits=fixnum_bits,
                                vector_bounds=vector_bounds, emit=self._event)
        self.events: list[tuple[str, dict]] = []
        with using_fixnum_bits(fixnum_bits), using_vector_bounds(vector_bounds):
            self._run(items)
            self.code = self._code(items, intervals, thresholds, fixnum_bits, vector_bounds)
        self.parents: dict[int, tuple[int, int]] = {}
        self.show = show
        self._frames(items, edge_width, log_range)
        self._place(placement, room)

    # ---------------------------------------------------------------- program and block
    def _block(self, program: Program | None, ref: str | None, name: str | None,
               contexts: list[Context]) -> tuple[Program, Block]:
        names: list[str] = []
        for c in contexts:
            names += [v for v in c.vars() if v not in names]
        if program is None:
            if ref is not None:
                raise MergeError("block names a block of program or source; give one of them")
            name = name or "C"
            if not _NAME.fullmatch(name):
                raise MergeError(f"name: {name!r} is not a block name")
            try:
                prog = parse(f"function {name}({', '.join(names)})\n{name}: fail\n")
            except ProgramError as e:
                raise MergeError(f"contexts: {e}") from None
            return prog, prog.function(name).entry
        if name is not None:
            raise MergeError("name labels the contexts without a program; with one, the labels come from its block")
        if ref is None:
            raise MergeError("block: name the block of the program whose versions these contexts are "
                             "(LABEL or FUNCTION/LABEL)")
        if "/" in ref:
            fn, _, label = ref.rpartition("/")
            if fn not in program.functions:
                raise MergeError(f"block: no function {fn!r} (functions: {', '.join(program.functions)})")
            if label not in program.functions[fn].blocks:
                raise MergeError(f"block: function {fn} has no block {label!r}")
            blk = program.functions[fn].blocks[label]
        else:
            found = [f.blocks[ref] for f in program.functions.values() if ref in f.blocks]
            if not found:
                raise MergeError(f"block: no block {ref!r} in the program")
            if len(found) > 1:
                raise MergeError(f"block: several functions have a block {ref!r}: write "
                                 + " or ".join(f"{b.function}/{ref}" for b in found))
            blk = found[0]
        bad = [n for n in names if n not in blk.params]
        if bad:
            raise MergeError(f"contexts: {', '.join(bad)} {'is' if len(bad) == 1 else 'are'} not a parameter of "
                             f"block {blk.key} (its parameters: {', '.join(blk.params) or 'none'})")
        return program, blk

    # ---------------------------------------------------------------- merges
    def _event(self, kind: str, **info) -> None:
        if kind == "must-merge":
            self._last_id = max(self.spec.by_id)
        elif kind == "merge":
            # whether the union is a new version, and if not, which version holds it (a context merged away
            # earlier resolves to the version it was merged into)
            pair = [self.spec.by_id[i] for i in info["merged"]]
            union = self.spec.merge_contexts(pair)[0].restrict(self.block.params)
            held = self.spec.versions.get(self.block.key, {}).get(union)
            info = {**info, "created": info["into"] > self._last_id, "union": held.id if held is not None else None}
        self.events.append((kind, info))

    def _run(self, items) -> None:
        spec = self.spec
        self.initial: list[int] = []
        for i, (ctx, label, _) in enumerate(items):
            v = spec.get_or_create(self.block, ctx)
            if v.id in self.initial:
                j = self.initial.index(v.id)
                raise MergeError(f"contexts[{i}] is the same context as contexts[{j}]")
            spec.roots.append(v)
            self.initial.append(v.id)
            if label is not None:
                v.label = label
        spec.invalidate()
        spec.merge_some(self.block)
        labels = [v.label for v in spec.by_id.values()]
        dup = sorted({x for x in labels if labels.count(x) > 1})
        if dup:
            raise MergeError(f"label {dup[0]} names two contexts (merged contexts are labelled "
                             f"{self.block.name}N); choose other labels")

    def _code(self, items, intervals, thresholds, fixnum_bits, vector_bounds) -> dict[int, tuple[list, list]]:
        """The block specialized in every context (looks only), and its exit context."""
        out: dict[int, tuple[list, list]] = {}
        given = {self.initial[i]: code for i, (_, _, code) in enumerate(items) if code is not None}
        for vid, v in self.spec.by_id.items():
            if vid in given:
                out[vid] = ([{"text": t} for t in given[vid]], [])
            elif self.real_block:
                s = Specializer(self.program, self.limit, "similarity", entry=self.block.function, intervals=intervals,
                                thresholds=thresholds, fixnum_bits=fixnum_bits, vector_bounds=vector_bounds)
                w = Version(len(self.spec.by_id) + 1000, self.block, v.context, v.label)
                s.specialize(w)
                out[vid] = ([line.as_dict() for line in w.body or []],
                            w.context_after.lines() if w.context_after is not None else [])
            else:
                out[vid] = ([], [])
        return out

    # ---------------------------------------------------------------- frames
    def _d(self, a: int, b: int) -> float:
        by = self.spec.by_id
        return self.distance(by[a].context, by[b].context)

    def _frames(self, items, edge_width, log_range) -> None:
        by = self.spec.by_id
        self.frames: list[dict] = []
        self.meta: list[dict] = []
        live = list(self.initial)
        merges = []
        for kind, info in self.events:
            if kind == "merge":
                merges.append(info)
        self.merges = merges
        # every frame: (kind, live vids, marks, edge states, absorbed vids, info). A merge takes three frames: the
        # pair picked; the merge (the pair at their meeting point, absorbed, the result there, the others dimmed);
        # the settle (everything clear again, back in the layout). The last settle is the `done` frame.
        steps: list[tuple[str, list[int], dict, dict, list[int], dict]] = [("start", list(live), {}, {}, [], {})]
        self.orders: dict[int, list[int]] = {0: list(live)}  # the order of the live nodes (circle placement)
        seq = list(live)
        for n_merge, info in enumerate(merges):
            pair, into = list(info["merged"]), info["into"]
            marks = {p: "merge" for p in pair}
            steps.append(("pick", list(live), marks, {_key(*pair): "merge"}, [], info))
            self.orders[len(steps) - 1] = list(seq)
            olds = [p for p in pair if p != into]
            arrive = into not in live  # the result appears when the pair reaches it
            others = [v for v in live if v not in pair and v != into]
            if arrive:
                self.parents[into] = (pair[0], pair[1])
            marks = {v: "dim" for v in others}
            marks.update({p: "absorbed" for p in olds})
            marks[into] = "merged"
            after = others + [into] if arrive else [v for v in live if v not in olds]
            steps.append(("merge", after, marks, {}, olds, {**info, "arrive": arrive, "others": others}))
            if arrive:
                seq = [into if v == min(pair) else v for v in seq]
            seq = [v for v in seq if v not in olds]
            live = after
            states = {_key(into, x): "new" for x in live if x != into} if arrive else {}
            last = n_merge == len(merges) - 1
            steps.append(("done" if last else "settle", list(live), {into: "merged"}, states, [],
                          {**info, "arrive": arrive}))
            self.orders[len(steps) - 1] = list(seq)
        if not merges:
            steps.append(("done", list(live), {}, {}, [], {}))
            self.orders[1] = list(seq)
        # widths: the log of the distance, clamped, thick for the nearest pairs
        pairs = set()
        for _, lv, _, _, _, _ in steps:
            pairs |= {_key(a, b) for i, a in enumerate(lv) for b in lv[i + 1:]}
        self.dist: dict[str, float] = {}
        if self.distance is not None:
            for k in pairs:
                a, b = map(int, k.split("--"))
                self.dist[k] = self._d(a, b)
        logs = [math.log10(1 + d) for d in self.dist.values()]
        if log_range is None:
            lo, hi = (min(logs), max(logs)) if logs else (0.0, 1.0)
        else:
            lo, hi = log_range
        self.log_range = (lo, hi)
        wmin, wmax = edge_width

        def width(d: float) -> float:
            x = min(max(math.log10(1 + d), lo), hi)
            t = (x - lo) / (hi - lo) if hi > lo else 0.5
            return round(wmax - t * (wmax - wmin), 2)

        self.width = width
        merges_done = 0
        for kind, lv, marks, states, gone, info in steps:
            nodes = {str(v): {"state": "done"} for v in lv}
            for v in gone:  # absorbed by the merge: drawn at the meeting point, faded out
                nodes[str(v)] = {"state": "done"}
            for v, m in marks.items():
                nodes[str(v)]["mark"] = m
            edges = {}
            if self.edges_mode != "none":
                # a merge frame draws only the edges between the contexts the merge leaves alone, dimmed
                drawn = info["others"] if kind == "merge" else lv
                for i, a in enumerate(drawn):
                    for b in drawn[i + 1:]:
                        k = _key(a, b)
                        state = states.get(k)
                        if kind in ("pick", "merge") and state is None:
                            state = "dim"
                        if self.edges_mode == "pair" and state != "merge":
                            continue
                        e = {"w": width(self.dist[k]), "d": self.shown(self.dist[k])}
                        if state:
                            e["state"] = state
                        edges[k] = e
            if kind == "merge" and info["arrive"]:
                nodes[str(info["into"])]["arrive"] = True
            if kind == "merge":
                merges_done += 1
            frame = {"nodes": nodes, "edges": edges, "caption": self._caption(kind, lv, info),
                     "panel": self._panel(kind, lv, info, merges_done)}
            self.frames.append(frame)
            meta = {"event": kind, "algo": ALGO[kind]}
            if self.real_block:
                meta["block"] = self.block.key
                meta["function"] = self.block.function
                lines = [i.line for i in self.block.instrs]
                meta["lines"] = list(range(min(lines), max(lines) + 1)) if lines else []
                meta["line"] = self.block.line
            self.meta.append(meta)
        self.steps = steps

    def shown(self, d: float) -> str:
        """A distance as displayed (captions, panel, edge labels): compact, or its log10 with
        ``distance_magnitude``. The merges and widths always use the raw distance."""
        return magnitude(d) if self.magnitude else compact(d)

    def _chip(self, vid: int) -> str:
        v = self.spec.by_id[vid]
        return ver(v.label, self.key_of(vid))

    def key_of(self, vid: int) -> str:
        """The colour key of a version: its block, or the version itself with ``colors: context``."""
        return f"{self.block.key}#{vid}" if self.color_keys else self.block.key

    def _caption(self, kind: str, live: list[int], info: dict) -> str:
        n = len(live)
        if kind == "start":
            pairs = n * (n - 1) // 2
            how = f"{pairs} pair{'s' if pairs != 1 else ''}" + ("" if self.distance else ", picked at random")
            if n <= self.limit:
                return join([f"{op('done')} {n} contexts", f"limit {self.limit}", "nothing to merge"])
            return join([f"{op('limit')} {n} contexts for a limit of {self.limit}", how,
                         f"{tag(self.heuristic)}"])
        if kind == "pick":
            a, b = info["merged"]
            pairs = n * (n - 1) // 2
            if self.distance is None:
                return join([f"{op('random pair')} {self._chip(a)} {self._chip(b)}", f"one of {pairs} pairs"])
            d = self.shown(self._d(a, b))
            what = "log₁₀ distance" if self.magnitude else "distance"
            return join([f"{op('closest pair')} {self._chip(a)} {self._chip(b)}", f"{what} {d}",
                         f"the smallest of {pairs} pair{'s' if pairs != 1 else ''}"])
        if kind == "merge":
            into = info["into"]
            olds = [i for i in info["merged"] if i != into]
            parts = [f"{op('merge')} {' '.join(self._chip(i) for i in olds)} → {self._chip(into)}"]
            if into in info["merged"]:
                parts.append("its context is their union")
            elif info.get("created"):
                parts.append("new context, the union of theirs")
            else:  # the union is a context merged away earlier: its version resolves to `into`
                parts.append(f"their union is {self._chip(info['union'])}, merged into {self._chip(into)} earlier"
                             if info.get("union") not in (None, into) else "their union is already a context")
            widened = info.get("widened") or []
            if widened:
                parts.append(f"{tag('widened')} {', '.join(var(w) for w in widened)}")
            parts.append(rich_context(self.spec.by_id[into].context))
            return join(parts)
        what = self._outcome(info) if info else ""
        if kind == "settle":
            return join([f"{op('limit')} {n} contexts for a limit of {self.limit}", what])
        m = len(self.merges)
        return join([f"{op('done')} {n} context{'s' if n != 1 else ''}", f"{m} merge{'s' if m != 1 else ''}",
                     f"limit {self.limit}", what])

    def _outcome(self, info: dict) -> str:
        """What the last merge left: a new context in place of its pair, or the pair absorbed."""
        into = info["into"]
        olds = [i for i in info["merged"] if i != into]
        if info["arrive"]:
            return f"{self._chip(into)} in place of {' and '.join(self._chip(i) for i in olds)}"
        return f"{' and '.join(self._chip(i) for i in olds)} absorbed into {self._chip(into)}"

    def _panel(self, kind: str, live: list[int], info: dict, merges: int) -> dict:
        by = self.spec.by_id
        panel = {"contexts": [by[v].label for v in live], "limit": self.limit, "merges": merges}
        if self.distance is not None:
            panel["distance"] = self.shown(self._d(*info["merged"])) if kind in ("pick", "merge") else ""
        return panel

    # ---------------------------------------------------------------- tables
    def tables(self) -> dict:
        versions = {}
        for vid, v in self.spec.by_id.items():
            code, after = self.code[vid]
            versions[str(vid)] = {"label": v.label, "block": self.key_of(vid), "function": self.block.function,
                                  "name": self.block.name, "context": v.context.lines(), "code": code,
                                  "after": after}
        return {"versions": versions}

    # ---------------------------------------------------------------- placement
    def _place(self, placement: str, room: tuple[float, float]) -> None:
        tables = self.tables()["versions"]
        show = self.show or ["label", "context"]
        sizes = [node_size(v, show) for v in tables.values()]
        self.size = (max(s[0] for s in sizes), max(s[1] for s in sizes))
        if placement == "circle":
            positions = self._circle(room)
        else:
            positions = self._distance(room)
        positions = self._meet(positions)
        # the drawing's box: every position of every frame, moved to the margin
        w, h = self.size
        xs = [p[0] for f in positions for p in f.values()]
        ys = [p[1] for f in positions for p in f.values()]
        x0, y0 = min(xs) - MARGIN, min(ys) - MARGIN
        self.box = {"width": round(max(xs) + w + MARGIN - x0, 1), "height": round(max(ys) + h + MARGIN - y0, 1)}
        for frame, pos in zip(self.frames, positions):
            frame["pos"] = {k: [round(p[0] - x0, 1), round(p[1] - y0, 1)] for k, p in pos.items()}

    def _drawn(self, i: int) -> list[int]:
        _, live, _, _, gone, _ = self.steps[i]
        return live + gone

    def _meet(self, positions: list[dict]) -> list[dict]:
        """The merge frames: the contexts left alone stay where the pick frame drew them, and the pair meets on the
        context that remains (the absorbed one under it), or, for a result not drawn yet, halfway between them,
        where the result appears."""
        out = list(positions)
        for i, (kind, live, _, _, absorbed, info) in enumerate(self.steps):
            if kind != "merge":
                continue
            prev = out[i - 1]
            into, pair = str(info["into"]), [str(v) for v in info["merged"]]
            if into in prev:
                meet = prev[into]
            else:
                (ax, ay), (bx, by) = prev[pair[0]], prev[pair[1]]
                meet = [(ax + bx) / 2, (ay + by) / 2]
            pos = {str(v): prev[str(v)] for v in info["others"]}
            for v in pair + [into]:
                pos[v] = list(meet)
            out[i] = pos
        return out

    def _circle(self, room) -> list[dict]:
        """Live contexts evenly on an ellipse, in the order given; a new result takes the place of the older
        context of its pair in that order, and the settle frame spaces the nodes evenly again."""
        w, h = self.size
        counts = sorted({len(s) for s in self.orders.values()})

        def slots(n: int, rx: float, ry: float) -> list[tuple[float, float]]:
            if n == 1:
                return [(0.0, 0.0)]
            start = math.pi if n == 2 else -math.pi / 2
            return [(rx * math.cos(start + 2 * math.pi * i / n), ry * math.sin(start + 2 * math.pi * i / n))
                    for i in range(n)]

        def clear(pts) -> bool:
            for i, (ax, ay) in enumerate(pts):
                for bx, by in pts[i + 1:]:
                    if abs(ax - bx) < w + NODE_GAP and abs(ay - by) < h + NODE_GAP:
                        return False
            return True

        def radius(k: float) -> float:
            r = 0.0
            for n in counts:
                lo = r
                while not clear(slots(n, lo * k, lo)):
                    lo += 2.0
                r = max(r, lo)
            return r

        best = None
        for k in CIRCLE_ASPECTS:
            r = radius(k)
            bw, bh = 2 * r * k + w + 2 * MARGIN, 2 * r + h + 2 * MARGIN
            scale = min(room[0] / bw, room[1] / bh)
            if best is None or scale > best[0] + 1e-9:
                best = (scale, k, r)
        _, k, r = best
        out = []
        for i in range(len(self.steps)):
            seq = self.orders.get(i)
            if seq is None:  # a merge frame: placed by _meet
                out.append({})
                continue
            pts = slots(len(seq), r * k, r)
            out.append({str(v): [pts[j][0] - w / 2, pts[j][1] - h / 2] for j, v in enumerate(seq)})
        return out

    def _distance(self, room) -> list[dict]:
        """Metric MDS of every context of the run on the clamped logs of their distances: a node keeps one
        place for the whole run, and nodes are then pushed apart until no two boxes overlap."""
        w, h = self.size
        vids = sorted(self.spec.by_id)
        n = len(vids)
        lo, hi = self.log_range
        near, far = SEPARATION
        delta = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                x = min(max(math.log10(1 + self._d(vids[i], vids[j])), lo), hi)
                t = (x - lo) / (hi - lo) if hi > lo else 0.5
                delta[i][j] = delta[j][i] = near + t * (far - near)
        pts = _principal(_smacof(delta))
        # node units: the diagonal of a node and the gap
        unit = math.hypot(w + NODE_GAP, h + NODE_GAP)
        # distances fix neither a rotation nor how tightly the drawing may pack: the rotation, scale and
        # horizontal stretch whose drawing fits the room best, the least distorted first (2 % to beat it)
        best = None
        for scale_, stretch in DISTANCE_FITS:
            for deg in range(0, 180, 5):
                a = math.radians(deg)
                c, s = math.cos(a), math.sin(a)
                cand = [((x * c - y * s) * unit * scale_ * stretch, (x * s + y * c) * unit * scale_) for x, y in pts]
                cand = _separate(cand, w + NODE_GAP, h + NODE_GAP)
                bw = max(p[0] for p in cand) - min(p[0] for p in cand) + w + 2 * MARGIN
                bh = max(p[1] for p in cand) - min(p[1] for p in cand) + h + 2 * MARGIN
                fit = min(room[0] / bw, room[1] / bh)
                if best is None or fit > best[0] * 1.02:
                    best = (fit, cand)
        pts = best[1]
        at = {vid: (p[0] - w / 2, p[1] - h / 2) for vid, p in zip(vids, pts)}
        out = []
        for i in range(len(self.steps)):
            out.append({str(v): list(at[v]) for v in self._drawn(i)})
        return out


# ------------------------------------------------------------------ helpers

def _key(a: int, b: int) -> str:
    return f"{min(a, b)}--{max(a, b)}"


def magnitude(d: float) -> str:
    """The log10 of a distance, two decimals: ``6.22``; ``-∞`` for a distance of 0."""
    return f"{math.log10(d):.2f}" if d > 0 else "-∞"


def compact(d: float) -> str:
    """A distance in three significant digits: ``16``, ``0.25``, ``4.8k``, ``1.67M``."""
    for unit, scale in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(d) >= scale:
            return f"{d / scale:.3g}{unit}"
    return f"{d:.3g}"


def _smacof(delta: list[list[float]]) -> list[tuple[float, float]]:
    """Stress majorization in the plane (unit weights), started from classical MDS. Deterministic."""
    n = len(delta)
    if n == 1:
        return [(0.0, 0.0)]
    if n == 2:
        return [(-delta[0][1] / 2, 0.0), (delta[0][1] / 2, 0.0)]
    # classical MDS: the two leading eigenvectors of the double-centred squared distances
    sq = [[delta[i][j] ** 2 for j in range(n)] for i in range(n)]
    row = [sum(r) / n for r in sq]
    total = sum(row) / n
    b = [[-0.5 * (sq[i][j] - row[i] - row[j] + total) for j in range(n)] for i in range(n)]
    axes = []
    for k in range(2):
        v = [1.0 + 0.1 * ((i * 7 + k * 3) % 5) for i in range(n)]
        lam = 0.0
        for _ in range(200):
            u = [sum(b[i][j] * v[j] for j in range(n)) for i in range(n)]
            for a, av in axes:  # deflation
                dot = sum(x * y for x, y in zip(a, v))
                u = [x - av * dot * y for x, y in zip(u, a)]
            norm = math.sqrt(sum(x * x for x in u)) or 1.0
            lam = norm
            v = [x / norm for x in u]
        axes.append((v, lam))
    x = [(axes[0][0][i] * math.sqrt(max(axes[0][1], 1e-9)), axes[1][0][i] * math.sqrt(max(axes[1][1], 1e-9)))
         for i in range(n)]
    for _ in range(SMACOF_ITERATIONS):
        nx = []
        for i in range(n):
            sx = sy = 0.0
            for j in range(n):
                if i == j:
                    continue
                dx, dy = x[i][0] - x[j][0], x[i][1] - x[j][1]
                d = math.hypot(dx, dy)
                ratio = delta[i][j] / d if d > 1e-12 else 0.0
                sx += x[j][0] + ratio * dx
                sy += x[j][1] + ratio * dy
            nx.append((sx / n, sy / n))
        x = nx
    return x


def _principal(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Centred and rotated so that the widest spread is horizontal; signs fixed by the first point."""
    n = len(pts)
    cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    pts = [(x - cx, y - cy) for x, y in pts]
    sxx = sum(x * x for x, _ in pts)
    syy = sum(y * y for _, y in pts)
    sxy = sum(x * y for x, y in pts)
    a = 0.5 * math.atan2(2 * sxy, sxx - syy)
    c, s = math.cos(a), math.sin(a)
    pts = [(x * c + y * s, -x * s + y * c) for x, y in pts]
    fx = -1.0 if pts[0][0] > 1e-9 else 1.0
    fy = -1.0 if pts[0][1] > 1e-9 else 1.0
    return [(x * fx, y * fy) for x, y in pts]


def _separate(pts: list[tuple[float, float]], w: float, h: float) -> list[tuple[float, float]]:
    """Push overlapping boxes (``w`` by ``h`` around each point) apart along the axis of least overlap."""
    pts = [list(p) for p in pts]
    for _ in range(500):
        moved = False
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                dx, dy = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
                ox, oy = w - abs(dx), h - abs(dy)
                if ox <= 0.01 or oy <= 0.01:
                    continue
                moved = True
                if ox / w < oy / h:
                    s = (ox / 2 + 0.5) * (1 if dx > 0 or (dx == 0 and i < j) else -1)
                    pts[i][0] -= s
                    pts[j][0] += s
                else:
                    s = (oy / 2 + 0.5) * (1 if dy > 0 or (dy == 0 and i < j) else -1)
                    pts[i][1] -= s
                    pts[j][1] += s
        if not moved:
            break
    return [(p[0], p[1]) for p in pts]
