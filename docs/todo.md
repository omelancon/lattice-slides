# Lattice: todo

This todo list is intended for Olivier to pick future directions, not for immediate implementation.

Updated 2026-10-01, after the 0.6.0 implementation (`implementation-report-2026-10-01.md`). The items left open by the versioning and abstract interpretation phases (`archive/todo.md`) are carried over below; everything done in those phases stays recorded there.

## Waiting on Olivier

- [ ] 0.6.0: a look at the arrow and at the Keybindings grid of the presenter view in Firefox (only Chromium was available in the session; the geometry uses `getBoundingClientRect`, `Range.getBoundingClientRect` and `getBBox`, which both engines support).
- [ ] 0.6.0: try the detour step of example 01 (`at=1` on the invariant detour of "Nothing here is linear") and the skip keys on a long animation (example 06 or 07) to judge the playback interval (30 to 90 ms per step, `playSteps` in `lattice.js`).
- [ ] 0.4/0.5: review of the example deck 07 and of its visual style (screenshots were checked in Chromium at 1280x720; fonts fall back on the build machine).
- [ ] 0.5: review of the two abstract interpretation slides (contexts show every live variable, including `n`; see the archived report addendum).

## Later, if wanted

Navigation and presenter view:
- [ ] Arrow labels: a `label_at` option (tail, middle, head). A label beside the middle of a `from` arrow can overlap text when the two boxes are close; `curve` moves it for now.
- [ ] Detour steps inside a tour: a detour step enters its detour as anywhere else and the tour successor applies only at the last step; decide whether a tour should be able to turn detour steps off.
- [ ] `archive/reading-notes.md` still cites the older `docs/this_phase/` paths of the thesis and the Gambit sources; harmless in an archive, fix if the files are ever moved.

Basic block versioning and abstract interpretation (from `archive/todo.md`):
- [ ] Importer for the Gambit `--plot` state stream (`.plot.html`).
- [ ] Scheme front end producing `.bbv` programs.
- [ ] Jump cascade removal in the `done` frame.
- [ ] Other traversal orders; the blog's backward-score heuristic.
- [ ] Nicer edge routing when a wrapped rank puts a target on a second line (edges cross the first line).
- [ ] Abstract interpretation: interprocedural calls (calls are opaque), boolean blindness, a `hide` option to drop variables such as `n` from the drawn contexts.

## Notes for whoever picks this up

- `check_docs.py` enforces version agreement across README, spec, report, `__init__.py` and `pyproject.toml`; the highest diagnostic code is LT054.
- Release step 4 of SKILL.md (removing `.lattice-cache/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`) is for Olivier's working tree.
