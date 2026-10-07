"""Timeline blocks: parsing (spec 3.15) and step compilation (spec 6.3)."""
from __future__ import annotations

import re

from .columns import WIDTH_HELP, column_flex
from .diagnostics import Diagnostics, SourceLoc
from .model import Slide, TimelineAssign, TimelineLine, TimelinePos, Track

_END = r"end(?:\s*-\s*\d+)?"  # `end` or `end-N`
_ASSIGN_RE = re.compile(
    r"\s*(?P<track>[A-Za-z0-9][A-Za-z0-9_-]*)\s+"
    rf"(?:(?P<start>\d+|{_END})?\s*\.\.\s*(?P<stop>[+-]?\d+|{_END})(?:\s+by\s+(?P<by>\d+))?"
    rf"|(?P<pos>[+-]?\d+|{_END}))\s*\Z"
)
# A detour step (spec 6.4): `detour ID` alone on its line. `detour` is therefore not usable as a track name.
_DETOUR_RE = re.compile(r"\s*detour\s+(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)(?P<blocking>\s+blocking)?\s*\Z")
# A `width` cue (spec 3.15): `width COL=W ...`. `width` is therefore not usable as a track name either.
_WIDTH_RE = re.compile(r"\s*width(?:\s+(?P<rest>.*?))?\s*\Z", re.S)
_COL_WIDTH_RE = re.compile(r"(?P<col>[A-Za-z0-9][A-Za-z0-9_-]*)=(?P<w>\S+)\Z")
COLUMNS_TRACK = "@columns"


def _width(m: re.Match, loc: SourceLoc, diags: Diagnostics) -> TimelineAssign | None:
    rest = m.group("rest") or ""
    if not rest:
        diags.error("LT064", "a width cue names columns and their widths: `width COL=W ...`", loc)
        return None
    widths: list[tuple[str, str]] = []
    for item in rest.split():
        cm = _COL_WIDTH_RE.match(item)
        if not cm:
            diags.error("LT064", f"{item!r} in a width cue: write COL=W, the id of a column and its width", loc)
            return None
        flex = column_flex(cm.group("w"))
        if flex is None:
            diags.error("LT064", f"{item!r}: {WIDTH_HELP}", loc)
            return None
        if any(c == cm.group("col") for c, _ in widths):
            diags.error("LT064", f"column {cm.group('col')!r} is named twice in one width cue", loc)
            return None
        widths.append((cm.group("col"), flex))
    return TimelineAssign(COLUMNS_TRACK, "width", TimelinePos("int", 0), widths=widths)


def _pos(text: str) -> TimelinePos:
    text = text.replace(" ", "").replace("\t", "")
    if text.startswith("end"):
        return TimelinePos("end", int(text[4:]) if len(text) > 3 else 0)
    if text[0] in "+-":
        return TimelinePos("rel", int(text))
    return TimelinePos("int", int(text))


def _assign(part: str, m: re.Match, loc: SourceLoc, diags: Diagnostics) -> TimelineAssign | None:
    tr = m.group("track")
    if m.group("pos") is not None:
        return TimelineAssign(tr, "pos", _pos(m.group("pos")))
    start = _pos(m.group("start")) if m.group("start") is not None else None
    stop = _pos(m.group("stop"))
    if start is not None and stop.kind == "rel":
        diags.error("LT049", f"{part.strip()!r}: a relative stop needs an open range (`..{m.group('stop')}`, from the "
                             "current position); after an explicit start it would be ambiguous", loc)
        return None
    by = int(m.group("by")) if m.group("by") is not None else 1
    if by < 1:
        diags.error("LT049", f"{part.strip()!r}: the stride of `by K` must be at least 1", loc)
        return None
    return TimelineAssign(tr, "range", stop, start, by)


