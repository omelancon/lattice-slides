"""Basic block versioning components: ``bbv-anim`` (an SBBV or ΛV run, one frame per event) and
``bbv-cfg`` (the source CFG of a program, static or following an animation). Spec 8.8 and 9.1."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

import re

from ..anim import frame_store, frames_of
from ..bbv.ir import Program, ProgramError, parse
from ..bbv.layout import layout_frames, node_size
from ..bbv.trace import ABSINT_EVENTS, EVENTS, AbstractTrace, VersioningTrace
from .animations import PanelAt, panel_root
from .base import Component, ComponentError, Part, RenderResult, register

SHOW = ["label", "context", "code"]
CLICKABLE_SHOW = SHOW + ["after"]  # an enlarged block may also show its exit context


class BbvCommonOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    program: str | None = None  # a .bbv file, or "file.py:function" returning a Program or its text
    source: str | None = None  # the program text itself
    functions: list[str] | None = None
    show: list[str] | None = None
    colors: Literal["origin", "none"] = "origin"
    direction: Literal["TB", "LR"] = "TB"
    wrap: int = 4  # versions per line of a rank before wrapping
    height: int | None = None
    prims: dict | None = None
    clickable: bool = True  # a click on a block enlarges it (spec 9.5)
    clickable_show: list[str] | None = None  # what the enlarged block shows; default everything
    rank_wrap: Any = 1  # bands of ranks (spec 9.5): an integer >= 1 or "auto"
    rank_wraps: dict | None = None  # per function, over rank_wrap
    rank_flow: Literal["restart", "snake"] = "restart"
    fit_aspect: Any = None  # "W:H", the target aspect of `auto`


class BbvAnimOptions(BbvCommonOptions):
    algorithm: Literal["sbbv", "lv"] = "sbbv"
    limit: int = 2
    limits: dict | None = None
    heuristic: Literal["similarity", "arithmetic", "random"] = "similarity"
    entry: str | None = None
    events: list[str] | None = None
    granularity: Literal["block", "instruction"] = "block"
    until: int | None = None
    call_edges: bool = False
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    caption: Literal["auto", "none"] = "auto"
    max_steps: int = 5000
    intervals: bool = False
    thresholds: str | list[int | str] = "machine"
    fixnum_bits: int = 61
    vector_bounds: bool = True  # vector lengths as symbolic bounds (with intervals)
    paths: list | None = None  # frames after the run highlighting the versions of a path (spec 9.5)
    fold: bool = False  # ΛV replaces a call by its constant result when the callee has no side effect (spec 9.5)


class BbvCfgOptions(BbvCommonOptions):
    pass


class AbstractInterpOptions(BbvCommonOptions):
    entry: str | None = None  # the function analysed
    thresholds: str | list[int | str] = "machine"
    narrowing: bool = True
    fixnum_bits: int = 61
    vector_bounds: bool = True  # vector lengths as symbolic bounds
    events: list[str] | None = None
    granularity: Literal["block", "instruction"] = "block"
    until: int | None = None
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    history: list[str] | None = None
    caption: Literal["auto", "none"] = "auto"
    max_steps: int = 2000


_KNOWN = {"program", "source", "functions", "show", "colors", "direction", "height", "prims", "algorithm", "limit", "limits",
          "heuristic", "entry", "events", "granularity", "until", "call_edges", "panel", "caption", "max_steps", "wrap",
          "thresholds", "narrowing", "fixnum_bits", "history", "intervals", "clickable", "clickable_show", "vector_bounds",
          "panel_at", "paths", "fold", "rank_wrap", "rank_wraps", "rank_flow", "fit_aspect"}


def load_program(opts: BbvCommonOptions, ctx) -> Program:
    from .animations import _extras

    if opts.source is not None and opts.program is not None:
        raise ComponentError("give either 'program' or 'source', not both")
    try:
        if opts.source is not None:
            prog = parse(opts.source, opts.prims)
        elif opts.program is None:
            raise ComponentError("'program' (a .bbv file or file.py:function) or 'source' is required")
        elif ":" in opts.program:
            extras = {k: v for k, v in _extras(opts).items() if k not in _KNOWN}
            result = ctx.call(opts.program, **extras)
            if isinstance(result, str):
                prog = parse(result, opts.prims)
            elif isinstance(result, Program):
                prog = result
                if opts.prims:  # a Program built in Python: its prims are added here
                    prog.add_prims(opts.prims)
                    prog.finalize()
            else:
                raise ComponentError(f"{opts.program} must return a Program or its text")
        else:
            prog = parse(ctx.path(opts.program).read_text(encoding="utf-8"), opts.prims)
    except ProgramError as e:
        raise ComponentError(f"program: {e}") from None
    return prog


def _show(opts: BbvCommonOptions, default: list[str]) -> list[str]:
    show = opts.show if opts.show is not None else default
    bad = [s for s in show if s not in SHOW]
    if bad:
        raise ComponentError(f"show: unknown item(s) {bad}; use {SHOW}")
    return show


def _zoom(opts: BbvCommonOptions, versions: dict, frames: list[dict]) -> dict | None:
    """What an enlarged block shows and its size per version, or ``None`` when blocks are not
    clickable. A node whose context changes with the frame (abstract interpretation) is sized on
    the largest of its frames, as the drawing is."""
    if not opts.clickable:
        return None
    show = opts.clickable_show if opts.clickable_show is not None else CLICKABLE_SHOW
    bad = [s for s in show if s not in CLICKABLE_SHOW]
    if bad:
        raise ComponentError(f"clickable_show: unknown item(s) {bad}; use {CLICKABLE_SHOW}")
    sizes = {vid: node_size(v, show) for vid, v in versions.items()}
    for f in frames:
        for vid, st in f["nodes"].items():
            if "lines" not in st and "after" not in st:
                continue
            v = versions[vid]
            w, h = node_size({**v, "context": st.get("lines", v["context"]), "after": st.get("after", v["after"])}, show)
            sizes[vid] = (max(sizes[vid][0], w), max(sizes[vid][1], h))
    return {"show": show, "sizes": {vid: list(s) for vid, s in sizes.items()}}


SLIDE_PAD_X = 72  # the horizontal padding of .lt-slide (lattice.css)
PANEL_GAP = 28  # the gap between the drawing and its panel (.lt-ga-main)
DEFAULT_HEIGHT = 430  # the default height of the drawing (.lt-ga-canvas)


def _room(ctx, height: float, panel: bool) -> tuple[float, float]:
    """The room of a drawing on its slide: the content width of the deck's aspect, less the panel when it
    shows beside the drawing, by ``height``."""
    from ..emit import DESIGN_SIZES

    aspect = getattr(ctx.meta, "aspect", "16:9")
    width = float(DESIGN_SIZES.get(aspect, DESIGN_SIZES["16:9"])[0] - 2 * SLIDE_PAD_X)
    if panel:  # the panel beside the drawing: clamp(150px, 22%, 260px) in lattice.css, and the gap
        width -= min(max(150.0, 0.22 * width), 260.0) + PANEL_GAP
    return (width, height)


def _aspect(value) -> float:
    """``fit_aspect``: ``"W:H"`` as the ratio W / H."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", str(value)) if isinstance(value, str) else None
    if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
        hint = " (in a YAML body, quote it: \"16:9\")" if isinstance(value, int) else ""
        raise ComponentError(f"fit_aspect: expected two positive numbers W:H, got {value!r}{hint}")
    return float(m.group(1)) / float(m.group(2))


