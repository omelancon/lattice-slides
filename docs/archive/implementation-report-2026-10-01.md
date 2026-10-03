# Implementation report: Lattice 0.6.0 (2026-10-01)

Five work items on navigation, the presenter view and a new component. What shipped, the decisions taken on the way, how it was verified, and what to sync. The rules now live in the spec (sections cited below); the rationale is in the design report (3.12, decisions 14 and 15).

## 1. What shipped

### Bug: Left with an empty history (spec 7.1, 7.2)

`prev()` in `lattice.js` no longer stops at "Start of history". With `H` empty it goes to the structural predecessor `pred(s)` at its last step, **without pushing anything**, so Left keeps walking backward. `pred(s)` is the first of: the slide before `s` in the active tour; the slide before `s` on the main path; a slide whose `next` is `s` (same scope first, then document order); a slide with a branch option to `s`; the origin of the detour whose entry is `s`. A slide with no predecessor (the start, a slide only reachable by link) flashes "No previous slide". Right afterwards pushes a forward entry as before, and Left then pops it. Browser test `test_prev_without_history_walks_the_structure`.

### Presenter view: Keybindings section (spec 7.5)

Right after Moves, a small uppercase title "Keybindings" and a compact two-column list (13 px, muted) of every action in `deck.keys` with its keys as `<kbd>` (Space, arrow glyphs, `Shift+→`) and a short description, plus a fixed row for the digit keys of branch options and detours. Built once in `buildPresenter`, so `keys:` overrides from the front matter appear as bound. Asserted in `test_presenter_preview_and_scrubber`.

### Skip keys (spec 7.2 SKIP, 7.6)

Three new actions in `DEFAULT_KEYS`: `skip-forward` (`Shift+ArrowRight`, +10 steps), `skip-back` (`Shift+ArrowLeft`, -10) and `last-step` (`End`). They are step moves: clamped to the slide, never leaving it, never touching history. As asked, the intermediate steps are **played in rapid succession** (`playSteps` in `lattice.js`: one single-step `go` per tick, 30 to 90 ms apart depending on the distance, so runtimes receive `animate: true` and the animation is seen rather than skipped); any key press cancels a running playback. Bindings gained the `Shift+KEY` notation: `onKey` tries `Shift+<key>` first, then the plain key, so existing letter bindings keep working. README key table updated. Browser test `test_skip_keys_play_steps_within_the_slide` checks the playback (the state is mid-way right after the key press), the clamping and that history stays empty.

### Detour steps (spec 3.9, 3.15, 6.4, 7.2, 11.2, 11.5, 12)

A step of a slide can enter a detour. Both syntaxes you chose are in:

- a timeline line `detour ID` between cues (`detour` is therefore reserved as a line keyword, not a track name);
- the attribute `at=N` on the detour container, for slides without a timeline: the detour step is inserted after step `N` of the table compiled from the tracks (several `at` detours are inserted in increasing order of `N`; `N` counts steps before any insertion).

The row of a detour step repeats the previous row, so nothing changes on the slide. `Slide.step_detours` and the deck JSON field `stepDetours` carry the mapping. Runtime: NEXT arriving on the step enters the detour, recording the excursion at that step, so Up or the end of the detour lands on it and the next Right performs the following step; PREV skips detour steps (no dead key press); reaching the step by the scrubber, the hash or a sync does nothing (steps stay positions). The presenter preview shows the detour's entry slide with the label "detour: Label", the Moves list says the same, the HUD draws the step as a small diamond, and the PDF export leaves detour steps out of `all`. New diagnostic **LT054** covers an unknown detour in a timeline, `at` out of range, `at` combined with a timeline, and a malformed `detour` line (`at=x` is LT009 like other malformed attributes). Tests: `test_detour_steps`, `test_detour_step_errors` (build), `test_detour_step_enters_and_returns` (browser). Example 01 uses `at=1` on the invariant detour of the slide "Nothing here is linear" (note added to its speaker notes).

