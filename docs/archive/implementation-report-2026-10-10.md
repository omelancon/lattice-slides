# Implementation report: constant folding in ΛV (Lattice 0.34.0, 2026-10-10)

The report of 0.33.3 is in `archive/implementation-report-2026-10-09.md`.

Olivier's request, from the "Built-in Constant Folding" slide of `phd_defense/src/future-work.md`: after the ΛV run of `(define (incr x) (+ x 1)) (incr 0)`, make the versions of `incr` disappear and replace the call by the constant 1. A first proposal (hand-written `edits:` frames after the run) was set aside for Olivier's question: could ΛV itself apply the fold, at the step where it becomes valid? His answers: during the run (not after the paths), and the call site becomes `#res = 1` with its return point kept, as thesis section 4.2 describes.

## 1. What was built

- **The algorithm** (`bbv/lv.py`, `fold=True`): after every step, every reachable, specialized call site is considered in creation order. It is folded when its callee entry's **region** (the versions it reaches along goto, test and return edges, and through call edges the versions of its callees) is fully specialized and does not contain the call site; no version of the region has a side effect (replayed on its context: no `fail`, no `display`, `read`, `random`, `vector-set!`, `##vector-set!`, no primitive declared by the deck, no primitive whose arguments do not already have the types it requires, no unknown callee); and every exit site the entry reaches returns the same constant to it (`constant_text`: a singleton integer interval, `#t`, `#f`, `nil`), all through one return point. The fold (`apply_fold`) replaces the call line by `#res = C` and `goto`, drops the call and return edges, adds a goto edge, keeps the old code (`folded_from`), the constant type (`folded`) and the entry (`folded_entry`) on the version, then brings exit sites and return points up to date and requeues.
- **Frames** (`bbv/trace.py`): `fold-pure` (the region marked `path`), `fold-site` (the call site and its return point marked `path`), `fold` (the call site `new`, the versions only that call reached `gone`, as after a merge), with the captions of spec 9.5 and the tones `no side effect`, `constant result` (accent) and `constant fold` (good) in `bbv.js`. The tables give a folded call site `alt`, its code before the fold, and the frames before its fold frame carry `alt: true` on it; `_code` resolves the callee label of an old call line through `folded_entry`.
- **Drawing** (`bbv.js`): `drawNode` draws both codes in the same place; `nodeState` shows the one the frame asks for (with the `shown` count of instruction frames) and updates the tooltip of such a node; `layout.node_size` sizes the box for the longer of the two, so the drawing never rescales and the enlarged block fits both.
- **Paths** (`bbv/paths.py`): a folded call is walked as its goto, `#res` bound to the constant.
- **Option** `fold` on `bbv-anim` (default `false`); with `algorithm: sbbv` it is an error (LT022).

## 2. Decisions

- The fold happens during the run (design decision 45), so the frames only show what the model proves; the thesis pairs it with context memoization, which the model does not do (roadmap v0.34).
- Side effects are judged conservatively: a primitive that could raise an exception (`car` of `any`) prevents the fold, `##car` does not. Allocation is not an effect, since a fresh value is never a constant.
- Return point indices are still allocated at the end, reachable exits first, so an exit that a fold made unreachable gets a late index (`return [4] r` in `incr`'s R1 before the fold, where the run without folding shows `[0]`).

## 3. Tests and verification

- `test_bbv.py`: the three frames of `incr` in order, their marks and captions, the final versions, `code` and `alt` of M1, `alt` on the frames before the fold only; no fold without the option, with `display`, without intervals, with an unknown input, or with `car` of `any` (and a fold with `##car`); a boolean constant; the error with SBBV; a path through a folded call; the box and the enlarged block sized for both codes.
- `test_runtime.py`: `test_a_folded_call_site_shows_its_code_of_the_step` (fresh load, forward, backward jumps; the box keeps its size; the region gone after the fold).
- The manual's new slide `bbv-fold` (`user_manual/programs/incr.bbv`), checked in screenshots; the defense slide checked step by step.
- `pytest -rs`: 458 passed, 1 skipped (Firefox, not installed here), 1 failed: the manual's `plot-sources` in `test_layout.py`, which fails the same way on 0.33.3 in this sandbox (section 4). Examples and the manual rebuilt (`scripts/build_examples.py`); `scripts/check_docs.py`: 0 problems.
- Docs: spec 8.8, 9.5 (the paragraph *Constant folding*, frames, marks, tables) and 15; design report (roadmap, decision 45); README; `docs/USER_SKILL.md` (feature map, a rule that bites); `docs/SKILL.md` (structure, tests, a pitfall); manual and versions.

## 4. Left open

- Only Chromium 141 was available (Firefox not installed): the two codes of a folded node are SVG text, nothing measured.
- `test_layout.py` fails on the manual's `plot-sources` at step 0 (a Vega plot covering a paragraph) before and after this change in this sandbox; it passed on 0.33.3 on Olivier's machine, so it is likely the fonts available here.
- No git commit: `git add docs/implementation-report-2026-10-10.md docs/archive/implementation-report-2026-10-09.md user_manual/programs/incr.bbv`, `git rm docs/implementation-report-2026-10-09.md`, then `git add -u`.