def _count(value, what: str) -> int | str:
    """A band count: an integer >= 1 or ``auto`` (spec 9.5)."""
    if isinstance(value, str) and value.strip() == "auto":
        return "auto"
    if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*", value):
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    raise ComponentError(f"{what}: expected an integer >= 1 or auto, got {value!r}")


def _bands(opts: BbvCommonOptions, prog: Program, ctx, panel: bool) -> dict:
    """The keyword arguments of ``layout_frames`` for the bands of ranks, checked (spec 9.5)."""
    wrap = _count(opts.rank_wrap, "rank_wrap")
    wraps = None
    if opts.rank_wraps is not None:
        if not isinstance(opts.rank_wraps, dict):
            raise ComponentError("rank_wraps: expected a mapping {FUNCTION: N | auto}")
        wraps = {}
        for name, value in opts.rank_wraps.items():
            if name not in prog.functions:
                raise ComponentError(f"rank_wraps: {name!r} is not a function of the program "
                                     f"(functions: {', '.join(prog.functions)})")
            wraps[name] = _count(value, f"rank_wraps: {name}")
    auto = wrap == "auto" or any(v == "auto" for v in (wraps or {}).values())
    height = float(opts.height or DEFAULT_HEIGHT)
    fit = None
    if opts.fit_aspect is not None:
        ratio = _aspect(opts.fit_aspect)
        if auto:
            fit = (height * ratio, height)
        else:
            ctx.warn("fit_aspect has no effect without rank_wrap=auto (or auto in rank_wraps)")
    if auto and fit is None:
        fit = _room(ctx, height, panel)
    cuts = None
    leader = getattr(ctx, "leader", None)
    if leader is not None and isinstance(leader.data, dict):
        lead = (leader.data.get("box") or {}).get("rankWrap") or {}
        cuts = {name: band["cut"] for name, band in lead.items()} or None
    return {"rank_wrap": wrap, "rank_wraps": wraps, "rank_flow": opts.rank_flow, "fit": fit, "cuts": cuts}


