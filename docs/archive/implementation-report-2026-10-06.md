# Implementation report: arrows absent at some positions (Lattice 0.22.0, 2026-10-06)

The defense's background slide gains four steps, after "many of which are redundant", each with an arrow at one of the highlighted checks of `findv` and a label saying why it is redundant. One `arrow` block with four targets did not fit: an arrow with `steps:` is shown at every position of its track, so it would point at the first check before its step and stay on the last one after. The rule is in spec 8.8 and 8.9 (with 15); the rationale is decision 31.

## 1. What was built

- **`null` steps** (`components/visual.py`, `runtime/components/arrow.js`): an entry `null` in the `steps:` of an `arrow` is a position without an arrow. The data keeps `null` at that position; target checks (`arrow_targets`, `arrow_ends`) skip it; steps that are all `null` are LT022. In the browser the SVG is hidden at that position, and the arrow shown next is placed directly instead of gliding from the one that is gone.
- **Docs**: spec 8.8 (the `arrow` row), 8.9 (Steps), 15 (0.22 row); manual (the "Arrows that move" note); README (the `arrow` row); design report (roadmap v0.22, decision 31); SKILL.md (tests table); todo; the 0.21.0 report copied to `docs/archive/`. Version 0.22.0.

## 2. Verification

- `pytest -rs`: 287 passed, no skips, in Chromium (2 new tests: `test_arrow_null_steps` in `test_output.py`, the data and the LT022; `test_arrow_null_steps_hide_it` in `test_runtime.py`, the arrow hidden at null positions forward and backward, and placed without a glide after one).
- Examples unchanged (none uses the feature); rebuilt. `check_docs.py` and `lattice check --strict` on the manual pass.
- The defense deck built without warnings. On the background slide (steps 3 to 7) the four arrows were looked at in Chromium at 1280x720: each head at its segment, the labels clear of the code (lengths 260 and 220 for the two `vector?` checks, the default 120 for the others), no console errors.

## 3. Not verified, and left open

- `docs/implementation-report-2026-10-05-e.md` and `-f.md` are copied to `docs/archive/`; the copies left in `docs/` need a `git rm`.
