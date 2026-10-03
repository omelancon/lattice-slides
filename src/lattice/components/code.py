"""Code components: ``code`` (static or following) and ``code-steps`` (spec 8.8)."""
from __future__ import annotations

import ast
import html
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pygments import highlight
from pygments.formatters import HtmlFormatter

from .scheme import lexer_for
from .base import Component, ComponentError, RenderResult, register
from .segments import NAME_RE, Marked, MarkerError, parse_markers, pieces, plain, select, trim, wrap_line


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
    meta: str | None = None  # as a follower: the leader's per-position meta key holding the lines
    markers: bool = True     # read segment markers (spec 8.10); false shows the text as written


class CodeStepsOptions(CodeOptions):
    steps: list[str | int | list[str | int]] = Field(default_factory=list)


def parse_ranges(spec: str | int | None) -> list[int]:
    """``"1-3, 7"`` -> ``[1, 2, 3, 7]``."""
    lines, names = parse_targets(spec)
    if names:
        raise ComponentError(f"invalid line range {names[0]!r}")
    return lines


def parse_targets(spec, segments: set[str] | None = None) -> tuple[list[int], list[str]]:
    """Line ranges and segment names: ``"1-3, i-init, 7"`` -> ``([1, 2, 3, 7], ["i-init"])``. A list
    holds the same items. With ``segments``, a name must be one of them."""
    if spec is None or spec == "":
        return [], []
    parts = spec if isinstance(spec, (list, tuple)) else str(spec).split(",")
    lines: list[int] = []
    names: list[str] = []
    for part in parts:
        if isinstance(part, int):
            lines.append(part)
            continue
        part = str(part).strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            lines.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            lines.append(int(part))
        elif NAME_RE.match(part):
            if segments is not None and part not in segments:
                raise ComponentError(f"no segment named {part!r} in this code"
                                     + (f" (segments: {', '.join(sorted(segments))})" if segments else ""))
            names.append(part)
        else:
            raise ComponentError(f"invalid line range {part!r}")
    return lines, names


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


def read_source_file(file: str, ctx) -> str:
    """A file of the deck, or ``lattice:PATH`` for a file bundled with Lattice (for example
    ``lattice:bbv/pseudocode/sbbv.txt``)."""
    if file.startswith("lattice:"):
        from importlib import resources

        res = resources.files("lattice") / file[len("lattice:"):]
        if not res.is_file():
            raise ComponentError(f"no bundled file {file!r}")
        return res.read_text(encoding="utf-8")
    return ctx.path(file).read_text(encoding="utf-8")


def _marked(text: str, opts: CodeOptions, where: str) -> Marked:
    if not opts.markers:
        return plain(text)
    try:
        return parse_markers(text)
    except MarkerError as e:
        raise ComponentError(f"{where}:{e.line}: {e}") from None


def load_source(opts: CodeOptions, body: str, ctx) -> Marked:
    """The displayed lines (markers removed, spec 8.10), the original line number of each, and the
    segments. ``symbol`` and ``lines`` count the lines of the file as written."""
    if opts.file:
        text = read_source_file(opts.file, ctx)
        marked = _marked(text, opts, opts.file)
        if opts.symbol:
            if opts.lang not in ("python", "py", "python3"):
                raise ComponentError("symbol extraction is only supported for Python")
            a, b = extract_symbol(text, opts.symbol)
            marked = select(marked, a, b)
        if opts.lines:
            wanted = parse_ranges(opts.lines)
            marked = select(marked, min(wanted), max(wanted))
        return trim(marked)
    if opts.symbol or opts.lines:
        raise ComponentError("'symbol' and 'lines' require 'file'")
    return trim(_marked(body, opts, "line"))


def render_code_html(src: Marked, lang: str, numbers: list[int], linenos: bool,
                     static_hl: set[int], static_segs: set[str], title: str | None) -> str:
    code = src.text
    body = highlight(code, lexer_for(lang), HtmlFormatter(nowrap=True)).rstrip("\n")
    segs = pieces(src)
    in_seg = {i for i, ps in segs.items() if any(g.name in static_segs for _, _, g, _ in ps)}
    rows = []
    for i, line in enumerate(body.split("\n")):
        n = numbers[i] if i < len(numbers) else (numbers[-1] if numbers else 0) + 1
        cls = "lt-line lt-hl" if n in static_hl else "lt-line"
        if i in in_seg:
            cls += " lt-hl-in"
        if i in segs:
            line = wrap_line(line, segs[i], static_segs)
        gutter = f'<span class="lt-ln">{src.orig[i] if i < len(src.orig) else n}</span>' if linenos else ""
        rows.append(f'<span class="{cls}" data-line="{n}">{gutter}{line or " "}</span>')
    head = f'<div class="lt-code-title">{html.escape(title)}</div>' if title else ""
    dim = " lt-has-hl" if static_hl or static_segs else ""
    return (f'<div class="lt-code{dim}" data-lang="{html.escape(lang)}">{head}'
            f'<pre><code>{"".join(rows)}</code></pre></div>')


