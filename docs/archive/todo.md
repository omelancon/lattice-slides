# BBV animations phase: status and todo

Updated 2026-10-01 (after the 0.5.0 implementation). Files in this folder: `plan.md` (design, strategy, decisions, questions), `plan-abstract-interpretation.md` (the 0.5.0 plan with its decisions), `reading-notes.md`, `implementation-report.md` (what shipped, fidelity notes, numbers, with a 0.5.0 addendum), this file.

## Done

- [x] Readings (Lattice docs and code, thesis chapters 1 to 3, the Gambit ΛV implementation, the SBBV blog post); `plan.md` and `reading-notes.md`.
- [x] Touch base: 15 questions answered, green light (decisions in `plan.md` section 6).
- [x] Phase 0: `lattice.bbv` model (types, prims, IR and `.bbv` parser, SBBV, heuristics, trace), tests against figure 6.
- [x] Phase 1: block bands layout (TB and LR, wrapping, lanes), `bbv-anim` and `bbv-cfg`, `bbv.js`, CSS, example 07, browser test, docs.
- [x] Phase 2: ΛV (entries, exits, return points, cascades, equivalence classes, hidden functions, index allocation), figures 14 to 16 in the example, tests.
- [x] Phase 3: instruction granularity, `events`, `until`, tooltips, algorithm following (`meta=algo`, bundled pseudo-code, `lattice:` files), PDF check, coherence pass (`check_docs.py` 0 problems), version 0.4.0.
- [x] Full suite green (85 tests, Chromium and Graphviz present), all seven examples rebuilt.
- [x] Firefox display fix: fixed panel width (constant graph scale) and a 30 px margin for back edges (Olivier confirmed, 2026-09-30).
- [x] 0.5.0: plan for abstract interpretation, 12 questions answered, green light.
- [x] Phase A: intervals, types with ranges, primitives with interval effects and narrowing rules, parameter annotations, predicates of any arity.
- [x] Phase B: `AbstractInterpreter`, `AbstractTrace`, pseudo-code listing, tests against figures 1, 2 and 4.
- [x] Firefox display fix 2: a wrapping caption no longer shrinks the drawing; the caption fits in the space left (`fitCaption` in `bbv.js`, 2026-10-01).
- [x] Hand-over: documentation coherence pass of SKILL.md applied (2026-10-01): roadmap and decisions reordered, component lists completed, primitive table and frame states in the spec aligned with the code, Firefox noted in setup and pitfalls; `check_docs.py` 0 problems.
- [x] Phase C: `abstract-interp-anim`, runtime, CSS marks, two example slides, browser test, docs, version 0.5.0; 94 tests green, examples rebuilt.

## Waiting on Olivier

- [ ] Review of the example deck and of the visual style (screenshots were checked in Chromium at 1280x720; fonts fall back on this machine).
- [ ] Review of the two abstract interpretation slides (contexts show every live variable, including `n`; see the report addendum).
- [x] Release tarball step removed from SKILL.md (Olivier, 2026-09-30).

## Later, if wanted

- [ ] Importer for the Gambit `--plot` state stream (`.plot.html`).
- [ ] Scheme front end producing `.bbv` programs.
- [ ] Jump cascade removal in the `done` frame.
- [ ] Other traversal orders; the blog's backward-score heuristic.
- [ ] Nicer edge routing when a wrapped rank puts a target on a second line (edges cross the first line).
- [ ] Abstract interpretation: interprocedural calls (calls are opaque), boolean blindness, a `hide` option to drop variables such as `n` from the drawn contexts.

## Notes for whoever picks this up

- Nothing is committed to git; the working tree holds v0.5.0 in full.
- Every prose file avoids em dashes (owner preference, also in SKILL.md).
- `check_docs.py` enforces version agreement across README, spec, report, `__init__.py` and `pyproject.toml`.
