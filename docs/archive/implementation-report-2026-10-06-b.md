# Implementation report: three quick skip presses (Lattice 0.23.0, 2026-10-06)

Shift+Right and Shift+Left move ten steps at a time, which is slow on a slide with a long animation, and End has no counterpart backward. Pressing Shift+Right three times within a second now plays to the last step of the slide, and Shift+Left three times to the first. The rule is in spec 7.6 (with 7.2, 7.5 and 15); the rationale is decision 32.

## 1. What was built

- **Runtime** (`src/lattice/runtime/lattice.js`): `burstTarget` in the input section counts the presses of `skip-forward` and `skip-back` in a one-second window from the first (`BURST_PRESSES`, `BURST_WINDOW_MS`). On the third press, `onKey` calls `playSteps` with the last step (or 0) instead of the ten-step action, so the playback is the same as `last-step`: played, clamped to the slide, cancelled by a new event, stopped in front of a blocking detour step, never touching `H`. A fourth quick press keeps going to the end. Auto-repeat (`KeyboardEvent.repeat`) is not counted; any other action or slide key resets the count. The count follows the action, so a deck that rebinds the skip keys keeps the gesture.
- **Presenter view**: the Keybindings section lists the gesture (the first key of each skip action, then "×3: last or first step of the slide").
- **Docs**: spec 7.2 (the SKIP row), 7.5 (the Keybindings section), 7.6 (the rule), 15 (0.23 row); README and manual key tables; design report (roadmap v0.23, decision 32); SKILL.md (structure and tests table); todo; the 0.22.0 report copied to `docs/archive/` and listed in its README. Version 0.23.0.

## 2. Verification

- `pytest -rs`: 288 passed, no skips, in Chromium. New test `test_three_quick_skips_go_to_the_end_of_the_slide` (`test_runtime.py`), on a slide of 41 steps: three quick Shift+Right presses play (not jump) to step 40 without touching history, three Shift+Left to 0; three slow presses move 30 steps; a direction change or another key in between does not reach the end; a held Shift+Right (auto-repeat) does not either, and three real presses afterwards do. The test fails against the 0.22.0 runtime (it stops at step 12). The presenter test checks the new Keybindings row.
- Examples and the manual rebuilt; `check_docs.py` passes.

## 3. Not verified, and left open

- Only Chromium was available; the gesture relies on `KeyboardEvent.repeat` and `performance.now`, which Firefox supports.
- The window (one second from the first press) and the playback speed to the end were not tried on a real talk; see the todo.
- `docs/implementation-report-2026-10-06.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
