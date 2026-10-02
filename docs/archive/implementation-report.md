# Implementation report: basic block versioning for Lattice 0.4.0

*Written 2026-09-30 after the green light of the touch base (decisions in `plan.md` section 6). Everything below is implemented, tested and documented in the working tree; nothing is committed to git.*

## What shipped

**Model, `src/lattice/bbv/`.** `types.py` (bit-set type lattice over `fx bg fl #t #f nil pair str proc other`, known function identities for procedures, thesis notation `fx | fl`, `!fx`, `a/b: fx`; immutable contexts with equivalence classes, narrowing, union, intersection, renaming for gotos), `prims.py` (type tests, fixnum and flonum operations, overflow-checking `fx*?` and friends, generic arithmetic, pairs; extensible from YAML), `ir.py` (programs, functions, blocks, six instruction forms, the `.bbv` line syntax with `;` comments, liveness giving blocks their parameters, positional or named goto rebinding, return blocks with `#res`), `sbbv.py` (algorithms 1.1 to 1.7: versions, FIFO queue, `getOrCreate` with merged chains, reachability recomputed from roots, merging by pairs until the limit holds, requeueing of reconnected versions, per-instruction specialization with notes for instruction-level frames), `lv.py` (algorithms 2.1 to 2.10 as a subclass: known-callee entry points, call sites, exit sites, return points from `callContext ∩ exitContextAfter` with parameter narrowing and result equivalence, a `sync_all` that adds before it removes, generic entries when the queue first empties, return index allocation per exit contract), `heuristics.py` (similarity and arithmetic distances ported from `context.scm`, random), `trace.py` (`VersioningTrace`: one frame per event, marks from a diff with the previous frame, automatic captions, panel, meta with program lines and pseudo-code lines, hidden functions filtered, `events`, `until`, instruction granularity), `layout.py` (block bands in `TB` and `LR`, Graphviz ranks with a longest-path fallback, wrapping of wide ranks by groups of one block, back-edge lanes, shared box), `pseudocode/sbbv.txt` and `lv.txt` (the thesis algorithms, for `code` following).

**Components and runtime.** `components/bbv.py` registers `bbv-anim` and `bbv-cfg`; `runtime/components/bbv.js` draws both (rounded nodes with label, starred entries, `;;` context lines, code lines with removed tests struck through, native tooltips with the full context; goto, `#t`/`#f`, dashed indexed return and dotted call edges; lane-routed back edges; gliding on single steps; `shown` lines in instruction frames; follower highlighting for `bbv-cfg`). Styles in `lattice.css` from existing tokens, origin colours from the build-time palette through `color-mix`.

**Core changes.** `code` gained `meta=KEY` (which per-position meta key to follow) and `file="lattice:PATH"` (bundled files). `pyproject.toml` ships the pseudo-code. Version 0.4.0.

**Example.** `examples/07-basic-block-versioning`: source CFG of `find`, SBBV with the source CFG following (LR), a detour with instruction-level frames and the algorithm listing following (`meta=algo`), a branch on the limit (1 and 3), ΛV on `power4`/`square` (figure 14), on `square` with `*` as a hyperfunction and `a/b` classes (figure 15), on `fact` with hidden operators (figure 16), and a detour with the same `fact` under SBBV. The tour `short` prints to a PDF of 8 pages.

**Tests.** `tests/test_bbv.py` (15 tests: notation, contexts, parser and its errors, figure 6 with limit 2 and the merge with limit 1, determinism across heuristics, figure 14 return points and entries, figure 16 fixnum path and operator entries without tests, SBBV opacity, frames and marks, hidden functions and event filters, layout invariants in both directions, components and followers, LT022 and LT045). `tests/test_runtime.py` gained a Chromium test stepping the example forward and backward and checking the final 14 versions. The whole suite: 85 passed.

**Documentation.** Spec: 8.8 rows for `bbv-anim`, `bbv-cfg` and the `code` options, 9.1, a new 9.5 (syntax grammar, semantics, algorithms, frames, layout), changelog 15, version. README: table rows, a paragraph, example 7. Report: 3.10, use case 4.7, roadmap v0.4 and later items, decision 12. SKILL.md: structure, test table, two pitfalls. `check_docs.py` reports 0 problems.

## Fidelity notes (what differs from the thesis figures)

- Return point contracts are computed by the algorithm, so `power4` gets four return points (fixnum, fixnum-or-bignum after `fx*?` fails, flonum, generic) where figure 14 draws three; the merge with limit 3 then folds the first two. `fact` reproduces figure 16's structure: entries `n: any` and `n: fx`, the fixnum path through `B2 D2 E2 F3 G2` calling the fixnum entry, overflow return points leading back to the generic path.
- The similarity heuristic is the default; `arithmetic` gives the figure-16 result on `fact` (it keeps the `fx` contexts apart), which the example uses.
- Jump cascades are not removed in the final frame (listed as later work in the report).
- Labels count versions per block in creation order (`C12` after many merges); the thesis renumbers its figures by hand.

