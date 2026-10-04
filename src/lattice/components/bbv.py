"""Basic block versioning components: ``bbv-anim`` (an SBBV or ΛV run, one frame per event) and
``bbv-cfg`` (the source CFG of a program, static or following an animation). Spec 8.8 and 9.1."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..anim import frame_store
from ..bbv.ir import Program, ProgramError, parse
from ..bbv.layout import layout_frames
from ..bbv.trace import ABSINT_EVENTS, EVENTS, AbstractTrace, VersioningTrace
from .base import Component, ComponentError, RenderResult, register

SHOW = ["label", "context", "code"]


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
    caption: Literal["auto", "none"] = "auto"
    max_steps: int = 5000
    intervals: bool = False
    thresholds: str | list[int] = "machine"
    fixnum_bits: int = 61


class BbvCfgOptions(BbvCommonOptions):
    pass


class AbstractInterpOptions(BbvCommonOptions):
    entry: str | None = None  # the function analysed
    thresholds: str | list[int] = "machine"
    narrowing: bool = True
    fixnum_bits: int = 61
    events: list[str] | None = None
    granularity: Literal["block", "instruction"] = "block"
    until: int | None = None
    panel: list[str] | None = None
    history: list[str] | None = None
    caption: Literal["auto", "none"] = "auto"
    max_steps: int = 2000


_KNOWN = {"program", "source", "functions", "show", "colors", "direction", "height", "prims", "algorithm", "limit", "limits",
          "heuristic", "entry", "events", "granularity", "until", "call_edges", "panel", "caption", "max_steps", "wrap",
          "thresholds", "narrowing", "fixnum_bits", "history", "intervals"}


def load_program(opts: BbvCommonOptions, ctx) -> Program:
    from .animations import _extras

    if opts.source is not None and opts.program is not None:
        raise ComponentError("give either 'program' or 'source', not both")
    try:
        if opts.source is not None:
            prog = parse(opts.source)
        elif opts.program is None:
            raise ComponentError("'program' (a .bbv file or file.py:function) or 'source' is required")
        elif ":" in opts.program:
            extras = {k: v for k, v in _extras(opts).items() if k not in _KNOWN}
            result = ctx.call(opts.program, **extras)
            if isinstance(result, str):
                prog = parse(result)
            elif isinstance(result, Program):
                prog = result
            else:
                raise ComponentError(f"{opts.program} must return a Program or its text")
        else:
            prog = parse(ctx.path(opts.program).read_text(encoding="utf-8"))
        if opts.prims:
            prog.add_prims(opts.prims)
            prog.finalize()
    except ProgramError as e:
        raise ComponentError(f"program: {e}") from None
    return prog


def _show(opts: BbvCommonOptions, default: list[str]) -> list[str]:
    show = opts.show if opts.show is not None else default
    bad = [s for s in show if s not in SHOW]
    if bad:
        raise ComponentError(f"show: unknown item(s) {bad}; use {SHOW}")
    return show


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


@register("bbv-anim")
class BbvAnim(Component):
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
                                    intervals=opts.intervals, thresholds=opts.thresholds, fixnum_bits=opts.fixnum_bits)
        except (ProgramError, ValueError) as e:
            raise ComponentError(str(e)) from None
        if trace.spec.truncated:
            ctx.warn(f"bbv-anim: stopped after {opts.max_steps} steps without converging (raise max_steps or lower the limit)")
        box, positions = layout_frames(trace.tables, trace.frames, show, _layout_fn(ctx), opts.direction, opts.wrap)
        frames = [{**f, "pos": p} for f, p in zip(trace.frames, positions)]
        cfg = ctx.frames_config
        data = {"box": box, "tables": trace.tables, "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval),
                "show": show, "colors": _colors(trace.tables, ctx, opts.colors), "callEdges": opts.call_edges,
                "panel": opts.panel, "height": opts.height, "algorithm": opts.algorithm}
        return RenderResult('<div class="lt-bbv-anim"></div>', data=data, positions=len(frames), meta=trace.meta)


@register("bbv-cfg")
class BbvCfg(Component):
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
        box, positions = layout_frames({"program": program_table, "versions": versions}, [frame], show, _layout_fn(ctx),
                                       opts.direction, opts.wrap)
        frames = [{**frame, "pos": positions[0]}]
        highlight = None
        count = 1
        if ctx.leader is not None:
            count = ctx.leader.positions
            highlight = []
            for m in ctx.leader.meta or [{}] * count:
                key = m.get("block")
                highlight.append(ids.get(key) if key else None)
        data = {"box": box, "tables": {"program": program_table, "versions": versions},
                "frames": frame_store(frames), "show": show, "colors": _colors({"program": program_table}, ctx, opts.colors),
                "callEdges": False, "panel": None, "height": opts.height, "highlight": highlight, "static": True}
        return RenderResult('<div class="lt-bbv-anim lt-bbv-cfg"></div>', data=data, positions=count)


@register("abstract-interp-anim")
class AbstractInterpAnim(Component):
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
                                  caption=opts.caption, until=opts.until, max_steps=opts.max_steps)
        except (ProgramError, ValueError) as e:
            raise ComponentError(str(e)) from None
        if trace.ai.truncated:
            ctx.warn(f"abstract-interp-anim: no fixed point after {opts.max_steps} steps (use thresholds for widening)")
        box, positions = layout_frames(trace.tables, trace.frames, show, _layout_fn(ctx), opts.direction, opts.wrap)
        frames = [{**f, "pos": p} for f, p in zip(trace.frames, positions)]
        cfg = ctx.frames_config
        panel = None
        if opts.panel is not None:
            panel = [k for k in opts.panel if k != "history"] + (opts.history or [] if "history" in opts.panel else [])
        data = {"box": box, "tables": trace.tables, "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval),
                "show": show, "colors": _colors(trace.tables, ctx, opts.colors), "callEdges": False,
                "panel": panel, "height": opts.height, "algorithm": "absint", "static": True}
        return RenderResult('<div class="lt-bbv-anim lt-bbv-absint"></div>', data=data, positions=len(frames),
                            meta=trace.meta)