def _layout(tables: dict, frames: list[dict], show: list[str], opts: BbvCommonOptions, prog: Program, ctx,
            panel: bool = False, call_edges: bool = False):
    """``layout_frames`` with the options of the drawing; a clamped band count warns (LT046). Returns the
    frames with their positions (``pos``) and the loops that travel before their band (``sides``, spec 9.5)."""
    notes: list[str] = []
    sides: list[dict] = []
    box, positions = layout_frames(tables, frames, show, _layout_fn(ctx), opts.direction, opts.wrap,
                                   call_edges=call_edges, notes=notes, sides=sides, **_bands(opts, prog, ctx, panel))
    for note in notes:
        ctx.warn(note)
    placed = []
    for f, p, sd in zip(frames, positions, sides):
        g = {**f, "pos": p}
        if sd:
            g["sides"] = sd
        placed.append(g)
    return box, placed


def _layout_fn(ctx):
    from ..graphs import has_graphviz

    if not has_graphviz():
        return None
    return lambda g: ctx.layout(g, engine="dot", rankdir="TB", edge_labels=False)


def _colors(tables: dict, ctx, mode: str) -> dict[str, str]:
    if mode == "none":
        return {}
    series = list(ctx.palette.get("series") or []) or ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2",
                                                       "#b279a2", "#ff9da6", "#9d755d"]
    out = {}
    i = 0
    for fn in tables["program"]["functions"]:
        for b in fn["blocks"]:
            out[b["key"]] = series[i % len(series)]
            i += 1
    return out


# ---------------------------------------------------------------- parts (spec 9.5), for arrows
KINDS = {"goto": "goto", "true": "true", "false": "false", "return": "return", "call": "call", "#t": "true",
         "#f": "false"}
_EDGE = re.compile(r"^(.+?)->(.+)$")


