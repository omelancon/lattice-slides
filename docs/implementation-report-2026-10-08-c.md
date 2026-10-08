# Implementation report: bands of ranks (Lattice 0.32.0, 2026-10-08)

A versioning drawing puts every origin block of a function on a rank and packs its versions along it, so a function with many ranks gives a drawing much longer than wide (`TB`) or much wider than tall (`LR`); scaled to fit its box, its text shrank to 5 px on a loop of ten ranks (case A, `vector-print.bbv`, SBBV, `LR`) and to 2 or 3 px on a recursive `fib` (case B, `fib-call.bbv`, ΛV). The request asked for an option that cuts the ranks of a function into bands laid side by side, so that the drawing takes the shape of its box. The rules are in spec 9.5 (Bands of ranks), with 8.6, 8.8 and 15; the rationale is design decision 42. The design was reviewed by Olivier before the work (`claude/v0.32-design.md` in the project): one lane per target in a gutter, up to a largest gap beyond which the closest targets share; labels just after the source; `auto` aimed at the slide's content with fewer bands winning ties, the runtime choice of the count left for later; a following `bbv-cfg` takes its leader's cut; the options on `abstract-interp-anim` too; the clamp warning only when a count exceeds every function; version 0.32.0 with case A in the manual. During the work, after the first screenshots, he asked that the runs beside a rank not overlap either: they now take slots of their own.

## 1. What was built

- **Options** (`components/bbv.py`, on `bbv-anim`, `bbv-cfg` and `abstract-interp-anim`): `rank_wrap` (an integer >= 1 or `auto`, default 1), `rank_wraps: {FUNCTION: N | auto}`, `rank_flow: restart | snake`, `fit_aspect: "W:H"`. Component errors (LT022) for a count that is not an integer >= 1 nor `auto`, a `rank_wraps` key that is not a function of the program, a malformed `fit_aspect` (with a hint to quote it when YAML read `16:9` as a number); LT021 for `rank_flow`. Warnings (LT046): a `rank_wrap` larger than the ranks of every drawn function, a `rank_wraps` entry larger than its function's ranks, `fit_aspect` without `auto`.
- **Layout** (`bbv/layout.py`): `layout_frames` gains `rank_wrap`, `rank_wraps`, `rank_flow`, `fit`, `cuts`, `call_edges` and `notes`.
  - The extents of every rank across and along (maximum over the frames) are computed first; they do not depend on the cut.
  - `cut_ranks` cuts the ranks into N groups of consecutive ranks by dynamic programming: the longest band as short as possible, then the least sum of squares of the lengths.
  - Bands: columns (`TB`) or bands one under the other (`LR`), each as wide or tall as its widest rank, 48 px apart or more; ranks start again in each band; `snake` mirrors every second band. The function's name sits above its first band.
  - Gutters: the lanes of the gutter between two bands are the most targets of edges between bands it serves in a frame (forward edges use the gutter after their band, backward ones the gutter before), capped at 5 (`GUTTER_LANES`); the gap is `max(48, 28 + 5 (lanes - 1) + 14)` px, at most 62, below the 64 px between functions.
  - `auto`: coordinate descent over the functions with `auto`, counts 1 to min(ranks, 6), scale `min(W / width, H / height, 1.4)`, the smallest count within 2 % of the best. The box of a choice is computed from the extents only, so the search is cheap.
  - `box.rankWrap` (only when a function has two bands or more): per function the cut, the bands (extent along, lane, `flip`), the gutters (first lane, count, step), the gutters past the ends of the ranks (`top`, `bottom`), and per block its band, rank and extent; `box.gaps` gives the gaps between ranks and lines. With one band per function the data is the 0.31 data, byte for byte (checked on every program of the manual and both cases in `TB` and `LR` with `wrap` 4 and 2 before the tests were written).
