"""``code-morph``: code whose text changes from one position to the next (spec 8.11).

Everything is decided here, at build time. Each version is highlighted with Pygments and cut into units
(a run of word characters, or one other character; runs of spaces are gaps, not units), every unit at a
row and a column of a monospace grid. Consecutive versions are aligned (``align``): units that survive
keep their identity, so the runtime only has to place each unit where the current version wants it,
and to fade in or out the units that have no place there.

The second authoring form (``file`` with ``steps:``) produces its versions by replacing the text of named
segments of one file (``replace_segments``); after that, both forms share the same pipeline.
"""
from __future__ import annotations

import difflib
import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pygments.formatters import HtmlFormatter

from .base import Component, ComponentError, RenderResult, register
from .code import CodeOptions, _marked, load_source, parse_targets, read_versions
from .scheme import lexer_for
from .segments import Marked, Segment, pieces, trim, wrap_line

UNIT_RE = re.compile(r"\w+|\s+|[^\w\s]")
TAB = 8            # the width the browser gives a tab in a `code` block (CSS default `tab-size`)
MOVE_MIN = 6       # a line moved elsewhere glides only if it holds at least this many characters
RESERVED = ("label", "lang", "highlight")
CHANGED = "changed"  # the highlight keyword: the rows holding units new at that position
_FORMATTER = HtmlFormatter()


class MorphOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str = "text"
    title: str | None = None
    versions: list[str | dict] = Field(default_factory=list)
    file: str | None = None
    lines: str | None = None
    symbol: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    label: str | None = None
    markers: bool = True
    linenos: bool = False
    duration: int = Field(600, ge=0, le=10000)
    room: Literal["max", "fit"] = "max"
    mark: bool = False
    highlight: str | int | list[str | int] | None = None  # the default highlight of every position

    @model_validator(mode="after")
    def _one_form(self):
        if self.versions and (self.file or self.steps):
            raise ValueError("give either 'versions' or 'file' with 'steps', not both")
        if not self.versions and not self.file:
            raise ValueError("needs 'versions', or 'file' with 'steps'")
        if self.steps and not self.file:
            raise ValueError("'steps' needs 'file'")
        if self.file and not self.steps:
            raise ValueError("'file' needs 'steps:' (one entry per position after the first)")
        if self.versions and (self.lines or self.symbol or self.label):
            raise ValueError("'lines', 'symbol' and 'label' belong to the 'file' form")
        return self


# ------------------------------------------------------------------ units


@dataclass
class Unit:
    text: str
    cls: str      # Pygments CSS class(es), as HtmlFormatter writes them ("" for plain text)
    row: int
    col: int


def expand_tabs(marked: Marked) -> Marked:
    """Tabs become spaces up to the next multiple of TAB; segment columns follow."""
    if not any("\t" in line for line in marked.lines):
        return marked
    maps: list[list[int] | None] = []
    lines = []
    for line in marked.lines:
        if "\t" not in line:
            maps.append(None)
            lines.append(line)
            continue
        m, out = [], []
        for ch in line:
            m.append(len(out))
            if ch == "\t":
                out.extend(" " * (TAB - len(out) % TAB))
            else:
                out.append(ch)
        m.append(len(out))
        maps.append(m)
        lines.append("".join(out))

    def col(l: int, c: int) -> int:
        m = maps[l] if l < len(maps) else None
        return c if m is None else m[min(c, len(m) - 1)]

    segs = [Segment(g.name, g.l0, col(g.l0, g.c0), g.l1, col(g.l1, g.c1), g.line, g.order) for g in marked.segments]
    return Marked(lines, list(marked.orig), segs)


def tokenize(lines: list[str], lang: str) -> list[list[Unit]]:
    """One list of drawn units per line."""
    lexer = lexer_for(lang)
    lexer.stripnl = False  # rows must stay the rows of `lines`
    rows: list[list[Unit]] = [[]]
    col = 0
    for ttype, value in lexer.get_tokens("\n".join(lines)):
        cls = _FORMATTER._get_css_classes(ttype)
        for k, part in enumerate(value.split("\n")):
            if k:
                rows.append([])
                col = 0
            for u in UNIT_RE.findall(part):
                if not u.isspace():
                    rows[-1].append(Unit(u, cls, len(rows) - 1, col))
                col += len(u)
    rows = rows[:len(lines)]
    while len(rows) < len(lines):
        rows.append([])
    return rows