class _Drawing:
    """What a versioning drawing shows, read from its render result: its nodes (versions; a block each in a
    fixed CFG), and which nodes and edges each position draws, as ``bbv.js`` draws them."""

    def __init__(self, result: RenderResult):
        data = result.data or {}
        self.versions: dict[str, dict] = data["tables"]["versions"]
        self.functions = [f["name"] for f in data["tables"]["program"]["functions"]]
        self.blocks = {f["name"]: [b["name"] for b in f["blocks"]] for f in data["tables"]["program"]["functions"]}
        frames = frames_of(data["frames"])
        if data.get("highlight") is not None:  # a bbv-cfg follower: one drawing at every position
            frames = frames[:1]
        call_edges = bool(data.get("callEdges"))
        self.nodes: list[set[str]] = []
        self.edges: list[set[str]] = []
        for f in frames:
            nodes = set((f.get("nodes") or {}).keys())
            edges = set()
            for key in (f.get("edges") or {}):
                src, rest = key.split("->", 1)
                dst, kind = rest.split(":", 1)
                if src in nodes and dst in nodes and (kind != "call" or call_edges):
                    edges.add(key)
            self.nodes.append(nodes)
            self.edges.append(edges)
        self.static = len(frames) == 1 or result.positions != len(frames)
        self.all_edges = sorted(set().union(*self.edges)) if self.edges else []

    # ---------------------------------------------------------------- names
    def node(self, ref: str, function: str | None = None) -> tuple[set[str], str, str | None]:
        """The vids a node reference names, the function it lives in, and a warning."""
        if "/" in ref:
            function, label = ref.rsplit("/", 1)
            if function not in self.functions:
                raise ComponentError(f"function {function!r} is not drawn here (drawn: {', '.join(self.functions)})")
            fns = [function]
        else:
            label = ref
            fns = [function] if function else self.functions
        if not label:
            raise ComponentError(f"{ref!r} is not a block name")
        blocks = [f for f in fns if label in self.blocks[f]]
        versions: dict[str, list[str]] = {}
        for vid, v in self.versions.items():
            if v["label"] == label and v["function"] in fns:
                versions.setdefault(v["function"], []).append(vid)
        if blocks:
            if len(blocks) > 1:
                raise ComponentError(f"several drawn functions have a block {label!r}: write "
                                     + " or ".join(f"{f}/{label}" for f in blocks))
            fn = blocks[0]
            vids = {vid for vid, v in self.versions.items() if v["block"] == f"{fn}/{label}"}
            if not vids or not any(vids & n for n in self.nodes):
                raise ComponentError(f"block {fn}/{label} has no version in any frame of this drawing")
            other = [vid for f, vs in versions.items() for vid in vs if vid not in vids]
            warning = None
            if other:
                v = self.versions[other[0]]
                warning = (f"{label!r} is a block and also a version of block {v['name']!r}; it names the block "
                           f"(rename one of the blocks to point at the version)")
            return vids, fn, warning
        if versions:
            if len(versions) > 1:
                raise ComponentError(f"several drawn functions have a version {label!r}: write "
                                     + " or ".join(f"{f}/{label}" for f in versions))
            fn, vids = next(iter(versions.items()))
            return set(vids), fn, None
        raise ComponentError(self._unknown(label, fns))

    def _unknown(self, label: str, fns: list[str]) -> str:
        names = [b if len(self.functions) == 1 else f"{f}/{b}" for f in fns for b in self.blocks[f]]
        fixed = all(v["label"] == v["name"] for v in self.versions.values())  # a fixed CFG: no versions
        msg = f"no block {label!r}" if fixed else f"no block or version {label!r}"
        if len(fns) == 1 and len(self.functions) > 1:
            msg += f" in function {fns[0]!r}"
        for f in fns:  # B4 when B has versions B1 to B3
            for b in self.blocks[f]:
                if label.startswith(b) and label != b and re.fullmatch(r"\.?\d+", label[len(b):]):
                    labels = [v["label"] for v in self.versions.values() if v["block"] == f"{f}/{b}"]
                    if labels:
                        return f"{msg}: block {b} has the versions {', '.join(labels)}"
        return f"{msg}; the blocks are {', '.join(names)}"

    def edge(self, src: str, dst: str, kind: str | None) -> set[str]:
        a, fn, _ = self.node(src)
        b, _, _ = self.node(dst, None if "/" in dst else fn)
        keys = [k for k in self.all_edges if k.split("->", 1)[0] in a and k.split("->", 1)[1].split(":")[0] in b]
        kinds = sorted({k.rsplit(":", 1)[1] for k in keys})
        if kind is not None:
            keys = [k for k in keys if k.rsplit(":", 1)[1] == kind]
        if not keys:
            outs = sorted({f"{self.versions[k.split('->', 1)[1].split(':')[0]]['label']} ({k.rsplit(':', 1)[1]})"
                           for k in self.all_edges if k.split("->", 1)[0] in a})
            what = f"no {kind} edge" if kind and kinds else "no edge"
            goes = f"; {src} goes to {', '.join(outs)}" if outs else f"; no edge leaves {src}"
            others = f" (its edges to {dst} are {', '.join(kinds)})" if kind and kinds else ""
            raise ComponentError(f"{what} {src}->{dst} in this drawing{others}{goes}")
        if kind is None and len(kinds) > 1:
            raise ComponentError(f"{src}->{dst} has edges of several kinds ({', '.join(kinds)}): write "
                                 + " or ".join(f"{src}->{dst}:{k}" for k in kinds))
        return set(keys)

    def part(self, name: str) -> Part:
        m = _EDGE.match(name)
        if m:
            src, dst = m.group(1), m.group(2)
            kind = None
            if ":" in dst:
                dst, _, written = dst.rpartition(":")
                if written not in KINDS:
                    raise ComponentError(f"unknown edge kind {written!r}; use goto, true, false, return, call, #t or #f")
                kind = KINDS[written]
            keys = self.edge(src.strip(), dst.strip(), kind)
            alts = ",".join(f'[data-key="{k}"]' for k in sorted(keys))
            selector = f".lt-bbv-edge:is({alts}):not(.lt-gone) > .lt-bbv-edge-mark"
            drawn = [bool(keys & e) for e in self.edges]
            warning = None
        else:
            if ":" in name:
                raise ComponentError(f"a kind (`:{name.rpartition(':')[2]}`) belongs to an edge, written A->B:kind")
            vids, _, warning = self.node(name.strip())
            alts = ",".join(f'[data-vid="{v}"]' for v in sorted(vids, key=int))
            selector = f".lt-bbv-node:is({alts}):not(.lt-gone)"
            drawn = [bool(vids & n) for n in self.nodes]
        if self.static or all(drawn):
            drawn = None
        return Part(selector, drawn, warning)


