# Implementation report: lengths without symbols, threshold offsets (Lattice 0.21.0, 2026-10-05)

The defense's `findv` should check overflow (`(or (fx+? i 1) (##+ i 1))`) and the abstract interpretation slide should show that check disappearing, without showing symbolic vector bounds yet. Two changes, agreed with Olivier. The rules are in spec 8.8, 9.5 and 9.6 (with 15); the rationale is decision 30. Sixth release of the day, hence `-f`.

## 1. What was found first

- No option turned the symbolic bounds off: `vector-length` and `##vector-length` always give `fx {⟦v⟧}` for a named vector.
- With lengths as numbers, the overflow check of `fx+?` did not disappear: the interpreter widens at every join (as the thesis's figure 2 does), so the block after `i < len` widened `[0, maxfix-1]` to the next threshold, `maxfix`, and `fx+?(i, 1)` could overflow again. Widening only at loop heads was prototyped and fixes it with `[sign, maxfix]`; Olivier chose threshold offsets instead, which keeps the algorithm of the thesis figures.

## 2. What was built

- **`vector_bounds`** (`bbv/intervals.py`: `vector_bounds`, `using_vector_bounds`; `bbv/prims.py`; `bbv/absint.py`; `bbv/sbbv.py`; `bbv/trace.py`; `components/bbv.py`): an option of `bbv-anim` (with `intervals`) and `abstract-interp-anim`, default `true`. Off, the run is wrapped in `using_vector_bounds(False)`: the length primitives give `fx [0, maxfix]`, and parameter annotations naming a length are widened to their numeric value at the entry (the only two sources of symbols). ΛV inherits it from `Specializer`.
- **Threshold offsets** (`thresholds_from`): `maxfix-K` and `minfix+K` (spaces allowed) in a thresholds list.
- **Docs**: spec 8.8 (both rows), 9.5 (vector lengths), 9.6 (Join), 15 (0.21 row); manual options tables; design report (roadmap v0.21, decision 30); SKILL.md (the pitfall on symbolic bounds, tests table); todo (widening at loop heads, prototyped, left as an option to decide); the 0.20.0 report copied to `docs/archive/`. Version 0.21.0.

## 3. Verification

- `pytest -rs`: 285 passed, no skips, in Chromium (2 new tests in `test_bbv.py`: offsets and their errors; `findv` with `fx+?` keeping `fx [0, maxfix]` at the loop head and dropping the overflow branch with and without symbols (`[0, ⟦v⟧-1]` against `[0, maxfix-1]` after the test), the overflow branch reached again without the `maxfix-1` threshold, an annotation widened at the entry, SBBV on example 07's `findv` keeping the check against the second length (`fx<(i, len2)`) only without symbols; both components with `vector_bounds: false`, their instance data free of `⟦`).
- Examples unchanged (no deck uses the option); rebuilt. `check_docs.py` and `lattice check --strict` on the manual pass. The defense deck built without warnings; its two slides looked at in Chromium, with no content past the slide body at any step.

## 4. Not verified, and left open

- Widening only at loop heads (todo).
- `docs/implementation-report-2026-10-05-e.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
