# Plan: animated abstract interpretation (`ai-anim`)

*Phase document, 2026-10-01. Follows the basic block versioning work of `plan.md` and `implementation-report.md`. Proposes one component, `ai-anim`, that animates classical abstract interpretation over a fixed CFG as presented in chapter 1.1 of the thesis (sum-to-n, figures 1 and 2; fact, figure 4). Section 6 lists the questions to settle before implementing.*

---

## 1. Summary

Abstract interpretation is the precursor of SBBV: the same contexts, but one context per block, joined by union with widening at every entry, narrowed at conditionals, and a worklist that re-interprets a block whenever its entry context grows, until a fixed point. The graph never changes; what changes is the annotation on each block. The component therefore draws the source CFG once (the `bbv-cfg` drawing) and animates the context lines inside the blocks, the worklist, and the edges along which contexts flow, with captions saying what was joined, when widening fired and when a branch was found dead.

Contexts gain **intervals**: an abstract value is a set of types (as in ΛV) plus, for integers, an interval. Type tests narrow the types; comparisons narrow the intervals; arithmetic widens them through interval arithmetic; union at joins applies the thesis widening (sign and 8, 32, 64-bit representability, figure 2). The same `.bbv` syntax and the same primitive table serve, with primitives extended by an interval semantics.

---

## 2. Goals and non-goals

Goals:

1. The algorithm of thesis 1.1: worklist over blocks of a fixed CFG, entry context = widened union of the predecessors' exit contexts, narrowing at conditionals (types and intervals), convergence.
2. The two thesis examples reproduced exactly: `sum-to-n` (figure 1, and the widening chain of `i` at the loop entry of figure 2: `{0}`, `[0,1]`, `[0,2]`, `[0,127]`, `[0,128]`, `[0,2^31-1]`, `[0,2^31]`, `[0,2^63-1]`, `[0,2^63]`, `[0,∞)`), and `fact` (figure 4: `i: (-∞,∞)`, `acc: [1,∞)` at `B`; `i: [1,∞)` in `C`; `acc: [1,∞)` returned).
3. One frame per event with automatic captions, the worklist in the panel, the chain of abstract values of chosen variables (the red path of figure 2) in the panel, and `code` following through program lines and a bundled pseudo-code listing, as for `bbv-anim`.
4. The same program files as `bbv-anim`, so a deck can show abstract interpretation and SBBV on the same `find` or `fact` and let the audience see what duplication buys.

Non-goals: interprocedural analysis (calls stay opaque, as in SBBV), relational domains, descending (narrowing) iterations after the fixed point, a drawing of the lattice itself (figure 2 as a diagram; the panel chain shows the same path as text).

---

## 3. Design

### 3.1 What the author writes

````markdown
# Abstract interpretation of `fact` {#fact-ai}

```ai-anim {#ai program="programs/fact-loop.bbv" height=440}
show: [label, context, code]
panel: [worklist, history]
history: [B.i, B.acc]
```
````

`programs/fact-loop.bbv` (figure 4, the thesis assumes an integer argument):

```
function fact(n: fx | bg)
A:  goto B(i=n, acc=1)
B(i, acc):  if >(i, 0) goto C else goto D
C:  i2 = -(i, 1)
    acc2 = *(acc, i)
    goto B(i=i2, acc=acc2)
D:  return acc
```

Additions to the `.bbv` syntax, all usable by `bbv-anim` too:

- **Parameter annotations** `name: TYPE` in the function header give the entry context (default `any`). Intervals are written after the type: `n: fx [0, 100]`.
- **Comparison tests**: `if PRIM(args) goto A else goto B` now accepts any primitive returning a boolean, not only one-argument type tests; `>`, `<`, `=`, `<=`, `>=`, `fx<`... narrow the intervals of their variable operands on each branch (`>(i, 0)` holds: `i ∈ [1, ∞)`; fails: `i ∈ (-∞, 0]`). A test on a boolean variable produced by an earlier comparison (`tmp = >(i, 0)` then `if tmp`) is narrowed as well when `tmp` is still bound to that comparison (question 2).
- Integer constants carry singleton intervals; `nil`, `#t`, `#f` carry none.

### 3.2 Abstract values and the interval lattice

