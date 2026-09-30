"""Local plugins for this deck. Lattice imports this file automatically."""
import ast
import html
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lattice import Component, ComponentError, RenderResult, Trace, register


class TruthTableOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbols: bool = True  # show 1/0 instead of True/False


@register("truth-table")
class TruthTable(Component):
    """A static component: one boolean expression per line of the body."""
    Options = TruthTableOptions
    body = "text"
    css = [str(Path(__file__).with_name("plugins.css"))]

    def render(self, block, opts, ctx):
        exprs = [line.strip() for line in block.body.splitlines() if line.strip()]
        if not exprs:
            raise ComponentError("write one boolean expression per line")
        trees = [ast.parse(e, mode="eval") for e in exprs]
        names = sorted({n.id for t in trees for n in ast.walk(t) if isinstance(n, ast.Name)})
        cell = (lambda v: "1" if v else "0") if opts.symbols else str
        head = "".join(f'<th class="{"wrap" if len(x) > 14 else ""}">{html.escape(x)}</th>' for x in names + exprs)
        rows = []
        for i in range(2 ** len(names)):
            env = {n: bool(i >> (len(names) - 1 - k) & 1) for k, n in enumerate(names)}
            vals = [env[n] for n in names]
            vals += [eval(compile(t, "<expr>", "eval"), {"__builtins__": {}}, env) for t in trees]
            rows.append("".join(f'<td class="{"t" if v else "f"}">{cell(v)}</td>' for v in vals))
        body = "".join(f"<tr>{r}</tr>" for r in rows)
        return RenderResult(f'<table class="truth-table"><tr>{head}</tr>{body}</table>')


class CallStackOptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str


@register("call-stack")
class CallStack(Component):
    """An animated component with its own JavaScript runtime."""
    Options = CallStackOptions
    body = "yaml"
    runtime = str(Path(__file__).with_name("call_stack.js"))
    css = [str(Path(__file__).with_name("plugins.css"))]

    def render(self, block, opts, ctx):
        trace = ctx.call(opts.source, **(opts.model_extra or {}))
        if not isinstance(trace, Trace) or not len(trace):
            raise ComponentError(f"{opts.source} must return a non-empty Trace")
        store = trace.frame_store(ctx.frames_config.max_full_bytes, ctx.frames_config.keyframe_interval)
        return RenderResult('<div class="call-stack"></div>', data={"frames": store},
                            positions=len(trace), meta=trace.meta)