def _numbers(opts: CodeOptions, src: Marked) -> list[int]:
    """The ``data-line`` of each displayed line: its line in the file (``line_base=file``) or its rank."""
    return list(src.orig) if opts.line_base == "file" else list(range(1, len(src.lines) + 1))


def _render(opts: CodeOptions, src: Marked) -> tuple[str, list[str]]:
    names = {g.name for g in src.segments}
    lines, segs = parse_targets(opts.highlight, names)
    html_ = render_code_html(src, opts.lang, _numbers(opts, src), opts.linenos, set(lines), set(segs), opts.title)
    return html_, sorted(names)


def _steps_data(targets: list[tuple[list[int], list[str]]]) -> dict:
    data = {"steps": [t[0] for t in targets]}
    if any(t[1] for t in targets):
        data["segs"] = [t[1] for t in targets]
    return data


@register("code")
class Code(Component):
    Options = CodeOptions
    body = "text"
    runtime = "code.js"

    def render(self, block, opts: CodeOptions, ctx) -> RenderResult:
        src = load_source(opts, block.body, ctx)
        html_, anchors = _render(opts, src)
        if ctx.leader is None:
            return RenderResult(html_, anchors=anchors)
        names = set(anchors)
        targets = []
        for m in (ctx.leader.meta or [{}] * ctx.leader.positions):
            lines = m.get(opts.meta) if opts.meta else m.get("lines", m.get("line"))
            targets.append(parse_targets(lines, names))
        return RenderResult(html_, data=_steps_data(targets), positions=ctx.leader.positions, anchors=anchors)


@register("code-steps")
class CodeSteps(Component):
    Options = CodeStepsOptions
    body = "yaml"
    runtime = "code.js"

    def render(self, block, opts: CodeStepsOptions, ctx) -> RenderResult:
        if opts.file is None:
            raise ComponentError("code-steps needs 'file' (the body holds the steps)")
        src = load_source(opts, "", ctx)
        html_, anchors = _render(opts, src)
        names = set(anchors)
        targets = [([], [])] + [parse_targets(s, names) for s in opts.steps]
        return RenderResult(html_, data=_steps_data(targets), positions=len(targets), anchors=anchors)


class DiffOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str = "text"
    versions: list[str | dict] = Field(default_factory=list)
    context: int | None = None  # lines of context around changes; None shows everything
    title: str | None = None
    markers: bool = True  # remove segment markers (spec 8.10); diffs define no segments


def _highlight_lines(code: str, lang: str) -> list[str]:
    body = highlight(code, lexer_for(lang), HtmlFormatter(nowrap=True)).rstrip("\n")
    return body.split("\n") if code else []


@dataclass
class Version:
    """One entry of a ``versions:`` list (``diff-steps``, ``code-morph``), as written."""
    text: str
    label: str           # the label given, else the file name or "version N"
    explicit: bool       # whether the label was given
    lang: str | None     # a language of its own (``code-morph`` only), else None
    where: str           # prefix of marker error messages: "FILE" or "version N, line"


def read_versions(versions: list, ctx) -> list[Version]:
    """Read a ``versions:`` list: file paths, or mappings with ``file`` or ``code`` and an optional
    ``label`` (and ``lang``, which only ``code-morph`` uses)."""
    out = []
    for i, v in enumerate(versions):
        if isinstance(v, str):
            v = {"file": v}
        lang = v.get("lang")
        lang = None if lang is None else str(lang)
        if "file" in v:
            text = read_source_file(v["file"], ctx)
            out.append(Version(text, v.get("label", v["file"]), "label" in v, lang, v["file"]))
        elif "code" in v:
            out.append(Version(str(v["code"]), v.get("label", f"version {i + 1}"), "label" in v, lang,
                               f"version {i + 1}, line"))
        else:
            raise ComponentError("each version is a file path, or a mapping with 'file' or 'code'")
    return out


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
        loaded = read_versions(opts.versions, ctx)
        texts = [self._clean(v.text, opts, v.where) for v in loaded]
        labels = [v.label for v in loaded]
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
    def _clean(text: str, opts: DiffOptions, where: str) -> str:
        if opts.markers:
            try:
                text = parse_markers(text).text
            except MarkerError as e:
                raise ComponentError(f"{where}:{e.line}: {e}") from None
        return text.rstrip("\n")

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