`lattice/bbv/intervals.py`: `Interval(lo, hi)` with `lo`, `hi` integers or `±∞`, `union`, `intersection`, arithmetic (`+`, `-`, `*`, `quotient` with the usual sign cases, `fx` variants clipped to the fixnum range), comparison narrowing (`narrow_lt(a, b)` and friends returning the pair of narrowed intervals for each outcome), and **widening with thresholds**: `widen(old, new)` keeps a bound that did not grow and moves a bound that grew to the next threshold at or beyond it. Thresholds: `0, 1, 2, 127, 128, 2^31-1, 2^31, 2^63-1, 2^63, ∞` and their negatives (`-1, -2, -128, -129, -2^31, -2^31-1, -2^63, -2^63-1, -∞`). This reproduces figure 2 step for step: `{0} ∪ {1} = [0,1]`, `[0,1] ∪ [1,2] = [0,2]`, `[0,2] ∪ [1,3]` widens to `[0,127]`, then `[0,128]`, then `[0,2^31-1]`... The list is an option (`thresholds:`), with `sign` (only `0` and `±∞`) and `none` (plain union, may not converge; capped by `max_steps`) as presets.

`types.py`: `Context` gains an interval per numeric variable (`None` when the variable cannot be an integer). `narrow`, `set`, `union`, `restrict`, `rename`, equality and printing extend naturally; `union` of contexts takes a `widen` flag. Printing follows the figures: `i: fx [0, ∞)`, `acc: fx | bg [1, ∞)`, and `n: any` when nothing is known. SBBV and ΛV keep ignoring intervals (they never set one), so their frames are unchanged.

Intervals and types inform each other (question 5): an integer whose interval fits the fixnum range is `fx`, otherwise `fx | bg`; a `fixnum?` test narrows the interval to the fixnum range; a flonum has no interval.

`prims.py`: each primitive gains an optional interval rule (`+`, `-`, `*`, `fx+`, `fx-`, `fx*`, `fx+?`, `fx-?`, `fx*?`, `quotient`, `abs`, `min`, `max`, `##+`...) and comparison primitives gain a narrowing rule. Rules are functions of the argument values; the `prims:` option of the components can still add simple entries.

### 3.3 The algorithm (`lattice/bbv/ai.py`)

```
abstractInterpretation(function, entryContext):
    for block in function.blocks: block.context ← ⊥
    entry.context ← entryContext;  worklist.enqueue(entry)
    while block ← worklist.dequeue():
        context ← block.context
        for instr in block.body:                      # transfer functions, instruction by instruction
            context ← interpret(instr, context)        # arithmetic widens intervals, type tests and
        for (successor, outContext) in outgoing(block, context):   # comparisons narrow them
            if outContext = ⊥: continue                # a dead branch
            joined ← widen(successor.context, successor.context ∪ outContext)
            if joined ≠ successor.context:
                successor.context ← joined;  worklist.enqueue(successor)
```

Events: `start` (entry context set), `dequeue` (block active), `instruction` (one per instruction when `granularity: instruction`, with the context after it), `propagate` (one per successor edge: `unchanged`, `union`, `widened` or `dead`, with the successor requeued when it changed), `done` (fixed point, with the final contexts). Captions name the variables that changed, for example "B: i: [0, 2] ∪ [1, 3] widened to [0, 127]; acc: [0, 3] ∪ [0, 4] widened to [0, 127]; B requeued." The worklist is FIFO; a block already queued is not queued twice.

### 3.4 Frames, drawing, runtime

