"""Static visual components: ``plot`` (matplotlib), ``dot`` (Graphviz) and ``math``."""
from __future__ import annotations

import csv
import html
import inspect
import io
import json
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .base import Component, ComponentError, RenderResult, register


class PlotOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["matplotlib", "vega", "plotly"] = "matplotlib"
    source: str | None = None
    spec: dict | None = None  # raw Vega-Lite spec or Plotly figure ({data, layout})
    data: str | None = None
    kind: Literal["line", "bar", "scatter"] = "line"
    x: str | None = None
    y: str | list[str] | None = None
    group: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    title: str | None = None
    logx: bool = False
    logy: bool = False
    width: float = 9.0   # inches (96 px per inch for vega and plotly)
    height: float = 4.2
    legend: bool = True


FONT_STACK = ["Avenir Next", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def _convert(v):
    try:
        return float(v) if any(c in v for c in ".eE") else int(v)
    except (ValueError, TypeError):
        return v


def _read_rows(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: _convert(v) for k, v in row.items()} for row in csv.DictReader(f)]


def _read_csv(path) -> dict[str, list]:
    cols: dict[str, list] = {}
    for row in _read_rows(path):
        for k, v in row.items():
            cols.setdefault(k, []).append(v)
    return cols


def _ys(opts: PlotOptions) -> list[str]:
    return [opts.y] if isinstance(opts.y, str) else list(opts.y or [])


def _series(opts: PlotOptions, cols: dict[str, list]) -> list[tuple[str, list, list]]:
    """(name, xs, ys) for each series described by the shorthand options."""
    ys = _ys(opts)
    for c in [opts.x, *ys, *([opts.group] if opts.group else [])]:
        if c not in cols:
            raise ComponentError(f"column {c!r} not found in {opts.data}")
    if opts.group:
        out = []
        for gname in dict.fromkeys(cols[opts.group]):
            idx = [i for i, g in enumerate(cols[opts.group]) if g == gname]
            out.append((str(gname), [cols[opts.x][i] for i in idx], [cols[ys[0]][i] for i in idx]))
        return out
    return [(y, cols[opts.x], cols[y]) for y in ys]


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _call_source(opts: PlotOptions, ctx, **available):
    """Call ``source`` with the keyword arguments its signature asks for."""
    from .base import import_path

    fn_file, _, fn_name = opts.source.rpartition(":")
    if not fn_file:
        raise ComponentError("source must be 'file.py:function'")
    fn = getattr(import_path(ctx.path(fn_file)), fn_name, None)
    if fn is None:
        raise ComponentError(f"{fn_file} has no function {fn_name!r}")
    params = inspect.signature(fn).parameters
    return fn(**{k: v for k, v in available.items() if k in params})


