"""Animated components: ``graph-anim`` and ``array-anim`` (spec sections 7.4 and 9)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..anim import ArrayTrace, GraphTrace, Trace
from .base import Component, ComponentError, RenderResult, register


class GraphAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    graph: str | None = None
    edges: list[str] | None = None
    directed: bool = False
    engine: str = "auto"
    rankdir: str = "LR"
    panel: list[str] | None = None
    edge_labels: bool | None = None
    height: int | None = None


class ArrayAnimOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    values: list | None = None
    panel: list[str] | None = None


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
        return RenderResult('<div class="lt-graph-anim"></div>', data=data, positions=len(trace),
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
        return RenderResult('<div class="lt-array-anim"></div>', data=data, positions=len(trace),
                            meta=trace.meta)
