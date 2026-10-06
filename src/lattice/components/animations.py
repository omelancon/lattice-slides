"""Animated components: ``graph-anim``, ``array-anim``, ``tree-anim`` and ``grid-anim`` (spec sections 8.8 and 9)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..anim import ArrayTrace, GraphTrace, GridTrace, Trace, TreeTrace, frame_store
from .base import Component, ComponentError, RenderResult, register

# Where the variable panel sits (spec 8.8): `auto` beside the drawing, or under it in a component narrower
# than 760 px (a container query of lattice.css); `right` and `below` whatever the width.
PanelAt = Literal["auto", "right", "below"]


def panel_root(cls: str, panel_at: str) -> str:
    """The root element of an animation component; `auto` adds nothing, so that decks render as before."""
    extra = "" if panel_at == "auto" else f" lt-panel-{panel_at}"
    return f'<div class="{cls}{extra}"></div>'


class GraphAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    graph: str | None = None
    edges: list[str] | None = None
    directed: bool = False
    engine: str = "auto"
    rankdir: str = "LR"
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    edge_labels: bool | None = None
    height: int | None = None


class ArrayAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    values: list | None = None
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"


class TreeAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    values: list | None = None
    layout: Literal["auto", "binary", "tidy"] = "auto"
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    height: int | None = None


class GridAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    values: list | None = None
    panel: list[str] | None = None
    panel_at: PanelAt = "auto"
    cell: int = 48
    height: int | None = None


def _extras(opts) -> dict:
    """Extra options become keyword arguments; attribute strings are read as YAML scalars."""
    import yaml

    out = {}
    for k, v in (opts.model_extra or {}).items():
        if isinstance(v, str):
            try:
                v = yaml.safe_load(v)
            except yaml.YAMLError:
                pass
        out[k] = v
    return out


def _store(trace: Trace, ctx) -> dict:
    cfg = ctx.frames_config
    return trace.frame_store(cfg.max_full_bytes, cfg.keyframe_interval)


@register("graph-anim")
class GraphAnim(Component):
    Options = GraphAnimOptions
    body = "yaml"
    runtime = "graph-anim.js"

    def render(self, block, opts: GraphAnimOptions, ctx) -> RenderResult:
        from ..graphs import graph_from_edges, layout

        import networkx as nx

        extras = _extras(opts)
        g = None
        if opts.graph:
            g = ctx.load_graph(opts.graph)
        elif opts.edges:
            g = graph_from_edges(opts.edges, opts.directed)
        trace = ctx.call(opts.source, g, **extras) if g is not None else ctx.call(opts.source, **extras)
        if not isinstance(trace, GraphTrace):
            raise ComponentError(f"{opts.source} must return a GraphTrace")
        if not len(trace):
            raise ComponentError(f"{opts.source} produced no frames")
        directed = g.is_directed() if g is not None else trace.directed
        full = (g.copy() if g is not None else (nx.DiGraph() if directed else nx.Graph()))
        ns, es = trace.elements()
        full.add_nodes_from(ns)
        sep = "->" if directed else "--"
        for key in es:
            if sep in key:
                u, v = key.split(sep, 1)
                if not full.has_edge(u, v):
                    full.add_edge(u, v)
        lay = layout(full, engine=opts.engine, seed=ctx.seed, rankdir=opts.rankdir,
                     edge_labels=opts.edge_labels)
        data = {"layout": lay, "frames": _store(trace, ctx), "panel": opts.panel, "height": opts.height}
        return RenderResult(panel_root("lt-graph-anim", opts.panel_at), data=data, positions=len(trace),
                            meta=trace.meta)


@register("array-anim")
class ArrayAnim(Component):
    Options = ArrayAnimOptions
    body = "yaml"
    runtime = "array-anim.js"

    def render(self, block, opts: ArrayAnimOptions, ctx) -> RenderResult:
        extras = _extras(opts)
        if opts.values is not None:
            trace = ctx.call(opts.source, list(opts.values), **extras)
        else:
            trace = ctx.call(opts.source, **extras)
        if not isinstance(trace, ArrayTrace):
            raise ComponentError(f"{opts.source} must return an ArrayTrace")
        if not len(trace):
            raise ComponentError(f"{opts.source} produced no frames")
        data = {"frames": _store(trace, ctx), "panel": opts.panel}
        return RenderResult(panel_root("lt-array-anim", opts.panel_at), data=data, positions=len(trace),
                            meta=trace.meta)


def _call(opts, ctx):
    extras = _extras(opts)
    if opts.values is not None:
        return ctx.call(opts.source, list(opts.values), **extras)
    return ctx.call(opts.source, **extras)


@register("tree-anim")
class TreeAnim(Component):
    Options = TreeAnimOptions
    body = "yaml"
    runtime = "tree-anim.js"

    def render(self, block, opts: TreeAnimOptions, ctx) -> RenderResult:
        from ..graphs import tree_layouts

        trace = _call(opts, ctx)
        if not isinstance(trace, TreeTrace):
            raise ComponentError(f"{opts.source} must return a TreeTrace")
        if not len(trace):
            raise ComponentError(f"{opts.source} produced no frames")
        size, positions = tree_layouts([f.get("tree", {}) for f in trace.frames], opts.layout)
        frames = [{**f, "pos": p} for f, p in zip(trace.frames, positions)]
        cfg = ctx.frames_config
        data = {"size": size, "frames": frame_store(frames, cfg.max_full_bytes, cfg.keyframe_interval),
                "panel": opts.panel, "height": opts.height}
        return RenderResult(panel_root("lt-tree-anim", opts.panel_at), data=data, positions=len(trace), meta=trace.meta)


@register("grid-anim")
class GridAnim(Component):
    Options = GridAnimOptions
    body = "yaml"
    runtime = "grid-anim.js"

    def render(self, block, opts: GridAnimOptions, ctx) -> RenderResult:
        trace = _call(opts, ctx)
        if not isinstance(trace, GridTrace):
            raise ComponentError(f"{opts.source} must return a GridTrace")
        if not len(trace):
            raise ComponentError(f"{opts.source} produced no frames")
        rows = max(len(f.get("values", [])) for f in trace.frames)
        cols = max((len(r) for f in trace.frames for r in f.get("values", [])), default=0)
        if not rows or not cols:
            raise ComponentError(f"{opts.source} produced an empty grid")
        dims = {"rows": rows, "cols": cols, "cell": opts.cell,
                "rowHead": any("rows" in f for f in trace.frames),
                "colHead": any("cols" in f for f in trace.frames)}
        data = {"dims": dims, "frames": _store(trace, ctx), "panel": opts.panel, "height": opts.height}
        return RenderResult(panel_root("lt-grid-anim", opts.panel_at), data=data, positions=len(trace), meta=trace.meta)