def parse_timeline(body: str, first_line: int, file, diags: Diagnostics) -> list[TimelineLine]:
    lines: list[TimelineLine] = []
    for i, raw in enumerate(body.split("\n")):
        loc = SourceLoc(file, first_line + i, 1)
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue
        dm = _DETOUR_RE.match(text)
        if dm:
            lines.append(TimelineLine([], loc, detour=dm.group("id"), blocking=bool(dm.group("blocking"))))
            continue
        if re.match(r"\s*detour\s", text):
            diags.error("LT054", "a detour step is written `detour ID` or `detour ID blocking`, alone on its line", loc)
            continue
        assigns: list[TimelineAssign] = []
        ok = True
        for part in text.split(","):
            wm = _WIDTH_RE.match(part)
            if wm:
                a = _width(wm, loc, diags)
                if a is None:
                    ok = False
                    break
                assigns.append(a)
                continue
            m = _ASSIGN_RE.match(part)
            if not m:
                if re.search(r"\sby\s", part) and ".." not in part:
                    msg = f"{part.strip()!r}: a stride `by K` follows a range (`a..b by K` or `..b by K`)"
                else:
                    msg = f"cannot parse timeline cue {part.strip()!r}"
                diags.error("LT049", msg, loc)
                ok = False
                break
            a = _assign(part, m, loc, diags)
            if a is None:
                ok = False
                break
            assigns.append(a)
        if not ok:
            continue
        tracks = [a.track for a in assigns]
        if tracks.count(COLUMNS_TRACK) > 1:
            diags.error("LT064", "one width cue per line: name every column in it (`width a=0 b=2fr`)", loc)
            continue
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
            lines = [TimelineLine([TimelineAssign(t.id, "range", TimelinePos("end"), TimelinePos("int", 1))], slide.loc)]
        else:
            lines = []

    detour_ids = {d.id for d in slide.detours}
    step_detours: dict[int, dict] = {}
    pos = {t: 0 for t in indep_ids}
    # The columns track (spec 6.1): its positions are width states, made by the `width` cues as they come.
    columns = next((t for t in tracks if t.kind == "columns"), None)
    states: list[dict[str, str]] = [dict(slide.column_init)]
    if columns is not None:
        pos[columns.id] = 0
        last[columns.id] = 0
    table = [dict(pos)]
    for line in lines:
        if line.detour is not None:
            if line.detour not in detour_ids:
                diags.error("LT054", f"detour {line.detour!r} is not a detour of this slide", line.loc)
                continue
            table.append(dict(table[-1]))  # the detour step shows the same positions as the step before it
            step_detours[len(table) - 1] = {"id": line.detour, "blocking": line.blocking}
            continue
        bad = False
        assigns = []
        for a in line.assigns:
            if a.kind == "width":
                if columns is None:  # its columns were refused (LT064)
                    bad = True
                    continue
                state = dict(states[pos[columns.id]])  # resolved against the state before the line
                state.update(a.widths)
                if state not in states:
                    states.append(state)
                    last[columns.id] = len(states) - 1
                assigns.append(TimelineAssign(columns.id, "pos", TimelinePos("int", states.index(state))))
                continue
            assigns.append(a)
            if a.track not in indep_ids:
                why = "is a follower" if a.track in by_id else "is not a track of this slide"
                diags.error("LT024", f"timeline track {a.track!r} {why}", line.loc)
                bad = True
        if bad:
            continue
        line = TimelineLine(assigns, line.loc)
        for cue in _expand(line, pos, last, diags):
            pos.update(cue)
            if pos == table[-1]:
                diags.warn("LT030", "timeline cue changes nothing", line.loc)
            table.append(dict(pos))
    for t in independent:
        if all(row[t.id] == 0 for row in table):
            diags.warn("LT026", f"track {t.id!r} is never advanced", slide.timeline_loc or slide.loc)

    # `at=N` detours (spec 6.4): a detour step inserted after step N of the table built so far.
    placed = sorted((d for d in slide.detours if d.at is not None), key=lambda d: (d.at, d.index_in_origin))
    if placed and slide.timeline is not None:
        for d in placed:
            diags.error("LT054", "at= cannot be combined with a timeline; write `detour ID` in the timeline instead",
                        d.loc)
    elif placed:
        last_step = len(table) - 1
        inserted = 0
        for d in placed:
            if not 0 <= d.at <= last_step:
                diags.error("LT054", f"at={d.at} is out of range: the slide has steps 0..{last_step}", d.loc)
                continue
            k = d.at + 1 + inserted
            table.insert(k, dict(table[k - 1]))
            step_detours[k] = {"id": d.id, "blocking": d.blocking}
            inserted += 1
    slide.step_detours = step_detours
    slide.checkpoints = checkpoints(table, step_detours)

    # `badge=step|next` ties a badge to a detour step (spec 3.9), checked for every badge of the detour,
    # placed or not; `at=` detours already reported by LT054 are left out so that one mistake gives one error.
    stepped = {v["id"] for v in step_detours.values()}
    for d in slide.detours:
        if d.id in stepped or d.at is not None:
            continue
        waiting = {loc: mode for mode, loc in d.badges if mode}
        if d.badge_mode:  # the detour's own mode, even when every placed badge overrides it
            waiting.setdefault(d.loc, d.badge_mode)
        for loc, mode in waiting.items():
            diags.error("LT055", f"badge={mode} needs a detour step: give the detour {d.id!r} at=N "
                                 f"or name it in a `detour {d.id}` timeline line", loc)

    def value(row, t: Track) -> int:
        seen = set()
        while t.follow is not None and t.id not in seen:
            seen.add(t.id)
            t = by_id.get(t.follow, t)
        return row.get(t.id, 0)

    slide.positions = [[value(row, t) for t in tracks] for row in table]
    if columns is not None:
        columns.positions = len(states)
        slide.column_states = states