@register("plot")
class Plot(Component):
    Options = PlotOptions
    body = "yaml"
    runtime = "plot.js"

    def render(self, block, opts: PlotOptions, ctx) -> RenderResult:
        if opts.backend == "matplotlib":
            return self._matplotlib(opts, ctx)
        spec = self._vega(opts, ctx) if opts.backend == "vega" else self._plotly(opts, ctx)
        return RenderResult(f'<div class="lt-plot lt-plot-{opts.backend}"></div>',
                            data={"backend": opts.backend, "spec": spec}, requires=[opts.backend])

    # ---------------------------------------------------------------- vega-lite
    def _vega(self, opts: PlotOptions, ctx) -> dict:
        pal = ctx.palette
        rows = _read_rows(ctx.path(opts.data)) if opts.data else None
        if opts.source:
            spec = _call_source(opts, ctx, data=rows)
            if not isinstance(spec, dict):
                raise ComponentError("a vega plot source must return a Vega-Lite spec (dict)")
        elif opts.spec is not None:
            spec = dict(opts.spec)
        else:
            if not (rows is not None and opts.x and opts.y):
                raise ComponentError("plot needs 'spec', 'source', or 'data', 'x' and 'y'")
            spec = self._vega_shorthand(opts, rows)
        if rows is not None and "data" not in spec:
            spec["data"] = {"values": rows}
        spec.setdefault("width", round(opts.width * 96))
        spec.setdefault("height", round(opts.height * 96))
        if opts.title and "title" not in spec:
            spec["title"] = opts.title
        theme = {
            "background": "transparent", "font": ", ".join(FONT_STACK),
            "axis": {"labelColor": pal["muted"], "titleColor": pal["ink"], "gridColor": pal["grid"],
                     "domainColor": pal["muted"], "tickColor": pal["muted"], "labelFontSize": 16,
                     "titleFontSize": 17, "titleFontWeight": 500, "titlePadding": 10},
            "legend": {"labelColor": pal["ink"], "titleColor": pal["muted"], "labelFontSize": 16,
                       "symbolSize": 120},
            "title": {"color": pal["ink"], "fontSize": 18},
            "range": {"category": pal["series"]}, "view": {"stroke": None},
            "line": {"strokeWidth": 2.5}, "point": {"size": 60},
        }
        spec["config"] = _deep_merge(theme, spec.get("config", {}))
        spec.setdefault("$schema", "https://vega.github.io/schema/vega-lite/v5.json")
        return spec

    def _vega_shorthand(self, opts: PlotOptions, rows: list[dict]) -> dict:
        ys = _ys(opts)
        numeric_x = all(isinstance(r.get(opts.x), (int, float)) for r in rows)
        mark = {"line": {"type": "line", "point": True}, "bar": {"type": "bar"},
                "scatter": {"type": "point", "filled": True}}[opts.kind]
        x = {"field": opts.x, "type": "quantitative" if numeric_x and opts.kind != "bar" else "ordinal",
             "title": opts.xlabel if opts.xlabel is not None else opts.x}
        if opts.logx:
            x["scale"] = {"type": "log"}
        y_title = opts.ylabel if opts.ylabel is not None else ", ".join(ys)
        spec: dict = {"mark": mark, "encoding": {"x": x}}
        if len(ys) > 1:
            spec["transform"] = [{"fold": ys, "as": ["series", "value"]}]
            y = {"field": "value", "type": "quantitative", "title": y_title}
            color = {"field": "series", "type": "nominal", "title": None}
        else:
            y = {"field": ys[0], "type": "quantitative", "title": y_title}
            color = {"field": opts.group, "type": "nominal", "title": None} if opts.group else None
        if opts.logy:
            y["scale"] = {"type": "log"}
        spec["encoding"]["y"] = y
        if color:
            if not opts.legend:
                color["legend"] = None
            spec["encoding"]["color"] = color
            if opts.kind == "bar":
                spec["encoding"]["xOffset"] = {"field": color["field"]}
        spec["encoding"]["tooltip"] = [{"field": opts.x}] + ([{"field": f} for f in ys] if len(ys) == 1 else
                                                             [{"field": "series"}, {"field": "value"}])
        if opts.group:
            spec["encoding"]["tooltip"].append({"field": opts.group})
        return spec

    # ---------------------------------------------------------------- plotly
    def _plotly(self, opts: PlotOptions, ctx) -> dict:
        pal = ctx.palette
        cols = _read_csv(ctx.path(opts.data)) if opts.data else None
        if opts.source:
            fig = _call_source(opts, ctx, data=cols)
            if hasattr(fig, "to_json"):
                fig = json.loads(fig.to_json())
            if not isinstance(fig, dict):
                raise ComponentError("a plotly plot source must return a figure or a dict {data, layout}")
        elif opts.spec is not None:
            fig = dict(opts.spec)
        else:
            if not (cols is not None and opts.x and opts.y):
                raise ComponentError("plot needs 'spec', 'source', or 'data', 'x' and 'y'")
            traces = []
            for name, xs, ys in _series(opts, cols):
                if opts.kind == "bar":
                    traces.append({"type": "bar", "name": name, "x": xs, "y": ys})
                else:
                    traces.append({"type": "scatter", "name": name, "x": xs, "y": ys,
                                   "mode": "lines+markers" if opts.kind == "line" else "markers"})
            fig = {"data": traces, "layout": {
                "xaxis": {"title": {"text": opts.xlabel if opts.xlabel is not None else opts.x}},
                "yaxis": {"title": {"text": opts.ylabel if opts.ylabel is not None else ", ".join(_ys(opts))}},
                "showlegend": opts.legend and len(traces) > 1}}
            if opts.kind == "bar":
                fig["layout"]["xaxis"]["type"] = "category"
            if opts.logx:
                fig["layout"]["xaxis"]["type"] = "log"
            if opts.logy:
                fig["layout"]["yaxis"]["type"] = "log"
        axis = {"gridcolor": pal["grid"], "zerolinecolor": pal["grid"], "linecolor": pal["muted"],
                "tickfont": {"color": pal["muted"]}}
        theme = {
            "width": round(opts.width * 96), "height": round(opts.height * 96),
            "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
            "font": {"family": ", ".join(FONT_STACK), "color": pal["ink"], "size": 15},
            "colorway": pal["series"], "xaxis": axis, "yaxis": axis,
            "margin": {"l": 70, "r": 20, "t": 50 if opts.title else 16, "b": 60},
            "legend": {"bgcolor": "rgba(0,0,0,0)"},
        }
        if opts.title:
            theme["title"] = {"text": opts.title}
        fig["layout"] = _deep_merge(theme, fig.get("layout", {}))
        fig.setdefault("data", [])
        return fig

    # ---------------------------------------------------------------- matplotlib
    def _matplotlib(self, opts: PlotOptions, ctx) -> RenderResult:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as e:  # pragma: no cover
            raise ComponentError("matplotlib is required: pip install 'lattice-slides[plot]'") from e
        pal = ctx.palette
        rc = {
            "svg.fonttype": "none", "font.family": "sans-serif", "font.sans-serif": FONT_STACK,
            "font.size": 15, "text.color": pal["ink"], "axes.labelcolor": pal["ink"],
            "axes.edgecolor": pal["muted"], "xtick.color": pal["muted"], "ytick.color": pal["muted"],
            "axes.prop_cycle": matplotlib.cycler(color=pal["series"]), "figure.facecolor": "none",
            "axes.facecolor": "none", "savefig.transparent": True, "axes.spines.top": False,
            "axes.spines.right": False, "axes.grid": True, "grid.color": pal["grid"], "grid.linewidth": 0.8,
            "legend.frameon": False, "lines.linewidth": 2.4, "lines.markersize": 6,
        }
        with matplotlib.rc_context(rc):
            if opts.source:
                from .base import import_path

                fn_file, _, fn_name = opts.source.rpartition(":")
                fn = getattr(import_path(ctx.path(fn_file)), fn_name, None) if fn_file else None
                if fn is None:
                    raise ComponentError(f"cannot find {opts.source!r} (expected 'file.py:function')")
                params = inspect.signature(fn).parameters
                if "ax" in params:
                    fig, ax = plt.subplots(figsize=(opts.width, opts.height))
                    kwargs = {"ax": ax}
                    if opts.data and "data" in params:
                        kwargs["data"] = _read_csv(ctx.path(opts.data))
                    fn(**kwargs)
                else:
                    fig = fn()
                if fig is None or not hasattr(fig, "savefig"):
                    raise ComponentError("plot source must return a Figure or accept an 'ax' argument")
            else:
                if not (opts.data and opts.x and opts.y):
                    raise ComponentError("plot needs either 'source' or 'data', 'x' and 'y'")
                fig = self._mpl_from_spec(plt, opts, _read_csv(ctx.path(opts.data)))
            buf = io.StringIO()
            fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.05)
            plt.close(fig)
        svg = buf.getvalue()
        svg = svg[svg.find("<svg"):]
        svg = re.sub(r'\swidth="[^"]*"', "", svg, count=1)
        svg = re.sub(r'\sheight="[^"]*"', "", svg, count=1)
        svg = re.sub(r"<metadata>.*?</metadata>", "", svg, flags=re.S)
        return RenderResult(f'<div class="lt-plot">{svg}</div>')

    def _mpl_from_spec(self, plt, opts: PlotOptions, cols):
        fig, ax = plt.subplots(figsize=(opts.width, opts.height))
        series = _series(opts, cols)
        n = len(series)
        for k, (name, xs, yv) in enumerate(series):
            if opts.kind == "line":
                ax.plot(xs, yv, marker="o", label=name)
            elif opts.kind == "scatter":
                ax.scatter(xs, yv, label=name)
            else:
                width = 0.8 / n
                pos = [i + (k - (n - 1) / 2) * width for i in range(len(xs))]
                ax.bar(pos, yv, width=width, label=name)
                ax.set_xticks(range(len(xs)), [str(x) for x in xs])
        if opts.logx:
            ax.set_xscale("log")
        if opts.logy:
            ax.set_yscale("log")
        ax.set_xlabel(opts.xlabel if opts.xlabel is not None else opts.x)
        ax.set_ylabel(opts.ylabel if opts.ylabel is not None else ", ".join(_ys(opts)))
        if opts.title:
            ax.set_title(opts.title)
        if opts.legend and n > 1:
            ax.legend()
        return fig


class DotOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Literal["dot", "neato", "fdp", "circo", "twopi", "sfdp"] = "dot"


@register("dot")
class Dot(Component):
    Options = DotOptions
    body = "text"

    def render(self, block, opts: DotOptions, ctx) -> RenderResult:
        from ..graphs import dot_to_svg

        return RenderResult(f'<div class="lt-dot">{dot_to_svg(block.body, opts.engine)}</div>')


@register("math")
class MathBlock(Component):
    body = "text"

    def render(self, block, opts, ctx) -> RenderResult:
        tex = html.escape(block.body.strip())
        return RenderResult(f'<div class="lt-math lt-math-block" data-display="1">{tex}</div>')


# ---------------------------------------------------------------- arrow
ANCHOR_ANGLES = {"right": 0.0, "top": 90.0, "left": 180.0, "bottom": 270.0}


def _anchor(v):
    """A side, `center`, `bullet`, or an angle in degrees (a number, or a string holding one)."""
    if isinstance(v, str) and (v in ANCHOR_ANGLES or v in ("center", "bullet")):
        return v
    try:
        if isinstance(v, bool):
            raise ValueError
        return float(v)
    except (TypeError, ValueError):
        raise ValueError("an anchor is left, right, top, bottom, center, bullet or an angle in degrees") from None


