# Implementation report: columns that change width (Lattice 0.24.0, 2026-10-06)

A compiler slide often holds source code beside an analysis that needs the whole row while it runs. A step can now change the width of columns: a `width` cue in the timeline collapses a column (`width src=0`) or gives it another width, and a later cue brings it back, for the optimised code to morph in. The rules are in spec 3.8, 3.15, 6.1, 6.3, 8.9, 10.4, 11.2 and 12 (changelog row 0.24 in section 15); the rationale is design report section 3.16 and decision 33. The design and Olivier's answers are in the project doc `claude/v0.24-design.md`.

## 1. What was built

- **Syntax.** `width COL=W ...` is a part of a timeline cue: alone on its line it is one step; with other assignments (`width src=1fr, code 1`) it happens on the same step; with ranges in lockstep it applies in the first cue. `W` takes the values of the `width` attribute: `Nfr`, a CSS length, or `0`. `width` is reserved like `detour`. `width=0` on a column collapses it from step 0. `::: columns {duration=600}` sets the length of the motion (`0`: at once).
- **Build.**
  - `columns.py` (new): `column_flex` turns a width into the CSS `flex` the build writes (every zero is the collapsed `0 0 0px`).
  - `body.py`: records `columns` and `column` containers with placeholders. `finish_columns` checks the columns named by `width` cues, records the widths they start from (`Slide.column_init`), then marks the tracked containers: those with a named or collapsed column get `data-lt-cols`, `data-lt-duration` and `--lt-gap`, and each of their columns gets `data-lt-col`, `data-lt-flex`, the `lt-column-in` wrapper, and `lt-col-shut` plus `inert` when it is collapsed. Other columns render byte for byte as before (checked on the examples and the manual).
  - `timeline.py`: parses the cue and compiles it as an assignment of the columns track (`@columns`, kind `columns`, added by `render.py`). Each cue makes a new state from the state before its line; a state seen before takes its position, and a cue that changes nothing is LT030.
  - `emit.py`: writes the states as `SlideJSON.columns`.
- **LT064** (new, error):
  - an invalid width, in an attribute or a cue (an invalid `width=` attribute used to be silently ignored, as agreed);
  - an invalid `duration`;
  - a cue naming an id that is not a column directly in a `columns` of the slide (or one in speaker notes);
  - a column named twice in one cue, two `width` parts on one line, `width` with nothing.
- **Runtime.**
  - `lattice.js`: `placeColumns` gives each column of a tracked container the flex value of the current position, before components are shown. Still moves (jumps, scrubber, preview, print, reduced motion) set the values at once.
  - An animated move measures the columns where they are and cancels any move under way. It then measures them at their final values and moves the boxes as `flex: 0 1 Wpx`, margins included (a collapsed column gives back one gap through a negative margin). Meanwhile `.lt-column-in` keeps a fixed width: the final one, or its own for a collapsing column, which fades out while an opening one fades in. The final values are set at the end.
  - A move that interrupts another takes 140 ms. The core dispatches `lt-relayout` with `detail.follow` (the duration) at the start of a move, and with `animate: false` at the end and after a still change.
  - `lattice.css`: the wrapper, the clipping during a move, and the collapsed state (hidden, contents at opacity 0, gap given back).
  - `arrow.js`: a follow mode that measures the arrow at every frame while columns move, blending in a change of the arrow's own target. An arrow whose target or `from` is in a collapsed (or collapsing) column is hidden without a warning.
- **Manual.**
  - A new slide, "Columns that make room", after "Timeline ranges". The source of `vsum` collapses, its abstract interpretation (`direction=LR`) takes the row, then the source comes back and morphs to `##vector-ref` and `##fx+`, with an arrow that follows.
  - A detour, "How it is written", shows the syntax.
  - New files `programs/vsum.scm` and `programs/vsum.bbv`. The "Containers" slide, the diagnostics detour and the cheat sheet mention the feature.
- **Docs.**
  - Spec: the sections above.
  - README syntax table, design report (section 3.16, roadmap v0.24, decision 33), SKILL.md (structure, tests table, a pitfall on moving columns), todo.
  - The 0.23.0 report copied to `docs/archive/` and listed in its README.
  - Version 0.24.0.

## 2. Verification

- `pytest -rs`: 304 passed, no skips, in Chromium (288 before). New tests:
  - `test_steps.py`: the columns track and its states, lockstep and detour steps, LT030, ten LT064 cases in cues and four on the containers.
  - `test_output.py`: the HTML of tracked and untracked columns and of a column collapsed from step 0, and the deck JSON.
  - `test_runtime.py`, `test_columns_change_width_however_a_step_is_reached`, on a slide of three columns with a diff, fragments and two arrows:
    - the same widths, arrows, fragments and diff from a fresh load, random jumps, every step forward and backward, skip playback, the preview and print;
    - a collapsed column takes no width and gives back its gap, is hidden and inert, and the arrow into it is hidden;
    - frozen halfway through a move, the contents keep their final width (their own when collapsing), and the other arrow ends under its target as measured at that moment;
    - an interrupted move heads for the widths of the step it returns to;
    - reduced motion places the columns directly.

  That interrupted-move check caught a real bug while it was written: without cancelling the transitions under way, the final layout was measured mid-transition.
- `test_layout.py` skips collapsed columns and covers the new manual slide at its first and last step.
- Screenshots in Chromium at 1280x720: the manual slide at rest, mid-collapse and mid-reopen, at the last step and in its detour, plus a scratch deck of the motivating case.
- Examples and the manual rebuilt; `check_docs.py` and `lattice check --strict` on the manual pass.

## 3. Not verified, and left open

- Only Chromium was available. The motion uses `flex-basis` and margin transitions, `overflow-x: clip`, `inert` and `Element.getAnimations`, which Firefox supports.
- The timing (600 ms, 140 ms for an interrupted move) and the look of a column sliding in at its final size were judged on screenshots only; see the todo.
- A slide opened at a step where a column is collapsed lays out that column's content at width 0 until it opens (invisible); see the todo.
- Found on the way, older than 0.24: an animation without `height` in a column lets its caption overlap a paragraph below the columns; see the todo.
- `docs/implementation-report-2026-10-06-b.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