- **Target box of `auto`** (`components/bbv.py`): the design width of the deck's `aspect` less the slide's padding (1136 px at 16:9), less the panel when it shows beside the drawing (`clamp(150 px, 22 %, 260 px)` and the 28 px gap), by `height` or 430 px; `fit_aspect` sets the aspect instead. The deck's `aspect` joins the render cache key (`render.py`), since it changes the result.
- **Following**: a `bbv-cfg` takes its leader's cut for a function whenever its own count for it equals the leader's (read from `leader.data["box"]["rankWrap"]`).
- **Runtime** (`bbv.js`), in an abstract frame (`a` across, `l` along, converted by `pt`), so that `TB` and `LR` share the code:
  - `routeInBand`: edges inside a band as before, along the band's own direction (a band that runs backwards swaps the sides of its nodes and what counts as a back edge), back edges on the band's lane.
  - `routesBetweenBands`: the edge steps out of its source into the free gap after its line (`lineGaps` reads the lines of the frame from the positions: between two lines of a wrapped rank, or after the rank), runs along it to its gutter, along the gutter to the gap before the target's line, and into the target. Bands in between are passed beyond the ends of their ranks (the shorter way).
  - `assignLanes`: one lane per target in a gutter, ordered so that the edge that travels farthest lies nearest the band it leaves; beyond the lanes, the two neighbouring targets closest to each other merge until the count fits.
  - Slots beside a rank (Olivier's request during the work): in the gap after a source's line, every edge leaving has its own slot; in the gap before a target's line, the edges into one target share theirs; slots are at most 5 px apart within 10 % to 45 % of the gap from the line, the run that travels farthest outermost.
  - Labels and the marks of parts sit 20 px into the run after the source (`LABEL_AFTER`), where `#t` and `#f` no longer collide with the labels of the curves leaving the same block.
- **Manual**: a new slide "Bands of ranks" (`bbv-bands`) on `user_manual/programs/vector-print.bbv` (case A, `LR`, `rank_wrap=2`), a row in "Versioning options". The options table no longer fitted its slide, so its rows were shortened, which also removes two `[[id|text]]` links whose `|` split their table cells (a 0.31 slip: the "paths" row ended at `[[bbv-paths`).
- **Docs**: spec 8.6, 8.8, 9.5 (Bands of ranks), 15; design report (decision 42, roadmap v0.32 and the runtime choice of the count under "Later"); README (`bbv-anim` and `bbv-cfg` rows, version); `docs/USER_SKILL.md` (a feature row, a "Rules that bite" line on `auto` in a column); `docs/SKILL.md` (structure, a pitfall on the abstract routing frame and the lane counts, test rows); todo; the 0.31 report copied to `docs/archive/` and listed in its README; version 0.32.0.

## 2. Results on the two cases

| Case | Options | Box (px) | Request's estimate | Cut (first ranks) | Lanes |
|---|---|---|---|---|---|
| A | `LR`, 1 band | 2753.4 x 488 | 2753 x 488 | | |
| A | `LR`, `rank_wrap=2` | 1412.2 x 851 | 1412 x 888 | 0, 5 | 4 |
| A | `TB`, `rank_wrap=2` | 1514.8 x 806 | 1522 x 806 | 0, 5 | 4 |
| B | `TB`, 1 band | 1850 x 2738 | 1850 x 2738 | | |
| B | `TB`, `rank_wraps: {fib: 2}` | 2881.8 x 1438 | 2889 x 1438 | 0, 9 | 4 |
| B | `LR`, `rank_wrap=2` | 2641.6 x 1664 | 2642 x 1696 | 0, 8 | 5 |

`auto` picks 2 bands for A in both directions (room 1136 x 480), 2 for B in `TB` (3 bands scale 1 % more, fewer bands win), 3 for B in `TB` with `show: [label, context]`; the request's "best" rows. Bands are as tall as their own widest rank, which is why case A `LR` is 851 px high rather than the estimate's 888.

**Snippets for your two slides:**

```markdown
```bbv-anim {#vp program="vector-print.bbv" algorithm=sbbv heuristic=arithmetic limit=2 intervals=true vector_bounds=false direction=LR height=480 rank_wrap=2}
show: [label, context, code]
thresholds: [0, 1, maxfix-1, maxfix]
```

```bbv-anim {#fib program="fib-call.bbv" algorithm=lv heuristic=arithmetic limit=3 entry=main direction=TB}
show: [label, context, code]
rank_wraps: {fib: 2}
```
```

In a column about 1050 px wide, `rank_wrap=auto` with `fit_aspect="1050:480"` gives the same 2 bands for case A. Case B stays small (about 0.3), as the request expected: up to six versions share a rank.

## 3. Verification

- `pytest -rs`: 408 passed, 1 skipped (the optional Firefox test), Chromium. Baseline before the work: 397 passed, same skip.
- New tests. `test_bbv.py`: `cut_ranks`; one band identical to the layout without bands (with the 0.31 box of case A pinned); both cases in both flows within 10 % of the estimates, no two live versions overlapping in any frame, every version in one band and inside its band's extent; `snake` order; gutter lanes and gaps; `auto` on both cases and a tall box; the options, errors and warnings in a deck, the three components; a follower taking its leader's cut, and its own cut with another count; `auto` against the deck's aspect, a panel, `panel_at=below`, `fit_aspect`, and the aspect in the cache key (this test fails with the old key). `test_runtime.py`: five banded drawings (A `LR`, A `LR` snake, A `TB` 3 snake, B `TB`, B `LR` snake with call edges) at three steps each and after an animated step: every edge between bands is sampled against the boxes of the live nodes (none crossed), and no two of them with different sources and targets share more than 6 px outside a gutter whose lanes are all taken; a path frame lights edges between bands; arrows at a version and at an edge between bands; the edge's mark just after its source; a block of a banded drawing enlarges; print mode loads without errors. Both checks were run against broken routing (edges between bands drawn as before; runs beside a rank without slots) and failed as they should.
- `check_docs.py`: 0 problems. Examples and manual rebuilt; `lattice check` of the manual without warnings.
- Screenshots (Chromium, 1280 x 720, after the last edit): the manual's "Bands of ranks" and "Versioning options"; cases A and B in both directions and both flows.

## 4. Not done, or left open

- The runtime choice of the count by the measured box (the request's stretch goal): on the roadmap.
- Edges between bands that are not neighbours pass the bands between them on one line, shared by every such edge.
- Inside a band, an edge that skips ranks is a curve as before, and may cross a block of the ranks it skips.
- Firefox was not available; the routes are SVG paths computed from positions, with nothing measured.
- No git commit.