Anchor = Annotated[Union[str, float], BeforeValidator(_anchor)]


class ArrowStep(BaseModel):
    """One target of an `arrow` with `steps:`; unset fields fall back to the block's options."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    to: str
    from_: str | None = Field(None, alias="from")
    angle: float | None = None
    length: float | None = None
    label: str | None = None
    from_anchor: Anchor | None = None
    to_anchor: Anchor | None = None


class ArrowOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    to: str | None = None          # element id, or a CSS selector, resolved inside the slide
    from_: str | None = Field(None, alias="from")   # another element: the arrow runs between the two
    angle: float | None = None     # degrees, from the target toward the tail, counterclockwise; 0 is right
    length: float = 120            # slide pixels, from the target's edge to the tail (ignored with `from`)
    label: str | None = None       # text at the tail
    color: str | None = None       # a CSS color, or a theme token: accent, detour, muted, ink
    width: float = 4               # stroke width
    curve: float = 0               # bend, as a fraction of the arrow's length; 0 is straight
    from_anchor: Anchor | None = None  # where the arrow leaves `from`: a side, center, or degrees
    to_anchor: Anchor | None = None    # where it enters `to`
    steps: list[ArrowStep | str | None] | None = None   # several targets, one per position; null: no arrow


ARROW_DEFAULT_ANGLE = 315.0
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
# an item of a list: `facts[2]`, `facts[-1]`, `facts[2][1]` (spec 8.9); not a CSS selector
_ITEM_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)((?:\[-?\d+\])+)$")
_THEME_COLORS = {"accent", "detour", "muted", "ink"}


def anchor_value(a: Anchor | None) -> float | str | None:
    """A side becomes its angle (counterclockwise, 0 is right); `center` and `bullet` stay; degrees are
    taken mod 360."""
    if a is None or a in ("center", "bullet"):
        return a
    if isinstance(a, str):
        return ANCHOR_ANGLES[a]
    return float(a) % 360.0


@register("arrow")
class Arrow(Component):
    """An arrow drawn over the slide, pointing at an element (spec 8.9). Geometry is measured in the browser."""
    Options = ArrowOptions
    body = "yaml"
    runtime = "arrow.js"

    def render(self, block, opts: ArrowOptions, ctx) -> RenderResult:
        if opts.to is None and not opts.steps:
            raise ComponentError("arrow needs `to` (an element id or selector) or a `steps:` list")
        if opts.to is not None and opts.steps:
            raise ComponentError("arrow: give either `to` or `steps`, not both")
        entries = opts.steps or [ArrowStep(to=opts.to)]
        if all(e is None for e in entries):
            raise ComponentError("arrow: every step is null; give at least one target")
        steps = []
        for i, e in enumerate(entries):
            if e is None:  # no arrow at this position (spec 8.9)
                steps.append(None)
                continue
            if isinstance(e, str):
                e = ArrowStep(to=e)
            frm = (e.from_ or None) if e.from_ is not None else opts.from_  # "" drops the block's `from`
            if e.from_anchor is not None and frm is None:
                raise ComponentError(f"arrow: step {i + 1} has `from_anchor` but no `from`")
            to, to_item = split_item(e.to, i)
            frm, from_item = split_item(frm, i) if frm is not None else (None, None)
            step = {
                "to": to,
                "from": frm,
                "angle": e.angle if e.angle is not None else opts.angle,
                "length": e.length if e.length is not None else opts.length,
                "label": e.label if e.label is not None else opts.label,
            }
            fa = anchor_value(e.from_anchor if e.from_anchor is not None else opts.from_anchor)
            ta = anchor_value(e.to_anchor if e.to_anchor is not None else opts.to_anchor)
            if fa is not None and frm is not None:  # the block's from_anchor applies to steps with a `from`
                step["from_anchor"] = fa
            if ta is not None:
                step["to_anchor"] = ta
            if to_item:
                step["to_item"] = to_item
            if from_item:
                step["from_item"] = from_item
            steps.append(step)
        if opts.from_anchor is not None and not any(s and s["from"] for s in steps):
            raise ComponentError("arrow: `from_anchor` needs `from`")
        for s in steps:
            if s is not None and s["from"] is None and s["angle"] is None:
                ta = s.get("to_anchor")
                # a side gives the direction, and `bullet` the left one
                s["angle"] = ta if isinstance(ta, float) else 180.0 if ta == "bullet" else ARROW_DEFAULT_ANGLE
        color = opts.color
        if color in _THEME_COLORS:
            color = f"var(--lt-{color})"
        data = {"steps": steps, "color": color, "width": opts.width, "curve": opts.curve}
        return RenderResult('<div class="lt-arrow-box" aria-hidden="true"></div>', data=data, positions=len(steps))


def split_item(ref: str, i: int) -> tuple[str, list[int] | None]:
    """`facts[2][1]` gives ("facts", [2, 1]); any other reference is returned as it is (spec 8.9)."""
    m = _ITEM_RE.match(ref)
    if not m:
        return ref, None
    path = [int(n) for n in re.findall(r"-?\d+", m.group(2))]
    if 0 in path:
        raise ComponentError(f"arrow: step {i + 1}: {ref!r}: list items are counted from 1 (or from -1, the last)")
    return m.group(1), path


def arrow_targets(data: dict) -> list[str]:
    """Bare element ids an arrow refers to (for the build-time check of render.py); the list of an item
    path is checked with the path (`arrow_ends`)."""
    out = []
    for s in data.get("steps", []):
        if s is None:
            continue
        for end in ("to", "from"):
            ref = s.get(end)
            if ref and _ID_RE.match(ref) and not s.get(f"{end}_item"):
                out.append(ref)
    return out


def arrow_ends(data: dict) -> list[tuple[int, str, str, list[int] | None, bool]]:
    """The ends the build checks against the slide's lists (LT063): (step, end, reference, item path,
    whether its anchor is `bullet`), for every end written as an item path or anchored at a bullet."""
    out = []
    for i, s in enumerate(data.get("steps", [])):
        if s is None:
            continue
        for end in ("to", "from"):
            ref, path = s.get(end), s.get(f"{end}_item")
            bullet = s.get(f"{end}_anchor") == "bullet"
            if ref and (path or bullet):
                out.append((i, end, ref, path, bullet))
    return out