def checkpoints(table: list[dict[str, int]], step_detours: dict[int, dict]) -> list[int]:
    """The checkpoints of a step table (spec 6.5): the last step of each run of steps of the same kind,
    and the last step. A step's kind is the set of tracks it changes; the rows hold the independent
    tracks and the columns track, never followers. A step that changes nothing (a detour step, an LT030
    cue) belongs to no run, and a blocking detour step ends the run before it."""
    last = len(table) - 1
    found: list[int] = []
    run_kind: frozenset[str] | None = None
    run_end = 0
    for i in range(1, len(table)):
        d = step_detours.get(i)
        if d is not None and d["blocking"]:
            if run_kind is not None:
                found.append(run_end)
            run_kind = None
            continue
        kind = frozenset(t for t in table[i] if table[i][t] != table[i - 1].get(t))
        if not kind:
            continue
        if run_kind is not None and kind != run_kind:
            found.append(run_end)
        run_kind, run_end = kind, i
    if run_kind is not None and run_end != last:
        found.append(run_end)
    return sorted(set(found) | {last})


def _value(p: TimelinePos, cur: int, last: int) -> int:
    if p.kind == "int":
        return p.n
    if p.kind == "end":
        return last - p.n
    return cur + p.n  # "rel"


def _range_values(a: TimelineAssign, cur: int, last: int) -> list[int]:
    """The positions of a range (spec 6.3): from its start to its stop every ``by`` positions, the stop
    always included; an open range starts from the current position, which it leaves out."""
    stop = _value(a.stop, cur, last)
    first = cur if a.start is None else _value(a.start, cur, last)
    step = a.by if stop >= first else -a.by
    values = list(range(first, stop, step)) + [stop]
    return values[1:] if a.start is None else values


def _expand(line: TimelineLine, pos: dict[str, int], last: dict[str, int], diags: Diagnostics) -> list[dict[str, int]]:
    """The cues of a timeline line, as the positions each one assigns. Every value is resolved against the
    positions before the line: a track appears once per line, so nothing on the line moves it earlier."""
    others = {a.track: _value(a.stop, pos[a.track], last[a.track]) for a in line.assigns if a.kind == "pos"}
    ranges = {a.track: _range_values(a, pos[a.track], last[a.track]) for a in line.assigns if a.kind == "range"}
    lengths = {len(v) for v in ranges.values()}
    if len(lengths) > 1:
        sizes = ", ".join(f"{t} {len(v)}" for t, v in ranges.items())
        diags.error("LT031", f"ranges of different lengths on one line ({sizes} steps); ranges on one line advance "
                             "together and must give the same number of steps", line.loc)
        return []
    # Out of range (LT025): one error per line, at the first bad value.
    for t, values in [(t, [v]) for t, v in others.items()] + list(ranges.items()):
        bad = next((v for v in values if not 0 <= v <= last[t]), None)
        if bad is not None:
            diags.error("LT025", f"position {bad} out of range 0..{last[t]} for track {t!r} "
                                 f"(the track is at {pos[t]} before this line)", line.loc)
            return []  # the line adds no step, rather than clamped cues that would only add warnings
    if not ranges:
        return [others]
    n = lengths.pop()
    if n == 0:
        what = "one range is" if len(ranges) == 1 else "the ranges are"
        tail = "" if others else "; the line adds no step"
        diags.warn("LT030", f"{what} empty: the track is already at its stop{tail}", line.loc)
        return [others] if others else []
    cues = []
    for i in range(n):
        cue = dict(others) if i == 0 else {}
        for t, values in ranges.items():
            cue[t] = values[i]
        cues.append(cue)
    return cues
