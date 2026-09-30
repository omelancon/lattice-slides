"""Code components: ``code`` (static or following) and ``code-steps`` (spec 8.8)."""
from __future__ import annotations

import ast
import html
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .base import Component, ComponentError, RenderResult, register


class CodeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str = "text"
    file: str | None = None
    lines: str | None = None
    symbol: str | None = None
    highlight: str | None = None
    linenos: bool = False
    line_base: Literal["snippet", "file"] = "snippet"
    title: str | None = None


class CodeStepsOptions(CodeOptions):
    steps: list[str | int] = Field(default_factory=list)


def parse_ranges(spec: str | int | None) -> list[int]:
    """``"1-3, 7"`` -> ``[1, 2, 3, 7]``."""
    if spec is None or spec == "":
        return []
    out: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise ComponentError(f"invalid line range {part!r}")
    return out


def extract_symbol(source: str, symbol: str) -> tuple[int, int]:
    """1-based inclusive line span of a Python function or class (``Class.method`` allowed)."""
    tree = ast.parse(source)
    nodes = [tree]
    target = None
    for name in symbol.split("."):
        found = None
        for parent in nodes:
            for n in getattr(parent, "body", []):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name:
                    found = n
                    break
            if found:
                break
        if found is None:
            raise ComponentError(f"symbol {symbol!r} not found")
        nodes = [found]
        target = found
    start = min([target.lineno] + [d.lineno for d in target.decorator_list])
    return start, target.end_lineno


def load_source(opts: CodeOptions, body: str, ctx) -> tuple[str, int]:
    """Return the snippet text and the file line number of its first line."""
    if opts.file:
        text = ctx.path(opts.file).read_text(encoding="utf-8")
        all_lines = text.split("\n")
        first = 1
        if opts.symbol:
            if opts.lang not in ("python", "py", "python3"):
                raise ComponentError("symbol extraction is only supported for Python")
            a, b = extract_symbol(text, opts.symbol)
            all_lines, first = all_lines[a - 1 : b], a
        if opts.lines:
            wanted = parse_ranges(opts.lines)
            lo, hi = min(wanted), max(wanted)
            all_lines = all_lines[lo - first : hi - first + 1]
            first = lo
        return "\n".join(all_lines).rstrip("\n"), first
    if opts.symbol or opts.lines:
        raise ComponentError("'symbol' and 'lines' require 'file'")
    return body.rstrip("\n"), 1


def render_code_html(code: str, lang: str, first_line: int, number_from: int, linenos: bool,
                     static_hl: set[int], title: str | None) -> str:
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    body = highlight(code, lexer, HtmlFormatter(nowrap=True)).rstrip("\n")
    rows = []
    for i, line in enumerate(body.split("\n")):
        n = number_from + i
        cls = "lt-line lt-hl" if n in static_hl else "lt-line"
        gutter = f'<span class="lt-ln">{first_line + i}</span>' if linenos else ""
        rows.append(f'<span class="{cls}" data-line="{n}">{gutter}{line or " "}</span>')
    head = f'<div class="lt-code-title">{html.escape(title)}</div>' if title else ""
    dim = " lt-has-hl" if static_hl else ""
    return (f'<div class="lt-code{dim}" data-lang="{html.escape(lang)}">{head}'
            f'<pre><code>{"".join(rows)}</code></pre></div>')


def _number_base(opts: CodeOptions, first: int) -> int:
    return first if opts.line_base == "file" else 1


@register("code")
class Code(Component):
    Options = CodeOptions
    body = "text"
    runtime = "code.js"

    def render(self, block, opts: CodeOptions, ctx) -> RenderResult:
        code, first = load_source(opts, block.body, ctx)
        base = _number_base(opts, first)
        html_ = render_code_html(code, opts.lang, first, base, opts.linenos,
                                 set(parse_ranges(opts.highlight)), opts.title)
        if ctx.leader is None:
            return RenderResult(html_)
        steps = []
        for m in (ctx.leader.meta or [{}] * ctx.leader.positions):
            lines = m.get("lines", m.get("line"))
            if isinstance(lines, (list, tuple)):
                steps.append([int(x) for x in lines])
            else:
                steps.append(parse_ranges(lines))
        return RenderResult(html_, data={"steps": steps}, positions=ctx.leader.positions)