class _NamesParts:
    """The `part` hook of the versioning drawings (spec 8.2, 9.5)."""

    def part(self, result: RenderResult, name: str) -> Part:
        return _Drawing(result).part(name)


@register("bbv-anim")
class BbvAnim(_NamesParts, Component):
    Options = BbvAnimOptions
    body = "yaml"
    runtime = "bbv.js"

    def render(self, block, opts: BbvAnimOptions, ctx) -> RenderResult:
        prog = load_program(opts, ctx)
        show = _show(opts, SHOW)
        if opts.events is not None:
            bad = [e for e in opts.events if e not in EVENTS]
            if bad:
                raise ComponentError(f"events: unknown kind(s) {bad}; use {EVENTS}")
        try:
            trace = VersioningTrace(prog, algorithm=opts.algorithm, limit=opts.limit, heuristic=opts.heuristic,
                                    entry=opts.entry, limits=opts.limits, seed=ctx.seed, functions=opts.functions,
                                    events=opts.events, caption=opts.caption, until=opts.until,
                                    max_steps=opts.max_steps, granularity=opts.granularity,
                                    intervals=opts.intervals, thresholds=opts.thresholds, fixnum_bits=opts.fixnum_bits,
                                    vector_bounds=opts.vector_bounds, paths=opts.paths, fold=opts.fold)
        except (ProgramError, ValueError) as e:
            raise ComponentError(str(e)) from None
        if trace.spec.truncated:
            ctx.warn(f"bbv-anim: stopped after {opts.max_steps} steps without converging (raise max_steps or lower the limit)")
        box, frames = _layout(trace.tables, trace.frames, show, opts, prog, ctx,
                              panel=bool(opts.panel) and opts.panel_at != "below", call_edges=opts.call_edges)
        cfg = ctx.frames_config
        data = {"box": box, "tables": trace.tables, "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval),
                "show": show, "colors": _colors(trace.tables, ctx, opts.colors), "callEdges": opts.call_edges,
                "panel": opts.panel, "height": opts.height, "algorithm": opts.algorithm,
                "captions": any(f.get("caption") for f in frames)}
        zoom = _zoom(opts, trace.tables["versions"], trace.frames)
        if zoom:
            data["zoom"] = zoom
        return RenderResult(panel_root("lt-bbv-anim", opts.panel_at), data=data, positions=len(frames), meta=trace.meta)