def odd_char(lines: list[str]) -> tuple[int, str] | None:
    """The first character that does not take one column of a monospace font: (1-based line, char)."""
    for i, line in enumerate(lines, start=1):
        for ch in line:
            if ch.isascii():
                if ch.isprintable() or ch == " ":
                    continue
            elif (unicodedata.east_asian_width(ch) not in ("W", "F") and not unicodedata.combining(ch)
                  and unicodedata.category(ch) not in ("Cc", "Cf", "Mn", "Me", "Zl", "Zp")):
                continue
            return i, ch
    return None


# ------------------------------------------------------------------ alignment


def _line_key(row: list[Unit]) -> tuple[str, ...]:
    return tuple(u.text for u in row)


def align(a: list[list[Unit]], b: list[list[Unit]], same_lang: bool = True) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Pairs ``((row, index) in a, (row, index) in b)`` of the units that survive from ``a`` to ``b``.

    Lines are aligned first, on their units without spaces; equal lines, and lines moved elsewhere
    unchanged, pair their units in order. The units of the other lines of each changed region are
    aligned together, so a unit may survive on another line."""
    ka = [_line_key(r) for r in a]
    kb = [_line_key(r) for r in b]
    ops = difflib.SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes()
    pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []

    def same_line(i: int, j: int) -> None:
        pairs.extend(((i, x), (j, x)) for x in range(len(a[i])))

    # moves: a line deleted on one side and inserted on the other, unchanged and unique
    old = [i for tag, a0, a1, _, _ in ops if tag in ("delete", "replace") for i in range(a0, a1)]
    new = [j for tag, _, _, b0, b1 in ops if tag in ("insert", "replace") for j in range(b0, b1)]
    count_a: dict[tuple, list[int]] = {}
    count_b: dict[tuple, list[int]] = {}
    for i in old:
        count_a.setdefault(ka[i], []).append(i)
    for j in new:
        count_b.setdefault(kb[j], []).append(j)
    moved_a: set[int] = set()
    moved_b: set[int] = set()
    for key, ia in count_a.items():
        jb = count_b.get(key)
        if len(ia) == 1 and jb and len(jb) == 1 and len("".join(key)) >= MOVE_MIN:
            same_line(ia[0], jb[0])
            moved_a.add(ia[0])
            moved_b.add(jb[0])

    def key(u: Unit) -> str:
        return f"{u.cls}\x00{u.text}" if same_lang else u.text

    for tag, a0, a1, b0, b1 in ops:
        if tag == "equal":
            for i, j in zip(range(a0, a1), range(b0, b1)):
                same_line(i, j)
        elif tag == "replace":
            fa = [(i, x) for i in range(a0, a1) if i not in moved_a for x in range(len(a[i]))]
            fb = [(j, y) for j in range(b0, b1) if j not in moved_b for y in range(len(b[j]))]
            sa = [key(a[i][x]) for i, x in fa]
            sb = [key(b[j][y]) for j, y in fb]
            sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
            for t, c0, c1, d0, d1 in sm.get_opcodes():
                if t == "equal":
                    pairs.extend(zip(fa[c0:c1], fb[d0:d1]))
    return pairs


@dataclass
class Morph:
    """The whole animation: per unit its text and, per version, ``[row, col, class index]`` or None."""
    texts: list[str]
    pos: list[list[list[int] | None]]
    classes: list[str]
    rows: list[int]
    cols: int
    changed: list[int]


def build_morph(versions: list[list[list[Unit]]], langs: list[str]) -> Morph:
    classes: list[str] = []
    cindex: dict[str, int] = {}

    def ci(c: str) -> int:
        if c not in cindex:
            cindex[c] = len(classes)
            classes.append(c)
        return cindex[c]

    n = len(versions)
    texts: list[str] = []
    pos: list[list[list[int] | None]] = []
    prev_ids: dict[tuple[int, int], int] = {}
    changed = [0] * n
    for v, rows in enumerate(versions):
        ids: dict[tuple[int, int], int] = {}
        if v:
            for (pa, pb) in align(versions[v - 1], rows, langs[v - 1] == langs[v]):
                ids[pb] = prev_ids[pa]
        moved_rows = []
        for r, row in enumerate(rows):
            for x, u in enumerate(row):
                t = ids.get((r, x))
                if t is None:
                    t = len(texts)
                    texts.append(u.text)
                    pos.append([None] * n)
                    ids[(r, x)] = t
                    moved_rows.append(r)
                elif pos[t][v - 1][:2] != [r, u.col]:
                    moved_rows.append(r)
                pos[t][v] = [r, u.col, ci(u.cls)]
        if v:
            if moved_rows:
                changed[v] = min(moved_rows)
            else:  # only removals: the row where they were, if it still exists
                gone = [p[v - 1][0] for p in pos if p[v - 1] is not None and p[v] is None]
                changed[v] = max(0, min(min(gone) if gone else 0, len(rows) - 1))
        prev_ids = ids
    cols = max([u.col + len(u.text) for rows in versions for row in rows for u in row] or [0])
    return Morph(texts, pos, classes, [len(rows) for rows in versions], cols, changed)


# ------------------------------------------------------------------ the steps form


def _contains(outer: Segment, inner: Segment) -> bool:
    return (outer is not inner and outer.order < inner.order
            and (outer.l0, outer.c0) <= (inner.l0, inner.c0) and (inner.l1, inner.c1) <= (outer.l1, outer.c1))


def replace_segments(base: Marked, repl: dict[str, str]) -> Marked:
    """``base`` with the contents of the named segments replaced (no two of them nested). The replaced
    segments cover their new text; segments nested in a replaced one disappear."""
    by_name = {g.name: g for g in base.segments}
    starts = [0]
    for line in base.lines:
        starts.append(starts[-1] + len(line) + 1)
    text = "\n".join(base.lines)

    def off(l: int, c: int) -> int:
        return starts[l] + c

    edits = []  # (start, end, new text, segment, [start, end) of the segment in the new text, relative)
    for name, new in repl.items():
        g = by_name[name]
        first_line = base.lines[g.l0]
        before = first_line[:g.c0]
        indent = first_line[:len(first_line) - len(first_line.lstrip(" \t"))]
        whole = before.strip() == "" and base.lines[g.l1][g.c1:].strip() == ""
        c0 = max(g.c0, len(indent)) if before.strip() == "" else g.c0  # the indentation stays
        s, e = off(g.l0, min(c0, len(first_line) if g.l1 > g.l0 else g.c1)), off(g.l1, g.c1)
        new = new.rstrip("\n")
        if before.strip() == "" and "\n" in new:  # further lines take the same indentation
            head, *rest = new.split("\n")
            new = "\n".join([head] + [indent + r if r else r for r in rest])
        if new == "" and whole:  # an empty replacement of whole lines removes them
            s = starts[g.l0]
            e = starts[g.l1 + 1] if g.l1 + 1 < len(base.lines) else len(text)
            if g.l1 + 1 >= len(base.lines) and s > 0:
                s -= 1  # the last lines: remove the line break before them instead
            edits.append((s, e, "", g))
        else:
            edits.append((s, e, new, g))
    edits.sort(key=lambda t: t[0])
    for i in range(1, len(edits)):  # a removal of the last lines may reach back into the edit before it
        s, e, new, g = edits[i]
        if s < edits[i - 1][1]:
            edits[i] = (edits[i - 1][1], e, new, g)

    out, last = [], 0
    for s, e, new, _ in edits:
        out.append(text[last:s])
        out.append(new)
        last = e
    out.append(text[last:])
    new_text = "".join(out)

    def mapo(o: int) -> int:
        for s, e, new, _ in edits:
            if s < o < e and new == "":
                o = s  # a boundary inside removed lines moves to where they were
        return o + sum(len(new) - (e - s) for s, e, new, _ in edits if e <= o)

    nstarts = [0]
    lines = new_text.split("\n")
    for line in lines:
        nstarts.append(nstarts[-1] + len(line) + 1)

    def lc(o: int) -> tuple[int, int]:
        import bisect

        l = max(0, bisect.bisect_right(nstarts, o) - 1)
        l = min(l, len(lines) - 1)
        return l, o - nstarts[l]

    replaced = {g.name for _, _, _, g in edits}
    segs = []
    for g in base.segments:
        if g.name in replaced:
            s, e, new, _ = next(t for t in edits if t[3] is g)
            if new == "" and e - s > off(g.l1, g.c1) - off(g.l0, g.c0):
                continue  # its lines are gone
            a = mapo(s)
            l0, c0 = lc(a)
            l1, c1 = lc(a + len(new))
        else:
            if any(_contains(t[3], g) for t in edits):
                continue
            l0, c0 = lc(mapo(off(g.l0, g.c0)))
            l1, c1 = lc(mapo(off(g.l1, g.c1)))
        segs.append(Segment(g.name, l0, c0, l1, c1, g.line, g.order))
    segs.sort(key=lambda g: g.order)
    return Marked(lines, list(range(1, len(lines) + 1)), segs)


def step_versions(base: Marked, steps: list[dict[str, Any]], label0: str | None) -> list[tuple[Marked, str, bool]]:
    """The versions of the steps form: ``(text, label, label given)`` for position 0 and each step.
    The reserved key ``highlight`` of a step is read by the caller."""
    by_name = {g.name: g for g in base.segments}
    out = [(base, label0 or "as written", label0 is not None)]
    state: dict[str, str] = {}
    for k, step in enumerate(steps, start=1):
        if "lang" in step:
            raise ComponentError(f"step {k}: the language can change only between versions (use 'versions:')")
        label = step.get("label")
        sets = {n: v for n, v in step.items() if n not in RESERVED}
        for name in sets:
            if name not in by_name:
                known = ", ".join(sorted(by_name)) or "none"
                raise ComponentError(f"step {k}: no segment named {name!r} in this code (segments: {known})")
        for name, value in sets.items():
            for other, v2 in sets.items():
                if v2 is not None and value is not None and _contains(by_name[other], by_name[name]):
                    raise ComponentError(f"step {k}: segment {name!r} is inside {other!r}, set in the same step")
        for name, value in sets.items():
            for outer in state:
                if outer not in sets and _contains(by_name[outer], by_name[name]):
                    raise ComponentError(f"step {k}: segment {name!r} is inside {outer!r}, which is replaced")
            if value is None:
                state.pop(name, None)
                continue
            for inner in [n for n in state if _contains(by_name[name], by_name[n])]:
                del state[inner]
            state[name] = "" if value is None else str(value)
        text = replace_segments(base, state) if state else base
        out.append((trim(text), str(label) if label is not None else f"step {k}", label is not None))
    return out


# ------------------------------------------------------------------ highlights


def _split_changed(spec) -> tuple[list, bool]:
    """The targets of a highlight without the keyword ``changed``, and whether it was named."""
    if spec is None:
        return [], False
    parts = spec if isinstance(spec, (list, tuple)) else str(spec).split(",")
    rest = [p for p in parts if not (isinstance(p, str) and p.strip() == CHANGED)]
    return rest, len(rest) != len(parts)


def _targets(spec, where: str) -> tuple[list[int], list[str], bool]:
    rest, changed = _split_changed(spec)
    try:
        lines, names = parse_targets(rest)
    except ComponentError as e:
        raise ComponentError(f"{where}: {e}") from None
    return lines, names, changed


def _lines(n: int) -> str:
    return f"{n} line" if n == 1 else f"{n} lines"


def changed_rows(m: Morph, v: int) -> set[int]:
    """The rows of version ``v`` holding a unit that did not survive from version ``v - 1``."""
    if v == 0:
        return set()
    return {p[v][0] for p in m.pos if p[v] is not None and p[v - 1] is None}


def resolve_highlights(texts: list[Marked], labels: list[str], m: Morph, own: list[tuple[bool, Any]],
                       default) -> list[tuple[set[int], set[str]]]:
    """Per position, the highlighted rows (0-based) and segment names (spec 8.11, Highlights): the
    position's own targets if it has some, else the default."""
    d_lines, d_names, d_changed = _targets(default, "highlight")
    known = {g.name for t in texts for g in t.segments}
    for n in d_names:
        if n not in known:
            raise ComponentError(f"highlight: no segment named {n!r} at any position"
                                 + (f" (segments: {', '.join(sorted(known))})" if known else ""))
    out = []
    for v, t in enumerate(texts):
        here = {g.name for g in t.segments}
        rows = m.rows[v]
        where = f"position {v} ({labels[v]})"
        has, spec = own[v]
        if has:
            lines, names, changed = _targets(spec, f"{where}, highlight")
            for n in lines:
                if not 1 <= n <= rows:
                    raise ComponentError(f"{where}: highlight line {n}, but this version has {_lines(rows)}")
            for n in names:
                if n not in here:
                    raise ComponentError(f"{where}: no segment named {n!r} at this position"
                                         + (f" (segments: {', '.join(sorted(here))})" if here else ""))
        else:
            lines, names, changed = d_lines, [n for n in d_names if n in here], d_changed
            for n in lines:
                if not 1 <= n <= rows:
                    raise ComponentError(f"highlight line {n} (the default of every position): {where} "
                                         f"has {_lines(rows)}")
        lit = {n - 1 for n in lines} | (changed_rows(m, v) if changed else set())
        out.append((lit, set(names)))
    return out


