# Implementation report: thresholds that name the fixnum range, predicates of `prims` (Lattice 0.20.0, 2026-10-05)

Two changes needed by the defense slide that runs abstract interpretation over `findv`, agreed with Olivier before implementation. The rules are in spec 8.8, 9.5 and 9.6 (with 15); the rationale is decision 29. Fifth release of the day, hence `-e`.

## 1. What was found first

- The index of `findv` is bounded by `##vector-length`, whose result is at most maxfix. With the `machine` thresholds (the sign and the 8, 32 and 64-bit limits), the block after the loop test widened `i` from `{0}` to the next threshold beyond maxfix, `2^63-1`, and showed `i: fx | bg [0, 2^63-1]`, although the loop head and the body showed fixnums. Writing maxfix in a `thresholds` list worked but needed the number itself (`1152921504606846975` for 61-bit fixnums).
- A predicate declared in the `prims` option of `bbv-anim`, `bbv-cfg` or `abstract-interp-anim` could not be tested in an `if`: `parse` checks the program with the default primitives, and the option was added after it ("'pred' is not a predicate"). This contradicted the documented `{name: {test: pair}}` form.

## 2. What was built

- **Thresholds by name** (`bbv/intervals.py`, `thresholds_from`): a `thresholds` option is a name (`machine`, `sign`, `none`, as before) or a list whose items are integers or the names `machine` and `sign` (their thresholds are added), `maxfix` and `minfix` (the bounds of the fixnum range of `fixnum_bits`). An unknown name is LT022. `AbstractInterpreter` and `Specializer` (the merges with `intervals`) resolve their thresholds with it; the option's type accepts strings in the list.
- **Predicates of `prims`** (`bbv/ir.py`, `components/bbv.py`): `parse(text, prims)` adds the primitives before checking the program; `load_program` passes the option for `program` files, `source` and program text returned by Python, and still adds it to a `Program` built in Python.
- **Docs**: spec 8.8 (the `abstract-interp-anim` row), 9.5 (`prims`), 9.6 (Join), 15 (0.20 row); manual (the `thresholds` and `prims` rows of the options tables); design report (roadmap v0.20, decision 29); SKILL.md (tests table); todo (a layout that folds long chains of ranks, noted while sizing the defense slide); the 0.19.0 report copied to `docs/archive/`. Version 0.20.0.

## 3. Verification

- `pytest -rs`: 283 passed, no skips, in Chromium (2 new tests in `test_bbv.py`: `thresholds_from` with names, `minfix` for 8 bits and an unknown name; `findv` analysed with `[sign, maxfix]`, `i: fx [0, maxfix]` at the loop head and after the test and the generic addition unreached, against `fx | bg` with `machine`; a deck whose `abstract-interp-anim` tests a predicate of its `prims`, and the two errors).
- The examples are unchanged (no deck uses either feature); rebuilt. `check_docs.py` and `lattice check --strict` on the manual pass. The defense slide built and looked at in Chromium at several steps.

## 4. Not verified, and left open

- Drawings of long CFGs stay small in both directions (todo).
- `docs/implementation-report-2026-10-05-d.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