@register("bbv-cfg")
class BbvCfg(_NamesParts, Component):
    Options = BbvCfgOptions
    body = "yaml"
    runtime = "bbv.js"

    def render(self, block, opts: BbvCfgOptions, ctx) -> RenderResult:
        prog = load_program(opts, ctx)
        show = _show(opts, ["label", "code"])
        visible = opts.functions or [f for f in prog.functions if not prog.functions[f].hidden]
        for f in visible:
            prog.function(f)
        tables = VersioningTrace.__new__(VersioningTrace)
        tables.program = prog
        tables.visible = visible
        program_table = tables._program_table()
        versions: dict[str, dict] = {}
        nodes: dict[str, dict] = {}
        edges: dict[str, dict] = {}
        ids: dict[str, str] = {}
        for fn in program_table["functions"]:
            for b in fn["blocks"]:
                vid = str(len(versions) + 1)
                ids[b["key"]] = vid
                versions[vid] = {"label": b["name"], "block": b["key"], "function": fn["name"], "name": b["name"],
                                 "context": [", ".join(b["params"])] if b["params"] else [], "code": b["code"], "after": []}
                nodes[vid] = {"state": "done"}
                if b is fn["blocks"][0]:
                    nodes[vid]["entry"] = True
        for fn in program_table["functions"]:
            for b in fn["blocks"]:
                for e in b["edges"]:
                    key = f"{ids[b['key']]}->{ids[fn['name'] + '/' + e['to']]}:{e['kind']}"
                    edges[key] = {"kind": e["kind"]}
        frame = {"nodes": nodes, "edges": edges, "caption": "", "panel": {}}
        box, frames = _layout({"program": program_table, "versions": versions}, [frame], show, opts, prog, ctx)
        highlight = None
        count = 1
        if ctx.leader is not None:
            count = ctx.leader.positions
            highlight = []
            for m in ctx.leader.meta or [{}] * count:
                if m.get("blocks") is not None:  # a path frame (spec 9.5): every block of the path
                    highlight.append([ids[k] for k in m["blocks"] if k in ids])
                    continue
                key = m.get("block")
                highlight.append(ids.get(key) if key else None)
        data = {"box": box, "tables": {"program": program_table, "versions": versions},
                "frames": frame_store(frames), "show": show, "colors": _colors({"program": program_table}, ctx, opts.colors),
                "callEdges": False, "panel": None, "height": opts.height, "highlight": highlight, "static": True,
                "captions": False}
        zoom = _zoom(opts, versions, [frame])
        if zoom:
            data["zoom"] = zoom
        return RenderResult('<div class="lt-bbv-anim lt-bbv-cfg"></div>', data=data, positions=count)


@register("abstract-interp-anim")
class AbstractInterpAnim(_NamesParts, Component):
    """Abstract interpretation over the fixed CFG of one function (thesis 1.1)."""

    Options = AbstractInterpOptions
    body = "yaml"
    runtime = "bbv.js"

    def render(self, block, opts: AbstractInterpOptions, ctx) -> RenderResult:
        prog = load_program(opts, ctx)
        show = _show(opts, SHOW)
        if opts.events is not None:
            bad = [e for e in opts.events if e not in ABSINT_EVENTS]
            if bad:
                raise ComponentError(f"events: unknown kind(s) {bad}; use {ABSINT_EVENTS}")
        if opts.functions and len(opts.functions) > 1:
            raise ComponentError("abstract-interp-anim analyses one function: give it as 'entry'")
        try:
            trace = AbstractTrace(prog, function=opts.entry or (opts.functions[0] if opts.functions else None),
                                  thresholds=opts.thresholds, narrowing=opts.narrowing, fixnum_bits=opts.fixnum_bits,
                                  events=opts.events, granularity=opts.granularity, history=opts.history,
                                  caption=opts.caption, until=opts.until, max_steps=opts.max_steps,
                                  vector_bounds=opts.vector_bounds)
        except (ProgramError, ValueError) as e:
            raise ComponentError(str(e)) from None
        if trace.ai.truncated:
            ctx.warn(f"abstract-interp-anim: no fixed point after {opts.max_steps} steps (use thresholds for widening)")
        panel = None
        if opts.panel is not None:
            panel = [k for k in opts.panel if k != "history"] + (opts.history or [] if "history" in opts.panel else [])
        box, frames = _layout(trace.tables, trace.frames, show, opts, prog, ctx,
                              panel=bool(panel) and opts.panel_at != "below")
        cfg = ctx.frames_config
        data = {"box": box, "tables": trace.tables, "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval),
                "show": show, "colors": _colors(trace.tables, ctx, opts.colors), "callEdges": False,
                "panel": panel, "height": opts.height, "algorithm": "absint", "static": True,
                "captions": any(f.get("caption") for f in frames)}
        zoom = _zoom(opts, trace.tables["versions"], trace.frames)
        if zoom:
            data["zoom"] = zoom
        return RenderResult(panel_root("lt-bbv-anim lt-bbv-absint", opts.panel_at), data=data, positions=len(frames),
                            meta=trace.meta)


