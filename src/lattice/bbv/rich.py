"""Inline markup for the captions, notes and panel entries of the versioning and abstract
interpretation animations (spec section 9.5, "Rich text").

A caption is a string in which a span ```kind:text``` names what ``text`` is, so that the runtime can
style it: ``op`` (the operation the frame shows, drawn as a badge), ``tag`` (a secondary operation),
``v`` (a version or block label, drawn as a chip in the origin colour of its block: ``v:A2|find/A``),
``var`` (a variable), ``ty`` (an abstract type, with its interval), ``code`` (an instruction or a
test) and ``rm`` (a test that was removed). Everything else is plain text. ``plain`` strips the markup
for tooltips and tests. Backticks never occur in programs, contexts or labels, which is what makes
the markup unambiguous.
"""
from __future__ import annotations

import re

SEP = " · "
_SPAN = re.compile(r"`(op|tag|v|var|ty|code|rm):([^`]*)`")


def span(kind: str, text) -> str:
    return f"`{kind}:{text}`"


def op(name: str) -> str:
    """The operation of the frame, first in every caption."""
    return span("op", name)


def tag(name: str) -> str:
    return span("tag", name)


def ver(label: str, block: str | None = None) -> str:
    """A version (or block) label; ``block`` is the origin block key that gives its colour."""
    return span("v", f"{label}|{block}" if block else label)


def var(name: str) -> str:
    return span("var", name)


def ty(text) -> str:
    return span("ty", text)


def code(text: str) -> str:
    return span("code", text)


def struck(text: str) -> str:
    return span("rm", text)


def binding(name: str, type_text) -> str:
    """``x: fx`` with both parts marked."""
    return f"{var(name)}: {ty(type_text)}"


def context(lines) -> str:
    """A context (its ``name: type`` lines, or a Context) as marked bindings separated by dots."""
    if not isinstance(lines, (list, tuple)):
        lines = lines.lines()
    out = []
    for line in lines:
        name, sep, text = line.partition(": ")
        out.append(binding(name, text) if sep else line)
    return SEP.join(out)


def join(parts: list[str]) -> str:
    """Caption parts separated by dots, empty parts dropped."""
    return SEP.join(p for p in parts if p)


def plain(text: str) -> str:
    """The caption without its markup (labels lose their block key)."""
    return _SPAN.sub(lambda m: m.group(2).split("|", 1)[0] if m.group(1) == "v" else m.group(2), text or "")


def parse(text: str) -> list[tuple[str, str]]:
    """``[(kind, text)]`` with ``kind`` ``""`` for plain runs; the runtime does the same split."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _SPAN.finditer(text or ""):
        if m.start() > pos:
            out.append(("", text[pos:m.start()]))
        out.append((m.group(1), m.group(2)))
        pos = m.end()
    if pos < len(text or ""):
        out.append(("", text[pos:]))
    return out
