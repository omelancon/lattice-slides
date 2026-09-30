"""Timeline blocks: parsing (spec 3.15) and step compilation (spec 6.3)."""
from __future__ import annotations

import re

from .diagnostics import Diagnostics, SourceLoc
from .model import Slide, TimelineAssign, TimelineLine, Track

_ASSIGN_RE = re.compile(
    r"\s*(?P<track>[A-Za-z0-9][A-Za-z0-9_-]*)\s+"
    r"(?:(?P<a>\d+)\s*\.\.\s*(?P<b>\d+|end)|(?P<sign>[+-])(?P<rel>\d+)|(?P<abs>\d+)|(?P<end>end))\s*\Z"
)


def parse_timeline(body: str, first_line: int, file, diags: Diagnostics) -> list[TimelineLine]:
    lines: list[TimelineLine] = []
    for i, raw in enumerate(body.split("\n")):
        loc = SourceLoc(file, first_line + i, 1)
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue
        assigns: list[TimelineAssign] = []
        ok = True
        for part in text.split(","):
            m = _ASSIGN_RE.match(part)
            if not m:
                diags.error("LT049", f"cannot parse timeline cue {part.strip()!r}", loc)
                ok = False
                break
            tr = m.group("track")
            if m.group("a") is not None:
                b = None if m.group("b") == "end" else int(m.group("b"))
                assigns.append(TimelineAssign(tr, "range", int(m.group("a")), b))
            elif m.group("rel") is not None:
                n = int(m.group("rel"))
                assigns.append(TimelineAssign(tr, "rel", n if m.group("sign") == "+" else -n))
            elif m.group("abs") is not None:
                assigns.append(TimelineAssign(tr, "abs", int(m.group("abs"))))
            else:
                assigns.append(TimelineAssign(tr, "end"))
        if not ok:
            continue
        if sum(1 for a in assigns if a.kind == "range") > 1:
            diags.error("LT031", "more than one range on a timeline line", loc)
            continue
        tracks = [a.track for a in assigns]
        if len(set(tracks)) != len(tracks):
            diags.error("LT049", "a track appears twice in the same cue", loc)
            continue
        lines.append(TimelineLine(assigns, loc))
    return lines


def compile_steps(slide: Slide, diags: Diagnostics) -> None:
    """Fill ``slide.positions`` from ``slide.tracks`` and ``slide.timeline``."""
    tracks = slide.tracks
    by_id = {t.id: t for t in tracks}
    independent = [t for t in tracks if t.follow is None and t.positions > 1]
    last = {t.id: t.positions - 1 for t in tracks}
    indep_ids = {t.id for t in independent}

    lines = slide.timeline
    if lines is None:
        if len(independent) >= 2:
            names = ", ".join(t.id for t in independent)
            diags.error("LT023", f"slide has several independent tracks ({names}) and no timeline", slide.loc)
            lines = []
        elif len(independent) == 1:
            t = independent[0]
            lines = [TimelineLine([TimelineAssign(t.id, "range", 1, None)], slide.loc)]
        else:
            lines = []

    pos = {t: 0 for t in indep_ids}
    table = [dict(pos)]
    for line in lines:
        bad = False
        for a in line.assigns:
            if a.track not in indep_ids:
                why = "is a follower" if a.track in by_id else "is not a track of this slide"
                diags.error("LT024", f"timeline track {a.track!r} {why}", line.loc)
                bad = True
        if bad:
            continue
        for cue in _expand(line, last):
            for a in cue:
                cur = pos[a.track]
                if a.kind == "abs":
                    new = a.a
                elif a.kind == "rel":
                    new = cur + a.a
                else:  # "end"
                    new = last[a.track]
                if not 0 <= new <= last[a.track]:
                    diags.error("LT025", f"position {new} out of range 0..{last[a.track]} for track {a.track!r}",
                                line.loc)
                    new = max(0, min(new, last[a.track]))
                pos[a.track] = new
            if pos == table[-1]:
                diags.warn("LT030", "timeline cue changes nothing", line.loc)
            table.append(dict(pos))
    for t in independent:
        if all(row[t.id] == 0 for row in table):
            diags.warn("LT026", f"track {t.id!r} is never advanced", slide.timeline_loc or slide.loc)

    def value(row, t: Track) -> int:
        seen = set()
        while t.follow is not None and t.id not in seen:
            seen.add(t.id)
            t = by_id.get(t.follow, t)
        return row.get(t.id, 0)

    slide.positions = [[value(row, t) for t in tracks] for row in table]


def _expand(line: TimelineLine, last: dict[str, int]):
    rng = next((a for a in line.assigns if a.kind == "range"), None)
    if rng is None:
        yield line.assigns
        return
    others = [a for a in line.assigns if a is not rng]
    b = last[rng.track] if rng.b is None else rng.b
    step = 1 if b >= rng.a else -1
    for i, v in enumerate(range(rng.a, b + step, step)):
        cue = [TimelineAssign(rng.track, "abs", v)]
        yield (others + cue) if i == 0 else cue