# ---------------------------------------------------------------- bbv-merge (spec 9.5, "Merge heuristics")
class BbvMergeOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    contexts: Any = None  # a list of contexts (mappings variable: type), or {context, label, code}
    limit: int = 2
    heuristic: Literal["similarity", "arithmetic", "random"] = "similarity"
    placement: Literal["circle", "distance"] = "circle"
    program: str | None = None  # code for the looks: a block of a program, specialized per context
    source: str | None = None
    block: str | None = None
    name: str | None = None  # the label prefix without a program (default C)
    prims: dict | None = None
    show: list[str] | None = None
    colors: Literal["origin", "context", "none"] = "origin"
    edges: Literal["all", "pair", "none"] = "all"
    edge_width: Any = None  # [min, max] stroke widths in px, of the farthest and nearest pairs; default [1, 7]
    log_range: Any = "auto"  # or [lo, hi]: the logs of the distances are clamped to it
    edge_labels: bool = False
    distance_magnitude: bool = False  # show log10 of the distances (captions, panel, edge labels)
    intervals: bool = False
    thresholds: str | list[int | str] = "machine"
    fixnum_bits: int = 61
    vector_bounds: bool = True
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    caption: Literal["auto", "none"] = "auto"
    height: int | None = None
    clickable: bool = True
    clickable_show: list[str] | None = None
    fit_aspect: Any = None  # "W:H": the room the placement aims at, instead of the slide's content width


MERGE_PANEL = ["contexts", "limit", "merges", "distance"]
_NO_DISTANCE = ("edges", "edge_width", "log_range", "edge_labels", "distance_magnitude")


def _pair(value, what: str, default):
    """Two increasing numbers ``[a, b]`` (a YAML list, or its text in an attribute)."""
    import yaml

    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = yaml.safe_load(value)
        except yaml.YAMLError:
            pass
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value) and value[0] < value[1]):
        return float(value[0]), float(value[1])
    raise ComponentError(f"{what}: expected two increasing numbers [a, b], got {value!r}")


