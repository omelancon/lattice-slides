"""Local plugins of the manual. Lattice imports a `lattice_plugins.py` next to the root file."""
import html
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lattice import Component, ComponentError, RenderResult, Trace, register

HERE = Path(__file__).parent


class ChecklistOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None


@register("checklist")
class Checklist(Component):
    """A static component: one item per line, `[x]` marks a done item. Build-time HTML only."""

    Options = ChecklistOptions
    body = "text"
    css = [str(HERE / "plugins.css")]

    def render(self, block, opts, ctx):
        items = [line.strip() for line in block.body.splitlines() if line.strip()]
        if not items:
            raise ComponentError("write one item per line")
        rows = []
        for item in items:
            done = item.startswith("[x]")
            text = item[3:].strip() if item[:3] in ("[x]", "[ ]") else item
            rows.append(f'<li class="{"done" if done else ""}">{html.escape(text)}</li>')
        head = f"<h3>{html.escape(opts.title)}</h3>" if opts.title else ""
        return RenderResult(f'<div class="checklist">{head}<ul>{"".join(rows)}</ul></div>')


class CallStackOptions(BaseModel):
    model_config = ConfigDict(extra="allow")  # extra options go to the trace function
    source: str


@register("stack-anim")
class CallStack(Component):
    """An animated component: frames from a Trace, drawn by its own JavaScript runtime."""

    Options = CallStackOptions
    body = "yaml"
    runtime = str(HERE / "call_stack.js")
    css = [str(HERE / "plugins.css")]

    def render(self, block, opts, ctx):
        trace = ctx.call(opts.source, **(opts.model_extra or {}))
        if not isinstance(trace, Trace) or not len(trace):
            raise ComponentError(f"{opts.source} must return a non-empty Trace")
        store = trace.frame_store(ctx.frames_config.max_full_bytes, ctx.frames_config.keyframe_interval)
        return RenderResult('<div class="call-stack"></div>', data={"frames": store},
                            positions=len(trace), meta=trace.meta)
