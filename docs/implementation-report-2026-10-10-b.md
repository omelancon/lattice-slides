# Implementation report: ΛV without generic entries (Lattice 0.35.0, 2026-10-10)

The report of 0.34.0 is in `archive/implementation-report-2026-10-10.md`.

Olivier's request, from the "Built-in Constant Folding" slide of `phd_defense/src/future-work.md`: once the call `(incr 0)` is folded, ΛV goes on to build the generic entry of `incr` (`A2`, `x: any`) and its versions, which the audience may take for a consequence of the fold. An option `generic_entry=true|false`, `true` by default so that existing animations do not change, `false` on that slide.

## 1. What was built

- `bbv/lv.py`: `LambdaVersioning(generic_entry=...)`. When the queue first empties, `after_step` queues the generic entries of the other functions only with `generic_entry` on; off, the run ends there (no `generic-entries` frame). The entry function keeps its generic entry, the root of the run.
- `bbv/trace.py` and `components/bbv.py`: the option `generic_entry` on `bbv-anim` (default `true`); `false` with `algorithm: sbbv` is an error (LT022), since SBBV starts from the generic entry of every function.
- The manual's `bbv-fold` slide sets it, so that its run ends with `M1` and `N1`.

## 2. Tests and verification

- `test_bbv.py`: no `generic-entries` frame and no `A2` without generic entries, the same frames as the default run up to that point, `M1` and `N1` alone after a fold; the default unchanged; the error with SBBV; the option through a deck.
- `pytest -rs`: 460 passed, 1 skipped (Firefox, not installed here), 1 failed: the manual's `plot-sources` in `test_layout.py`, as in 0.34.0 (section 3). Examples and the manual rebuilt; `scripts/check_docs.py`: 0 problems.
- Docs: spec 8.8, 9.5 and 15; README; design report (roadmap); `docs/USER_SKILL.md`; `docs/SKILL.md`; manual and versions; `archive/README.md`.

## 3. Left open

- An unknown callee (a procedure in a variable) is still an opaque call without generic entries: its return point receives `any`, as when the callee is unknown with them.
- The `plot-sources` layout failure of 0.34.0 in this sandbox (fonts) is unchanged.