The drawing is the source CFG, laid out once (block bands as `bbv-cfg`, so the two components look alike on consecutive slides; Graphviz ranks when available). Frames reuse the `bbv.js` format and runtime with one extension: a node may carry `lines` (its context lines for that frame), which replace the static context lines. Node sizes are computed over all frames so a block never resizes. Marks: `active` (dequeued block), `changed` (entry context grew), `widened` (a bound jumped to a threshold), `dead` (entry context still ⊥: dimmed, as a never-reached block), edges `new` for the edge just propagated, `gone` style for a dead branch. The panel offers `worklist` (block labels), `history` (the chain of values of the tracked variables, with `∪` and `∇` between steps, as figure 2's solid and dashed edges), `iterations` (dequeues so far).

`meta[i]` carries `event`, `block`, `lines`, `line` and `algo` (lines of a bundled `lattice:bbv/pseudocode/ai.txt`, the listing above) so `code` blocks and `bbv-cfg` follow it as they follow `bbv-anim`.

### 3.5 Options

| Option | Default | Meaning |
|---|---|---|
| `program`, `source`, `prims`, `functions`, `show`, `colors`, `direction`, `wrap`, `height`, `caption`, `events`, `until`, `max_steps` | as `bbv-anim` | shared behaviour |
| `entry` | first function | the function analysed (one function per instance; calls are opaque) |
| `thresholds` | thesis list | widening thresholds, or `sign`, or `none` |
| `narrowing` | `true` | narrow at conditionals (off: pure union, to show why narrowing matters) |
| `granularity` | `block` | `block` or `instruction` |
| `panel` | none | keys among `worklist`, `history`, `iterations` |
| `history` | `[]` | `BLOCK.VAR` entries whose chain of entry values the panel shows |
| `fixnum_bits` | 62 | width used to decide `fx` versus `fx | bg` from an interval |

---

## 4. Implementation strategy

**Phase A, intervals and contexts (1 day).** `intervals.py` with thresholds and arithmetic, `Context` intervals, printing, prims' interval and narrowing rules, parser additions (annotations, comparison tests). Tests: the figure 2 chain from `widen`, interval arithmetic cases, narrowing of `>`, `<=`, `=`; SBBV and ΛV suites unchanged.

**Phase B, the interpreter and frames (1 day).** `ai.py`, `AbstractTrace` producing frames, captions, history, `pseudocode/ai.txt`. Tests: `sum-to-n` reaches figure 1 with exactly the figure 2 chain for `i`; `fact` reaches figure 4; `narrowing: false` loses `i: [1, ∞)` in `C`; `find` under abstract interpretation keeps `p: any` at `A` and the `procedure?` test (the SBBV contrast).

**Phase C, component, runtime, example, docs (1 day).** `ai-anim` in `components/bbv.py`, per-frame `lines` in `bbv.js`, example slides in `07-basic-block-versioning` (sum-to-n with the history panel, fact, and `find` under abstract interpretation before the SBBV slide), browser test, spec 8.8 and 9.5, README, report, SKILL.md, release 0.5.0.

---

## 5. Risks

- Captions with intervals get long when many variables change at once; the caption names at most three variables and says "and n others".
- Thresholds make the chain long (10 steps for `i`, plus `acc`); `until` and `events` keep slides short, and the history panel shows the whole chain at once at the end.
- Non-terminating programs with `thresholds: none` stop at `max_steps` with a warning, as `bbv-anim` does.

---

## 6. Decisions (touch base of 2026-10-01)

| # | Decision |
|---|---|
| 1 | Component `abstract-interp-anim`; module `lattice.bbv.absint`, trace `AbstractTrace`, listing `lattice:bbv/pseudocode/absint.txt`. |
| 2 | Direct comparison tests only (`if >(i, 0) goto ...`); no tracking of boolean temporaries (boolean blindness stays). |
| 3 | Threshold widening at every join, thesis thresholds, `sign` and `none` presets. |
| 4 | Intervals for integers only. |
| 5 | Intervals and types inform each other; fixnum width option, default 62 bits. |
| 6 | Parameter annotations in the function header, honoured by `bbv-anim` too. |
| 7 | Entry context inside the block, exit context in the tooltip. |
| 8 | History as a panel chain with `∪` and `∇` markers. |
| 9 | Block bands drawing, as `bbv-cfg`. |
| 10 | Example slides: sum-to-n with the history panel, fact (figure 4). |
| 11 | Release 0.5.0. |
| 12 | Green light given. |

## 7. Questions asked at the touch base (kept for the record)

1. **Name.** `ai-anim` (with `AbstractTrace` and `lattice.bbv.ai`), or `absint-anim`?
2. **Comparison tests.** Direct tests only (`if >(i, 0) goto ...`), or also tracking of boolean temporaries (`tmp = >(i, 0)` then `if tmp`)? Recommendation: both, the direct form in phase A, the tracked form in phase B.
3. **Widening.** Threshold widening reproducing figure 2 exactly (0, 1, 2, 127, 128, 2^31-1, 2^31, 2^63-1, 2^63, ∞ and negatives), applied at every join (sound and simplest), with `sign` and `none` presets. Or only at loop heads?
4. **Flonums.** No intervals for flonums (integers only), as the figures suggest?
5. **Intervals and types.** Let an interval decide `fx` versus `fx | bg` (fixnum width an option, default 62 bits), and let `fixnum?` clip the interval? Or keep the two domains independent?
6. **Entry contexts.** Parameter annotations in the function header (`function fact(n: fx | bg)`), also honoured by `bbv-anim` as the generic entry context? Or an `assume:` option on the block only?
7. **Display.** Entry contexts only inside blocks (as figures 1 and 4), with the exit context in the tooltip? Or both visible?
8. **History panel.** Is the chain of a tracked variable with `∪`/`∇` markers the right rendering of figure 2's red path, or do you want a drawn lattice (out of scope here, could be a later component)?
9. **Layout.** Reuse the block bands drawing of `bbv-cfg` (same look on consecutive slides) rather than a Graphviz spline layout?
10. **Example.** Slides to add: sum-to-n with history, fact (figure 4), `find` under abstract interpretation right before the SBBV slide. Anything else, for example `narrowing: false` on fact as a detour?
11. **Release.** 0.5.0 with these three phases, roughly three days.
12. **Green light?**
