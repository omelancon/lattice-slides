"""Named segments in code (spec 8.10).

A segment is a stretch of code named by markers written in comments of the source itself, so that an
arrow or a highlight can say ``i-init`` instead of a line number and a token position:

    (let loop (#|@i-init|# (i 0) #|@end|#) ...)       ; inline form, block comments

    # @loop                                           # whole-line form, line comments
    while lo < hi:
        ...
    # @end

``parse_markers`` removes the markers and returns the displayed lines, the original line number of each
of them and the segments in displayed coordinates. ``wrap_line`` wraps the segments of one line of
Pygments HTML in ``<span class="lt-seg" data-lt-seg="NAME">`` elements without touching the tokens'
classes; the first piece of a segment carries ``id="NAME"``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


NAME = r"[A-Za-z][A-Za-z0-9_-]*"
NAME_RE = re.compile(rf"\A{NAME}\Z")
_BODY = rf"\s*@(?:(?P<end>end)(?:\s+(?P<endname>{NAME}))?|(?P<name>{NAME}))\s*"
# block comments recognized in any language: Scheme and Lisp, C family, ML, Haskell, HTML
_PAIRS = [(r"#\|", r"\|#"), (r"/\*", r"\*/"), (r"\(\*", r"\*\)"), (r"\{-", r"-\}"), (r"<!--", r"-->")]
INLINE_RE = re.compile("|".join(f"(?:{o}{_BODY.replace('?P<', f'?P<p{i}_')}{c})"
                                for i, (o, c) in enumerate(_PAIRS)))
# a line holding only a line comment with a marker: #, ;, //, --, %
LINE_RE = re.compile(rf"\A[ \t]*(?:#+|;+|//|--|%+)[ \t]*@(?:(?P<end>end)(?:[ \t]+(?P<endname>{NAME}))?|(?P<name>{NAME}))[ \t]*\Z")


class MarkerError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(message)
        self.line = line


@dataclass
class Segment:
    name: str
    l0: int          # displayed line index (0-based) and column where the segment starts
    c0: int
    l1: int = -1     # and where it ends (exclusive column)
    c1: int = -1
    line: int = 0    # original line of the opening marker, for messages
    order: int = 0   # opening order: an outer segment opens before the segments it contains


@dataclass
class Marked:
    lines: list[str]
    orig: list[int]                     # original 1-based line number of each displayed line
    segments: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _groups(m: re.Match) -> tuple[bool, str | None]:
    """(is an end marker, name) of an inline or line-form match."""
    d = {k.split("_", 1)[-1]: v for k, v in m.groupdict().items() if v is not None}
    if "end" in d:
        return True, d.get("endname")
    return False, d["name"]


def plain(text: str) -> Marked:
    lines = text.split("\n")
    return Marked(lines, list(range(1, len(lines) + 1)))


def parse_markers(text: str) -> Marked:
    """Remove segment markers from ``text``; raise MarkerError on a malformed one."""
    out = Marked([], [])
    stack: list[Segment] = []
    names: dict[str, int] = {}
    order = 0

    def open_(name: str, l0: int, c0: int, lineno: int):
        nonlocal order
        if name in names:
            raise MarkerError(f"segment @{name} is already defined at line {names[name]}", lineno)
        names[name] = lineno
        order += 1
        stack.append(Segment(name, l0, c0, line=lineno, order=order))

    def close(name: str | None, l1: int, c1: int, lineno: int):
        if not stack:
            raise MarkerError("@end without an open segment", lineno)
        seg = stack[-1]
        if name is not None and name != seg.name:
            raise MarkerError(f"@end {name} closes segment @{seg.name}", lineno)
        stack.pop()
        seg.l1, seg.c1 = l1, c1
        if (seg.l1, seg.c1) <= (seg.l0, seg.c0) or not _has_text(out.lines, seg):
            raise MarkerError(f"segment @{seg.name} is empty", lineno)
        out.segments.append(seg)

    for lineno, line in enumerate(text.split("\n"), start=1):
        m = LINE_RE.match(line)
        if m:
            is_end, name = _groups(m)
            n = len(out.lines)
            if is_end:
                close(name, n - 1, len(out.lines[-1]) if n else 0, lineno)
            else:
                open_(name, n, 0, lineno)
            continue
        matches = list(INLINE_RE.finditer(line))
        if not matches:
            out.lines.append(line)
            out.orig.append(lineno)
            continue
        n = len(out.lines)
        buf, pos = "", 0
        events = []  # (is_end, name, column) in the cleaned line
        for mm in matches:
            buf += line[pos:mm.start()]
            pos = mm.end()
            is_end, name = _groups(mm)
            if is_end and buf.strip():
                buf = buf.rstrip(" \t")          # a closing marker takes the spaces before it,
            else:                                # but never the indentation of its line;
                while pos < len(line) and line[pos] in " \t":
                    pos += 1                     # an opening marker takes the spaces after it
            events.append((is_end, name, len(buf)))
        buf += line[pos:]
        stripped = buf.rstrip(" \t")
        if stripped.strip():
            out.lines.append(stripped)
            out.orig.append(lineno)
            for is_end, name, col in events:
                col = min(col, len(stripped))
                if is_end:
                    close(name, n, col, lineno)
                else:
                    open_(name, n, col, lineno)
        else:  # nothing but markers: the line is dropped
            for is_end, name, _ in events:
                if is_end:
                    close(name, n - 1, len(out.lines[-1]) if n else 0, lineno)
                else:
                    open_(name, n, 0, lineno)
    if stack:
        seg = stack[-1]
        raise MarkerError(f"segment @{seg.name} is never closed", seg.line)
    out.segments.sort(key=lambda s: s.order)
    return out


def _has_text(lines: list[str], seg: Segment) -> bool:
    for i in range(seg.l0, seg.l1 + 1):
        if i >= len(lines):
            break
        a = seg.c0 if i == seg.l0 else 0
        b = seg.c1 if i == seg.l1 else len(lines[i])
        if lines[i][a:b].strip():
            return True
    return False


def select(marked: Marked, lo: int, hi: int) -> Marked:
    """The displayed lines whose original number is in ``lo..hi``, with the segments clipped to them."""
    idx = [i for i, n in enumerate(marked.orig) if lo <= n <= hi]
    if not idx:
        return Marked([], [])
    s, e = idx[0], idx[-1]
    return _slice(marked, s, e)


def _slice(marked: Marked, s: int, e: int) -> Marked:
    out = Marked(marked.lines[s:e + 1], marked.orig[s:e + 1])
    for g in marked.segments:
        if g.l1 < s or g.l0 > e:
            continue
        l0, c0 = (g.l0, g.c0) if g.l0 >= s else (s, 0)
        l1, c1 = (g.l1, g.c1) if g.l1 <= e else (e, len(marked.lines[e]))
        seg = Segment(g.name, l0 - s, c0, l1 - s, c1, g.line, g.order)
        if _has_text(out.lines, seg):
            out.segments.append(seg)
    return out


def trim(marked: Marked) -> Marked:
    """Drop the empty lines at both ends, as Pygments does (``stripnl``)."""
    s, e = 0, len(marked.lines) - 1
    while s <= e and marked.lines[s] == "":
        s += 1
    while e >= s and marked.lines[e] == "":
        e -= 1
    if s > e:
        return Marked([], [])
    if s == 0 and e == len(marked.lines) - 1:
        return marked
    return _slice(marked, s, e)


def pieces(marked: Marked) -> dict[int, list[tuple[int, int, Segment, bool]]]:
    """Per displayed line, the pieces ``(c0, c1, segment, first)`` of every segment on it, without the
    whitespace at their edges; ``first`` marks the piece that carries the id."""
    out: dict[int, list[tuple[int, int, Segment, bool]]] = {}
    for g in marked.segments:
        first = True
        for i in range(g.l0, g.l1 + 1):
            text = marked.lines[i]
            a = g.c0 if i == g.l0 else 0
            b = g.c1 if i == g.l1 else len(text)
            part = text[a:b]
            if not part.strip():
                continue
            a += len(part) - len(part.lstrip())
            b -= len(part) - len(part.rstrip())
            out.setdefault(i, []).append((a, b, g, first))
            first = False
    return out


_TOKEN_RE = re.compile(r'<span class="([^"]*)">([^<]*)</span>|([^<]+)')
_UNIT_RE = re.compile(r"&[#A-Za-z0-9]+;|[^&]|&")


def wrap_line(line_html: str, line_pieces, hl: set[str]) -> str:
    """Wrap the pieces of one line in segment spans. ``line_html`` is HtmlFormatter output with
    ``nowrap``: a flat sequence of ``<span class="X">text</span>`` and bare text."""
    tokens: list[tuple[str | None, list[str]]] = []
    pos = 0
    for m in _TOKEN_RE.finditer(line_html):
        if m.start() != pos:  # not the flat shape we expect: leave the line alone
            return line_html
        pos = m.end()
        # keep Pygments' own escaping: a unit is one character of the code, an entity or a plain char
        if m.group(3) is not None:
            tokens.append((None, _UNIT_RE.findall(m.group(3))))
        else:
            tokens.append((m.group(1), _UNIT_RE.findall(m.group(2))))
    if pos != len(line_html):
        return line_html
    opens: dict[int, list] = {}
    closes: dict[int, list] = {}
    for a, b, g, first in line_pieces:
        opens.setdefault(a, []).append((b, g, first))
        closes.setdefault(b, []).append(g)
    cuts = sorted(set(opens) | set(closes))
    out: list[str] = []
    col = 0

    def boundary(c: int):
        for g in sorted(closes.get(c, []), key=lambda g: -g.order):     # innermost first
            out.append("</span>")
        for b, g, first in sorted(opens.get(c, []), key=lambda t: t[1].order):  # outermost first
            cls = "lt-seg lt-hl" if g.name in hl else "lt-seg"
            ident = f' id="{g.name}"' if first else ""
            out.append(f'<span class="{cls}" data-lt-seg="{g.name}"{ident}>')

    ci = 0
    if cuts and cuts[0] == 0:
        boundary(0)
        ci = 1
    for cls, text in tokens:
        start = col
        end = col + len(text)
        while text:
            nxt = cuts[ci] if ci < len(cuts) else None
            if nxt is not None and start < nxt < end:  # a boundary inside the token: split it
                part, text = text[:nxt - start], text[nxt - start:]
                start = nxt
            else:
                part, text = text, []
                start = end
            part = "".join(part)
            out.append(f'<span class="{cls}">{part}</span>' if cls else part)
            if ci < len(cuts) and start == cuts[ci]:
                boundary(cuts[ci])
                ci += 1
        col = end
    while ci < len(cuts):  # pieces ending at the end of the line
        boundary(cuts[ci])
        ci += 1
    return "".join(out)