## Numbers

Frames: `find` limit 2, 30 (instruction level: 46); `power4` ΛV limit 3, 82; `square-ops`, 58; `fact` with hidden operators, 102 visible frames out of 199 events. Data per instance: 30 to 120 KB of JSON; the example deck is 559 KB.

## Left for later (from the plan and the touch base)

Importer for the Gambit `--plot` stream, a Scheme front end, jump cascade removal in the `done` frame, other traversal orders, the blog's backward-score heuristic.

---

# Addendum: abstract interpretation for Lattice 0.5.0

*Written 2026-10-01 after the second green light (decisions in `plan-abstract-interpretation.md` section 6). Implemented, tested and documented in the working tree; nothing is committed to git.*

## What shipped

**Intervals, `src/lattice/bbv/intervals.py`.** `Interval(lo, hi)` with unbounded ends, union, intersection (possibly empty), threshold widening (a bound that grew jumps to the next threshold on its side), arithmetic for `+ - * quotient abs`, and narrowing for `< <= = >=` and their negations. The thesis thresholds (`0 1 2 127 128 2^31-1 2^31 2^63-1 2^63` and their negative counterparts) and a `sign` set; bounds print as `2^31-1`.

**Types with ranges.** `Type` carries an optional range that only integer types keep; `fx [0, 100]`, `{0}` and `(-inf, 5]` parse; union joins ranges, intersection drops the integer bits when ranges are disjoint, `widen` extrapolates with the thresholds, `refined` turns an interval inside the fixnum range into `fx` and one outside into `bg`. Contexts gained `map`, and `union(other, thresholds, widen=True)`.

**Primitives.** Every primitive now has a transfer function on intervals and, when it is a comparison or a type test, a narrowing rule used both ways (true and false branches). Integer constants carry singleton intervals. `if` accepts predicates of any arity (`(if (< i n) ...)`). Function headers accept parameter annotations (`function fact(n: fx | bg)`), which SBBV and ΛV also honour (ranges stripped, since they ignore intervals).

**The interpreter, `absint.py`.** One entry context per block, FIFO worklist, transfer functions borrowed from the SBBV specializer with `intervals=True`, union with widening at every join, narrowing at conditionals (switchable), dead edges, a per-variable history of `∪` and `∇` steps, and `start / dequeue / instruction / propagate / done` events. `trace.py` turns them into frames (`AbstractTrace`): context lines inside each block, the exit context in the tooltip, marks `active new changed widened`, dead edges, a worklist panel and one panel entry per tracked `BLOCK.VAR`, automatic captions and the 22-line pseudo-code listing for `meta=algo` following.

**Component.** `abstract-interp-anim` (options `entry thresholds narrowing fixnum_bits events granularity until panel history caption max_steps` on top of the common ones), drawn by the same `bbv.js` with the block bands layout of `bbv-cfg`; context text is updated in place between frames.

**Example and tests.** Two slides open example 07: `sum-to-n` with the `B.i` history chain of figure 2, and `fact` reaching figure 4 in 7 iterations. `tests/test_bbv.py` has 24 tests (9 new: the figure 2 chain, interval arithmetic and narrowing, parser annotations and predicates, SBBV ignoring intervals, figures 1, 2 and 4, narrowing off, dead branches, frames). The browser test also steps the new slide. Whole suite: 94 passed; seven decks rebuilt; `check_docs.py` 0 problems; version 0.5.0 everywhere.

## Fidelity notes

- Figure 4 draws only the loop variables; the component shows every live variable of a block, so the parameter `n` appears in each context (`n: fx | bg` from its annotation).
- The widening chain of figure 2 is reproduced exactly: `{0}`, `[0, 1]`, `[0, 2]`, `[0, 127]`, `[0, 128]`, `[0, 2^31-1]`, `[0, 2^31]`, `[0, 2^63-1]`, `[0, 2^63]`, `[0, ∞)`, each step marked `∪` or `∇` in the history panel. Once the interval leaves the fixnum range the type widens from `fx` to `fx | bg`, which the thesis figure leaves implicit.
- `fact` converges to `i: [1, ∞)` in the body and `acc: [1, ∞)` at the loop head, as in figure 4; `narrowing: false` loses the bound on `i` (tested).
- Calls are opaque (`#res: any`), as decided; the loop examples do not call anything.

## Numbers

Frames: `sum-to-n` 63 (30 iterations), `fact-loop` 16 (7 iterations). The example deck is 621 KB with 14 slides.