@register("code-steps")
class CodeSteps(Component):
    Options = CodeStepsOptions
    body = "yaml"
    runtime = "code.js"

    def render(self, block, opts: CodeStepsOptions, ctx) -> RenderResult:
        if opts.file is None:
            raise ComponentError("code-steps needs 'file' (the body holds the steps)")
        code, first = load_source(opts, "", ctx)
        base = _number_base(opts, first)
        steps = [[]] + [parse_ranges(s) for s in opts.steps]
        html_ = render_code_html(code, opts.lang, first, base, opts.linenos,
                                 set(parse_ranges(opts.highlight)), opts.title)
        return RenderResult(html_, data={"steps": steps}, positions=len(steps))


class DiffOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str = "text"
    versions: list[str | dict] = Field(default_factory=list)
    context: int | None = None  # lines of context around changes; None shows everything
    title: str | None = None


def _highlight_lines(code: str, lang: str) -> list[str]:
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        lexer = get_lexer_by_name("text")
    body = highlight(code, lexer, HtmlFormatter(nowrap=True)).rstrip("\n")
    return body.split("\n") if code else []


@register("diff-steps")
class Diff(Component):
    """Step through successive versions of a snippet; each step marks what changed."""

    Options = DiffOptions
    body = "yaml"
    runtime = "diff.js"

    def render(self, block, opts: DiffOptions, ctx) -> RenderResult:
        import difflib

        if len(opts.versions) < 2:
            raise ComponentError("diff needs at least two versions")
        texts, labels = [], []
        for i, v in enumerate(opts.versions):
            if isinstance(v, str):
                v = {"file": v}
            if "file" in v:
                texts.append(ctx.path(v["file"]).read_text(encoding="utf-8").rstrip("\n"))
                labels.append(v.get("label", v["file"]))
            elif "code" in v:
                texts.append(str(v["code"]).rstrip("\n"))
                labels.append(v.get("label", f"version {i + 1}"))
            else:
                raise ComponentError("each version is a file path, or a mapping with 'file' or 'code'")
        lines = [t.split("\n") if t else [] for t in texts]
        hl = [_highlight_lines(t, opts.lang) for t in texts]
        panes = []
        for i in range(len(texts)):
            rows: list[tuple[str, str]] = []
            if i == 0:
                rows = [("ctx", h) for h in hl[0]]
            else:
                sm = difflib.SequenceMatcher(None, lines[i - 1], lines[i], autojunk=False)
                for tag, a0, a1, b0, b1 in sm.get_opcodes():
                    if tag == "equal":
                        rows += [("ctx", hl[i][j]) for j in range(b0, b1)]
                        continue
                    rows += [("del", hl[i - 1][j]) for j in range(a0, a1)]
                    rows += [("add", hl[i][j]) for j in range(b0, b1)]
            rows = self._collapse(rows, opts.context) if i > 0 else rows
            sign = {"ctx": " ", "add": "+", "del": "-", "gap": ""}
            body = "".join(
                f'<span class="lt-line lt-diff-{k}"><span class="lt-diff-sign">{sign[k]}</span>{h or " "}</span>'
                for k, h in rows)
            added = sum(1 for k, _ in rows if k == "add")
            removed = sum(1 for k, _ in rows if k == "del")
            stat = f'<span class="lt-diff-stat">+{added} -{removed}</span>' if i else ""
            head = (f'<div class="lt-code-title">{html.escape(labels[i])}{stat}</div>')
            hidden = " hidden" if i else ""
            panes.append(f'<div class="lt-diff-pane" data-pane="{i}"{hidden}>{head}<pre><code>{body}</code></pre></div>')
        title = f'<div class="lt-code-title">{html.escape(opts.title)}</div>' if opts.title else ""
        return RenderResult(f'<div class="lt-code lt-diff" data-lang="{html.escape(opts.lang)}">{title}{"".join(panes)}</div>',
                            data={"count": len(texts)}, positions=len(texts))

    @staticmethod
    def _collapse(rows, context):
        if context is None:
            return rows
        near = set()
        for i, (k, _) in enumerate(rows):
            if k != "ctx":
                near.update(range(i - context, i + context + 1))
        out, gap = [], False
        for i, row in enumerate(rows):
            if row[0] != "ctx" or i in near:
                out.append(row)
                gap = False
            elif not gap:
                out.append(("gap", '<span class="lt-diff-gap">\u22ef</span>'))
                gap = True
        return out