_SEG_DATA = re.compile(r' data-lt-seg="[^"]*"')


def highlight_layer(marked: Marked, rows: set[int], names: set[str]) -> tuple[str, set[int]]:
    """The layer painted under the units at one position: a row element for each highlighted row and
    each row holding a highlighted segment (shaped like a ``code`` line, its text transparent), and the
    rows that stay undimmed. Its segment marks carry no id and no ``data-lt-seg``: arrows measure the
    text copy on top, never this layer."""
    lit = {i: [(a, b, g, False) for a, b, g, _ in ps if g.name in names] for i, ps in pieces(marked).items()}
    held = {i for i, ps in lit.items() if ps}
    out = []
    for i in sorted(rows | held):
        if i >= len(marked.lines):
            continue
        h = _esc(marked.lines[i])
        if lit.get(i):
            h = _SEG_DATA.sub("", wrap_line(h, lit[i], names))
        cls = "lt-line lt-hl" if i in rows else "lt-line"
        out.append(f'<span class="{cls}" style="--r:{i}">{h or " "}</span>')
    return "".join(out), rows | held


# ------------------------------------------------------------------ the component


def _esc(t: str) -> str:
    return html.escape(t, quote=False)


def _layer(marked: Marked) -> str:
    """The plain text of one version with its segments: the copy that selection and arrows use."""
    segs = pieces(marked)
    rows = []
    for i, line in enumerate(marked.lines):
        h = _esc(line)
        if i in segs:
            h = wrap_line(h, segs[i], set())
        rows.append(h)
    return "\n".join(rows)