def _mix(colors: list[str]) -> str:
    rgb = [[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in colors]
    return "#" + "".join(f"{round(sum(x[k] for x in rgb) / len(rgb)):02x}" for k in range(3))


@register("bbv-merge")
class BbvMerge(Component):
    """A merge heuristic at work: contexts merged two by two until the limit holds (spec 9.5)."""

    Options = BbvMergeOptions
    body = "yaml"
    runtime = "bbv.js"

    def render(self, block, opts: BbvMergeOptions, ctx) -> RenderResult:
        from ..bbv.merging import MergeError, MergeRun

        if opts.contexts is None:
            raise ComponentError("contexts: list the contexts to merge, such as [{x: fx, y: fx}, {x: fl, y: fx}]")
        random = opts.heuristic == "random"
        if random:
            given = [k for k in _NO_DISTANCE if k in opts.model_fields_set]
            if given:
                raise ComponentError(f"{', '.join(given)}: the random heuristic has no distance to draw")
        edge_width = _pair(opts.edge_width, "edge_width", (1.0, 7.0))
        if edge_width[0] <= 0:
            raise ComponentError("edge_width: widths must be positive")
        log_range = None
        if not (isinstance(opts.log_range, str) and opts.log_range.strip() == "auto"):
            log_range = _pair(opts.log_range, "log_range", None)
        panel = opts.panel
        if panel is not None:
            allowed = MERGE_PANEL if not random else [k for k in MERGE_PANEL if k != "distance"]
            bad = [k for k in panel if k not in allowed]
            if bad:
                raise ComponentError(f"panel: unknown key(s) {bad}; use {allowed}"
                                     + (" (random has no distance)" if random and "distance" in bad else ""))
        prog = None
        if opts.program is not None or opts.source is not None:
            prog = load_program(opts, ctx)
        items = opts.contexts if isinstance(opts.contexts, list) else None
        has_code = prog is not None or any(isinstance(i, dict) and "code" in i and "context" in i for i in items or [])
        default = ["label", "context"] + (["code"] if has_code else [])
        show = _show(opts, default)
        if "code" in show and not has_code:
            raise ComponentError("show: code needs a program and its block (program or source, and block), "
                                 "or code given with the contexts")
        height = float(opts.height or DEFAULT_HEIGHT)
        if opts.fit_aspect is not None:
            room = (height * _aspect(opts.fit_aspect), height)
        else:
            room = _room(ctx, height, bool(panel) and opts.panel_at != "below")
        try:
            run = MergeRun(opts.contexts, limit=opts.limit, heuristic=opts.heuristic, seed=ctx.seed, program=prog,
                           block=opts.block, name=opts.name, intervals=opts.intervals, thresholds=opts.thresholds,
                           fixnum_bits=opts.fixnum_bits, vector_bounds=opts.vector_bounds, placement=opts.placement,
                           edges=opts.edges, edge_width=edge_width, log_range=log_range, show=show,
                           color_keys=opts.colors == "context", room=room, magnitude=opts.distance_magnitude)
        except (MergeError, ProgramError, ValueError) as e:
            raise ComponentError(str(e)) from None
        if len(run.initial) <= opts.limit:
            ctx.warn(f"bbv-merge: {len(run.initial)} contexts within a limit of {opts.limit}: nothing to merge")
        tables = run.tables()
        versions = tables["versions"]
        w, h = run.size
        box = {**run.box, "sizes": {vid: [w, h] for vid in versions}, "direction": "TB"}
        frames = run.frames
        if opts.caption == "none":
            frames = [{**f, "caption": ""} for f in frames]
        cfg = ctx.frames_config
        data = {"kind": "merge", "box": box, "tables": tables,
                "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval), "show": show,
                "colors": self._colors(run, prog, ctx, opts.colors), "callEdges": False, "panel": panel,
                "height": opts.height, "algorithm": "sbbv", "static": True, "edgeLabels": opts.edge_labels,
                "captions": opts.caption != "none"}
        zoom = _zoom(opts, versions, [])
        if zoom:
            zoom["sizes"] = {vid: [max(s[0], w), max(s[1], h)] for vid, s in zoom["sizes"].items()}
            data["zoom"] = zoom
        return RenderResult(panel_root("lt-bbv-anim lt-bbv-merge", opts.panel_at), data=data, positions=len(frames),
                            meta=run.meta)

    @staticmethod
    def _colors(run, prog, ctx, mode: str) -> dict[str, str]:
        if mode == "none":
            return {}
        series = list(ctx.palette.get("series") or []) or ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2",
                                                           "#b279a2", "#ff9da6", "#9d755d"]
        if mode == "origin":
            index = 0
            if prog is not None:  # the colour this block has in a bbv-anim or bbv-cfg of the program
                fns = [f for f in prog.functions.values() if not f.hidden] or list(prog.functions.values())
                keys = [b.key for f in fns for b in f.blocks.values()]
                index = keys.index(run.block.key) if run.block.key in keys else 0
            return {run.block.key: series[index % len(series)]}
        out: dict[str, str] = {}
        for i, vid in enumerate(run.initial):
            out[run.key_of(vid)] = series[i % len(series)]
        for vid in sorted(run.spec.by_id):
            if vid in run.parents:
                a, b = run.parents[vid]
                out[run.key_of(vid)] = _mix([out[run.key_of(a)], out[run.key_of(b)]])
        return out

    def part(self, result: RenderResult, name: str) -> Part:
        """``LABEL`` (a context) or ``A--B`` (the edge between two contexts)."""
        data = result.data or {}
        versions = data["tables"]["versions"]
        by_label = {v["label"]: vid for vid, v in versions.items()}
        frames = frames_of(data["frames"])

        def vid_of(label: str) -> str:
            label = label.strip()
            if label not in by_label:
                raise ComponentError(f"no context {label!r}; the contexts are {', '.join(by_label)}")
            return by_label[label]

        if "--" in name:
            a, _, b = name.partition("--")
            x, y = sorted((int(vid_of(a)), int(vid_of(b))))
            key = f"{x}--{y}"
            drawn = [key in (f.get("edges") or {}) for f in frames]
            if not any(drawn):
                raise ComponentError(f"no edge {name} is drawn: edges join contexts alive at the same step, "
                                     "and none are drawn with heuristic=random or edges=none (edges=pair draws "
                                     "only the pair picked)")
            selector = f'.lt-bbv-dist[data-key="{key}"]:not(.lt-gone) > .lt-bbv-edge-mark'
        else:
            vid = vid_of(name)
            drawn = [vid in (f.get("nodes") or {}) and f["nodes"][vid].get("mark") != "absorbed" for f in frames]
            selector = f'.lt-bbv-node[data-vid="{vid}"]:not(.lt-gone):not(.mk-absorbed)'
        return Part(selector, None if all(drawn) else drawn)