### The `arrow` component (spec 8.8, 8.9)

` ```arrow {to=ID ...} ` draws an arrow over the slide, pointing at an element. Options: `to` (an element id, or a CSS selector such as `.lt-line[data-line="4"]`, resolved inside the slide), `from` (another element: the arrow runs edge to edge between the two boxes), `angle` (degrees, from the target toward the tail, counterclockwise, 0 pointing right), `length` (120), `label`, `color` (CSS color or a theme token `accent`, `detour`, `muted`, `ink`), `width` (4), `curve` (bend as a fraction of the length), and a body `steps:` list that makes the block a track with one position per target (each entry can override `to`, `from`, `angle`, `length`, `label`; `from: ""` drops the block's `from`). On a single-step move the arrow glides between geometries; other moves place it directly. `{.reveal}` before the block works as for any block.

As you asked, there is **no computed default direction**: when neither `from` nor `angle` is given, the angle is the constant `ARROW_DEFAULT_ANGLE = 315` in `components/visual.py`. Under the convention documented in the spec (the direction from the target toward the tail, counterclockwise, 0 to the right), 315 means the arrow comes from the lower right and points up-left. I kept the convention I had described in the design; if you meant the other common reading (315 as "from the upper right"), either change the constant to 45 or say so and I will flip the convention, both are one-line changes.

Geometry is measured in the browser (`runtime/components/arrow.js`), the one runtime layout in Lattice and recorded as such (SKILL invariant, decision 14): the wrapper is moved out of the body onto the slide section as an overlay (absolute, full slide, no pointer events), boxes are read with `getBoundingClientRect` in slide units (so the window scale does not matter), the box of a target is the extent of its contents (a heading or a code line is pointed at its text, not its full row), the tail is shortened when it would leave the slide and the label is pushed back inside. Re-measured on enter, on every step, on resize, when the slide body changes size and once fonts are loaded. Print mode clones the overlay with the slide, and the per-page id renaming already handles the arrowhead marker (checked on a PDF of example 01). A bare id that no element of the slide carries is warning LT046 at build time (`render.py`); a selector not found at runtime hides the arrow with a console warning. The SVG classes are `lt-arrow-box`, `lt-arrow-line` and `lt-arrow-text` because `.lt-arrow` already styles the graph animation's arrowheads (that collision cost one filled lens-shaped arrow before I found it). Tests: `test_arrow_component`, `test_arrow_needs_a_target` (build), `test_arrow_runtime_points_at_its_targets` (browser: overlay placement, head at the target's edge for 315 and 270 degrees, the step move). Example 01's code slide now has a three-step arrow from the right column into the code.

### Addendum: blocking detour steps and `skip-detour` (same day)

Asked after the report was first written. A multi-step (Shift+Right, Shift+Left, End) passes through detour steps without entering them, as recorded in the SKIP row of spec 7.2; that stays the default. Two additions:

- A detour step can be **blocking**: `blocking=true` on the detour container (with `at=`), or `detour ID blocking` on a timeline line. A forward playback stops in front of it and flashes "Cannot step detour" (backward playback is not affected, since Left skips detour steps anyway). `stepDetours` entries are now objects `{"id", "blocking"}`, and `Slide.step_detours` holds the same dicts; `blocking=maybe` is LT009 like any malformed boolean.
- A `skip-detour` action, bound to `Shift+ArrowDown`, steps over the detour step(s) that follow the current step without entering them (a no-op with a flash when the next step is not a detour step). It is the only way past a blocking detour step without entering it, and it works on any detour step. The Moves list shows it under the "detour: Label" line (marked "(blocking)" when it is), and the Keybindings section lists it.

Spec 3.8, 3.9, 3.15, 4, 6.4, 7.1, 7.2 (SKIP, new SKIP-DETOUR), 7.5, 7.6, 11.2 and 15; README (detour row, timeline row, keys); report 3.12 and decision 15. Tests extended in `test_detour_steps`, `test_detour_step_errors` and `test_detour_step_enters_and_returns` (blocking stops End and Shift+Right, the flash text, the explicit skip, Right still enters). Suite: 102 passed; examples rebuilt; `check_docs.py` clean.

## 2. Decisions

- Items in one unit each, spec first, then code, test, README (SKILL workflow). Version bumped to **0.6.0** (features: minor) everywhere; `check_docs.py` reports 0 problems.
- `pred` prefers the tour, then the main path, then `next` edges in the same scope: at a merge point this picks the main-path predecessor, which is what a presenter walking back expects.
- Skip playback interval: `max(30, min(90, 1000 / n))` ms, so ten steps take about a second and `End` on a long animation stays under a second.
- Detour steps are entered only by NEXT (never by PREV, scrubbing, the hash or a sync) to keep "positions, not events". PREV skips them. `at` and a timeline on the same slide is an error rather than a merge rule.
- `arrow` keeps its natural name: the Pygments `arrow` lexer is obscure, and registered names already win over lexers (spec 3.13). Decision 14 records it.
- The arrow component is a documented exception to "build time does the work": measurement only, no layout decisions (decision 14, SKILL invariant).

## 3. Verification

- `pytest`: 102 passed (94 before), about 36 s, in Chromium 141 (Playwright) in this workspace. Firefox is not available here, so the arrow was not checked in Firefox (SKILL pitfalls); its geometry uses only `getBoundingClientRect`, `Range.getBoundingClientRect` and `getBBox`, which both engines support.
- `python scripts/build_examples.py`: all seven decks rebuilt (they embed the new runtime, which is why every `talk.html` changed).
- Screenshots looked at: the presenter view with the Keybindings section and a detour step in the preview and the Moves list; the arrow test deck (default angle, `from` with a curve, step moves, a reveal-hidden arrow); example 01's code slide at its three steps; pages 7 to 9 of `lattice pdf examples/01-getting-started/talk.md --steps all` (arrow printed on both steps of the code slide).
- Documentation pass: README, spec, report and SKILL reread for the changed topics; spec 1 (terminology), 3.8, 3.9, 3.15, 4, 6.4 (new), 7.1, 7.2, 7.5, 7.6, 8.8, 8.9 (new), 11.2, 11.5, 12, 15; report 3.12 (new), roadmap v0.6, decisions 14 and 15; SKILL map, structure, invariants, test table, pitfalls, highest diagnostic LT054.
- Cleaned `.lattice-cache/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/` in the workspace copy (release step 4).

## 4. Files to sync to your folder

Changed: `README.md`, `pyproject.toml`, `src/lattice/__init__.py`, `src/lattice/model.py`, `src/lattice/parser.py`, `src/lattice/timeline.py`, `src/lattice/emit.py`, `src/lattice/pdf.py`, `src/lattice/render.py`, `src/lattice/components/visual.py`, `src/lattice/runtime/lattice.js`, `src/lattice/runtime/lattice.css`, `tests/test_steps.py`, `tests/test_output.py`, `tests/test_runtime.py`, `examples/01-getting-started/talk.md`, every `examples/*/talk.html`, `docs/spec.md`, `docs/design-report.md`, `docs/SKILL.md`.

New: `src/lattice/runtime/components/arrow.js`, `docs/implementation-report-2026-10-01.md` (this file).

Renamed: `docs/deprecated_and_archives/` to `docs/archive/` (contents untouched; its `reading-notes.md` still cites the older `docs/this_phase/` paths, left as is since it is an archive).

## 5. Left for later

- A Firefox look at the arrow and the Keybindings grid.
- Arrow labels placed beside the middle of a `from` arrow can overlap text when the two boxes are close; `curve` moves them, and a `label_at` option (tail, middle, head) would be a small addition.
- Detour steps and tours: a detour step inside a tour enters the detour as anywhere else; the tour successor applies only at the last step, as before.
