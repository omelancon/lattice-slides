"""Column widths (spec 3.8): the values of ``width``, as the CSS ``flex`` values the build writes, and the
pass that marks the columns whose width changes (or starts collapsed) for the runtime (spec 10.4)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diagnostics import SourceLoc

SHUT = "0 0 0px"      # a collapsed column (width 0)
DEFAULT = "1 1 0"     # the stylesheet's `.lt-column` (no width attribute)
DEFAULT_DURATION = 600

_NUM = r"(\d+(?:\.\d+)?|\.\d+)"
_FR_RE = re.compile(rf"{_NUM}fr\Z")
_LEN_RE = re.compile(rf"{_NUM}(px|em|rem|%|vw|vh)\Z")
_ZERO_RE = re.compile(r"(0+(\.0*)?|\.0+)\Z")
DURATION_RE = re.compile(r"\d+\Z")


def column_flex(width: str) -> str | None:
    """The CSS ``flex`` of a column of width ``width``, or None when it is not a width (LT064). Every zero
    width is the collapsed value ``SHUT``."""
    w = width.strip()
    if _ZERO_RE.match(w):
        return SHUT
    m = _FR_RE.match(w)
    if m:
        return SHUT if float(m.group(1)) == 0 else f"{m.group(1)} 1 0"
    m = _LEN_RE.match(w)
    if m:
        return SHUT if float(m.group(1)) == 0 else f"0 0 {w}"
    return None


WIDTH_HELP = "a column width is a fraction (2fr), a CSS length (px, em, rem, %, vw, vh) or 0"


@dataclass
class ColumnBox:
    """A ``columns`` container met while building a slide body."""
    index: int
    loc: SourceLoc
    duration: int
    gap: str | None
    in_notes: bool
    columns: list[int] = field(default_factory=list)


@dataclass
class ColumnInfo:
    """A ``column`` container: its id, the flex value of its attribute (None: the default) and its box
    (None when it is not directly inside a ``columns``)."""
    index: int
    id: str | None
    flex: str | None
    box: int | None
    loc: SourceLoc


# Placeholders written by BodyBuilder.container and replaced by `finish` once the timeline is known.
def box_tokens(n: int) -> tuple[str, str]:
    return f"\x00CB:{n}\x00", f"\x00CG:{n}\x00"  # end of the start tag, end of the style value


def column_tokens(c: int) -> tuple[str, str, str, str]:
    return f"\x00CS:{c}\x00", f"\x00CA:{c}\x00", f"\x00CI:{c}\x00", f"\x00CE:{c}\x00"  # class, tag, open, close


_TOKEN_RE = re.compile(r"\x00C[BGSAIE]:\d+\x00")


def finish(html_: str, boxes: list[ColumnBox], cols: list[ColumnInfo], named: set[str]) -> str:
    """Replace the column placeholders of ``html_``. A box is *tracked* when one of its columns is named in
    a ``width`` cue (``named``) or collapsed by its attribute: it gets ``data-lt-cols``, its columns
    ``data-lt-col``, ``data-lt-flex`` and the ``lt-column-in`` wrapper (spec 10.4). Other columns render
    as before the placeholders existed."""
    if "\x00C" not in html_:
        return html_
    tracked = set()
    for b in boxes:
        if b.in_notes:
            continue
        if any(cols[c].flex == SHUT or (cols[c].id is not None and cols[c].id in named) for c in b.columns):
            tracked.add(b.index)
    subs: dict[str, str] = {}
    for b in boxes:
        on = b.index in tracked
        end, gap = box_tokens(b.index)
        subs[end] = f' data-lt-cols="" data-lt-duration="{b.duration}"' if on else ""
        subs[gap] = f";--lt-gap:{b.gap}" if on and b.gap else ""
    for c in cols:
        on = c.box is not None and c.box in tracked
        cls, tag, open_, close = column_tokens(c.index)
        shut = on and c.flex == SHUT
        subs[cls] = " lt-col-shut" if shut else ""
        subs[tag] = (f' data-lt-col="{c.id or ""}" data-lt-flex="{c.flex or ""}"' + (" inert" if shut else "")) if on else ""
        subs[open_] = '<div class="lt-column-in">' if on else ""
        subs[close] = "</div>" if on else ""
    return _TOKEN_RE.sub(lambda m: subs.get(m.group(0), ""), html_)
