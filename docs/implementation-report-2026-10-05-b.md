# Implementation report: timeline ranges (Lattice 0.17.0, 2026-10-05)

A timeline range can now start where its track is (`reveal ..end`, `trace ..+2`), positions can be counted from the last one (`end-1`), a range can keep every `K`-th position (`by K`), and several ranges on one line advance together. The rules are in spec 3.15, 6.3 and 12 (with 15); the rationale is report section 3 (the paragraph on steps) and decision 26. The design was proposed and agreed before implementation (project doc `claude/v0.17-design.md`, with Olivier's answers). This is the second release of the day, hence the `-b` in the name (SKILL.md, release step 3).

## 1. What was found first

- A range had to start with an integer (`a..b` or `a..end`) and always started there: after `trace 3`, the line `trace 1..end` jumped back to 1. `+N` was one cue that jumped `N` positions. Nothing said "from where the track is", and `reveal ..end`, `reveal ..+2` and `reveal +1..end` were all LT049.
- The current position of every track is known when a line is compiled (`compile_steps` already kept it in `pos`), so the new forms are resolved at build time; the deck JSON and the runtime are unchanged.

## 2. What was built

- **Model** (`model.py`): `TimelineAssign` now has `kind` `pos` or `range`, a `stop` and an optional `start` (`None` is an open range), both `TimelinePos` (`int`, `end` with an offset, or `rel`), and a stride `by`. Nothing else used the old fields.
- **Parsing** (`timeline.py`): one regex accepts `[START] .. STOP [by K]` and the single positions, with `end-N` wherever `end` was accepted (spaces allowed, as around `..`). LT049 for a relative stop after an explicit start (`2..+3`, ambiguous, as agreed), for `by 0`, for `by K` without a range, and, since they are not in the grammar, for relative starts (`+1..end`, as agreed). The parse-time LT031 check is gone.
- **Expansion** (`_expand`, `_range_values`): every value of a line is resolved against the positions before the line (a track appears once per line, so nothing on the line moves it first). A range walks from its start to its stop every `K` positions and always ends on the stop; an open range starts from the current position and leaves it out, so `t ..+N` gives `N` cues. Ranges on one line must have the same length (LT031, whose message gives each length) and cue `i` takes the `i`-th value of each; other assignments go in the first cue, as before. An empty open range is warning LT030 and adds no step, or one step holding the line's other assignments (as agreed). A value out of range is LT025 once per line, and the line then adds no step (before, each out-of-range cue was reported and clamped, which also produced LT030 warnings).
- **Docs**: spec 3.15 (grammar, example, a summary paragraph), 6.3 (pseudo-code and the rules of `resolve` and `expand`), 12 (LT030, LT031, LT049), 15 (0.17 row); README (timeline row, version); manual: a new live slide "Timeline ranges" after "Timelines" (a bubble sort and five bullets driven by every new form) and `end-2` on "Timelines", LT031 in the diagnostics table; design report (paragraph on steps, roadmap v0.17, decision 26); SKILL.md (structure, tests table, the `-b` report name); todo; archive (the 0.16.0 report copied to `docs/archive/`). Version 0.17.0.

## 3. Verification

- `pytest -rs`: 267 passed, no skips, in Chromium (33 new tests in `test_steps.py`): every form on the reveal track (open, relative, backward, absolute stops both ways, `end-N`, spaces, strides on closed and open ranges, `a..a`), open ranges on a component track with its follower and with other assignments, lockstep ranges in both directions, an open range after a detour step, empty open ranges with and without other assignments, and the errors (LT025 once per line, LT049, LT031). The LT031 case of `test_timeline_errors` now uses ranges of different lengths, since two ranges are no longer an error by themselves.
- **Existing decks**: every example rebuilt with 0.17.0 is identical to its 0.16.0 build apart from the version, the deck hash and the random clip-path ids of matplotlib plots (examples 02 and 03); the manual differs by its new slide and the two edited lines.
- **Looked at** (Chromium, 1280x720): "Timeline ranges" at steps 0, 4 and 9, and "Timelines" at its last step. `python scripts/build_examples.py` rebuilt every deck; `lattice check --strict` on the manual and `check_docs.py` pass.

## 4. Not verified, and left open

- Only Chromium was used; the change is build-time only, so the browsers see the same step tables as before.
- The examples and the rest of the manual keep their timelines as written (see the todo).
- `docs/implementation-report-2026-10-05.md` is copied to `docs/archive/`; the copy left in `docs/` (with the 10-03 and 10-04 ones) needs a `git rm`.
