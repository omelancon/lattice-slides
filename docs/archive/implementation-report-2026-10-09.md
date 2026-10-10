# Implementation report: arrowheads on a straight end (Lattice 0.33.3, 2026-10-09)

The report of 0.33.0 to 0.33.2 is in `archive/implementation-report-2026-10-08-d.md`; this patch starts a new one, since that report was archived.

Olivier's review of 0.33.2: on the `fib` slide of `phd_defense/src/lv.md` (not touched), the arrowhead into `A2` did not line up with its edge. The cause predates 0.33.2 and shows most on lit edges and loops. Olivier's answers: the sizes proposed (10 by 7, 12 by 9 lit); between the lines of a wrapped rank, a leg as long as the gap allows; the last dash before an arrowhead left as it falls; release 0.33.3.

## 1. Diagnosis

- Markers were sized in stroke widths (7 widths long, the point of reference at 9 of 10), so an arrowhead was about 12.6 px long at rest and 24.5 px on a path, its back 11.3 or 22.1 px behind the end of the edge.
- An edge through a gutter entered its target from a slot 4 to 20 px from it, and the last rounded corner (radius 12) took half of that: the straight end was 2 to 10 px. The arrowhead pointed into the node while the edge under its back half still turned. Curves bend under it too, less visibly.
- Measured on the `fib` slide (done and path frames): 23 of 64 edges had a straight end shorter than the part of their arrowhead behind it, every edge through a gutter among them (H1 -> A2 and P1 -> A2: 6 px under 22).

## 2. What was built

- **Arrowheads** (`bbv.js`, `mount`): `markerUnits="userSpaceOnUse"`, `preserveAspectRatio="none"`, 10 by 7 for `default`, `gone` and `dim`, 12 by 9 for `new`, `active` and `path` (`ARROW`, `ARROW_LIT`).
- **The straight leg** (`LEG` = 13 px): `polyline` rounds its last corner only as far as leaves that leg (a sharp corner when the last segment is shorter); `route` and `routeInBand` end their curves 13 px before the node (or half the distance, when shorter) and add a straight segment.
- **Slots** (`routesInGutters`): the runs out of a line take 6 to 38 % of the gap from it (`SLOT_OUT`), the runs into a line 30 to 62 % (`SLOT_IN`), a lone run into a line 46 % (`ENTRY_LONE`); the two parts of a rank gap never overlap. Slots are grouped by gap and by direction (in or out).
- **Layout** (`layout.py`): `MARGIN` 30 to 40 px, so that the runs into a first rank (up to 27 px out) stay inside the drawing; `END_GAP` 0.6 to 0.75 of a rank gap (33 px), so that the runs past the ends of the ranks lie beyond them. The proposal said 36 px; the end runs, which would have met the entry slots, asked for 40.

## 3. Effects

- Every versioning drawing is 20 px wider and taller (10 px per margin).
- `rank_wrap=auto` for `fib` in `TB` (the test case of 0.32): 3 bands draw 2.9 % larger than 2 (2.0 % in 0.33.2, just inside the 2 % tie that favours fewer bands), so `auto` now picks 3. The test checks the rule instead of the count. Olivier's `fib` slide keeps 2 bands.
- Between the lines of a wrapped rank (14 px) the leg is as long as the gap allows (4 to 9 px), as agreed.

## 4. Tests and verification

- `test_arrowheads_sit_on_a_straight_end` (new): marker units and sizes per state; on the `fib` deck of the loops test, at four steps and in the middle of a glide, every drawn edge stays on the line of its last half pixel for at least the part of its arrowhead behind the end. It fails on 0.33.2.
- `test_layout_margins_cover_back_edges` now checks that the entry slots, the end runs and the margin come in that order; `test_one_band_is_the_layout_without_bands` gains 20 px per side of its figure; `test_auto_takes_the_shape_of_the_box` checks the tie rule for `fib`.
- `pytest -rs`: 453 passed, none skipped (Firefox included). The `fib` slide measured again: 0 of 64 edges off their straight end (23 in 0.33.2); a zoomed screenshot of the arrow into `A2` before and after.
- Docs: spec 9.5 and 15, design report, `docs/SKILL.md` (tests, the bands pitfall), README and manual versions, `archive/README.md` (the archived report of 0.33), todo.

## 5. Left open

- The last dash of a dashed edge falls where its pattern ends, up to 7 px before the arrowhead (Olivier: leave it).
- No git commit (one new file, `docs/implementation-report-2026-10-09.md`: `git add` it; the rest `git add -u`).