@register("code-morph")
class CodeMorph(Component):
    """Code whose text changes between positions; unchanged tokens glide (spec 8.11)."""

    Options = MorphOptions
    body = "yaml"
    runtime = "code-morph.js"

    def render(self, block, opts: MorphOptions, ctx) -> RenderResult:
        texts, labels, given, langs, own = self._versions(opts, ctx)
        texts = [expand_tabs(t) for t in texts]
        for v in range(1, len(texts)):
            if texts[v].lines == texts[v - 1].lines and langs[v] == langs[v - 1]:
                ctx.warn(f"code-morph: positions {v - 1} and {v} show the same code", "LT059")
        for v, t in enumerate(texts):
            odd = odd_char(t.lines)
            if odd:
                ctx.warn(f"code-morph: position {v}, line {odd[0]}: {odd[1]!r} (U+{ord(odd[1]):04X}) does not take one "
                         "column of a monospace font; the code after it on that line is misplaced", "LT060")
        m = build_morph([tokenize(t.lines, lang) for t, lang in zip(texts, langs)], langs)
        height = max(1, max(m.rows))
        show_label = bool(opts.title) or any(given) or len(set(langs)) > 1
        anchors = sorted({g.name for t in texts for g in t.segments})
        layers = [_layer(t) for t in texts]

        # highlights (spec 8.11): per position the rows left undimmed (None: nothing dims) and a layer
        hl: list[list[int] | None] = []
        under: list[str] = []
        for t, (rows, names) in zip(texts, resolve_highlights(texts, labels, m, own, opts.highlight)):
            layer, bright = highlight_layer(t, rows, names)
            under.append(layer)
            hl.append(sorted(bright) if rows or names else None)
        lit0 = set(hl[0] or ())
        has_hl = any(h is not None for h in hl)

        toks = []
        for text, p in zip(m.texts, m.pos):
            at = p[0] or next(q for q in p if q is not None)
            off = "" if p[0] else " lt-mt-off"
            lit = " lt-mt-lit" if p[0] and at[0] in lit0 else ""
            cls = m.classes[at[2]]
            toks.append(f'<span class="lt-mt{" " + cls if cls else ""}{off}{lit}" style="--r:{at[0]};--c:{at[1]}">'
                        f'{_esc(text)}</span>')
        gutter = ""
        if opts.linenos:
            gutter = "".join(f'<span class="lt-morph-ln{"" if r < m.rows[0] else " lt-mt-off"}'
                             f'{" lt-mt-lit" if r in lit0 else ""}" style="--r:{r}">{r + 1}</span>'
                             for r in range(height))
        h0 = height if opts.room == "max" else max(1, m.rows[0])
        box_cls = "lt-morph-box" + (" lt-morph-ln-on" if opts.linenos else "")
        under_html = ""
        if has_hl:
            box_cls += " lt-morph-hl-on" + (" lt-morph-dim" if hl[0] is not None else "")
            under_html = (f'<span class="lt-morph-under" aria-hidden="true">'
                          f'<span class="lt-morph-hl lt-morph-hl-cur">{under[0]}</span>'
                          f'<span class="lt-morph-hl"></span></span>')
        stage = (f'<span class="lt-morph-stage" style="--h:{h0};--cols:{m.cols}">{under_html}{gutter}'
                 f'<span class="lt-morph-toks" aria-hidden="true">{"".join(toks)}</span>'
                 f'<span class="lt-morph-text">{layers[0]}</span></span>')
        head = ""
        if show_label:
            label = f'<span class="lt-morph-label{"" if opts.title else " lt-morph-label-solo"}">{html.escape(labels[0])}</span>'
            head = f'<div class="lt-code-title">{html.escape(opts.title or "")}{label}</div>'
        html_ = (f'<div class="lt-code lt-morph" data-lang="{html.escape(langs[0])}">{head}'
                 f'<pre><code class="{box_cls}">{stage}</code></pre></div>')
        data = {"pos": m.pos, "classes": m.classes, "rows": m.rows, "height": height, "labels": labels,
                "layers": layers, "changed": m.changed, "duration": opts.duration, "room": opts.room,
                "mark": opts.mark, "linenos": opts.linenos}
        if has_hl:
            data["hl"] = hl
            data["under"] = under
        meta = [{"label": lab, "version": i} for i, lab in enumerate(labels)]
        return RenderResult(html_, data=data, positions=len(texts), meta=meta, anchors=anchors)

    @staticmethod
    def _versions(opts: MorphOptions, ctx) -> tuple[list[Marked], list[str], list[bool], list[str], list[tuple[bool, Any]]]:
        """Texts, labels, whether each label was given, languages, and each position's own highlight
        ``(given, targets)``."""
        if opts.versions:
            if len(opts.versions) < 2:
                raise ComponentError("code-morph needs at least two versions")
            loaded = read_versions(opts.versions, ctx)
            texts = [trim(_marked(v.text, opts, v.where)) for v in loaded]
            langs = [v.lang or opts.lang for v in loaded]
            labels, given = [], []
            mixed = len(set(langs)) > 1
            for i, v in enumerate(loaded):
                if not v.explicit and mixed:
                    labels.append(lexer_for(langs[i]).name)
                else:
                    labels.append(str(v.label))
                given.append(v.explicit)
            return texts, labels, given, langs, [(v.has_highlight, v.highlight) for v in loaded]
        code_opts = CodeOptions(lang=opts.lang, file=opts.file, lines=opts.lines, symbol=opts.symbol,
                                markers=opts.markers)
        base = load_source(code_opts, "", ctx)
        vs = step_versions(base, opts.steps, opts.label)
        own = [(False, None)] + [("highlight" in step, step.get("highlight")) for step in opts.steps]
        return [t for t, _, _ in vs], [lab for _, lab, _ in vs], [g for _, _, g in vs], [opts.lang] * len(vs), own
