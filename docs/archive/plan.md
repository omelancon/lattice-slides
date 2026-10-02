# Plan: animated basic block versioning for Lattice

*Phase document, 2026-09-30. Proposes two components, `bbv-anim` and `bbv-cfg`, that animate the specialization of control-flow graphs by Static Basic Block Versioning (SBBV) and Lambda Versioning (ΛV). Sources read and what they contribute: `reading-notes.md` (same folder). Nothing here is implemented yet; section 6 lists the questions to settle first.*

---

## 1. Summary

Add a build-time Python model of SBBV and ΛV, run it on a small program written by the author, record every step of the algorithm as a frame, and replay those frames in the browser as a growing specialized CFG: versions appear as they are queued and specialized, merge candidates light up, merged versions vanish, unreachable subgraphs fade, and, for ΛV, entry points, exit sites and indexed return points come and go across functions. The visual language follows the thesis figures (block label, `;; x: fx` context header, specialized code, starred entries, dashed `[i]` return edges), with the blog post's origin colours and dashed queued versions on top.

The deliverable fits Lattice's split exactly: Python does the algorithm, the layout and the captions; the runtime only draws a state and glides between two known positions on a single step, as `tree-anim` already does.

---

## 2. Goals and non-goals for this phase

Goals:

1. A faithful, readable SBBV (thesis algorithms 1.1 to 1.7) and ΛV (algorithms 2.1 to 2.10) on a small IR, deterministic, with the three merge heuristics of the thesis (similarity, arithmetic, random) and a pluggable version limit.
2. One frame per algorithm event, with an automatic caption, so an animation of `find` or `fact` needs no hand-written frames.
3. A stable, meaningful layout: versions of one origin block stay on the origin's row, in creation order; nodes glide on single steps and never jump on other moves.
4. Composition with existing Lattice features: a static source CFG that follows the animation (highlighting the block being specialized), a `code` block that follows it (highlighting the program line or the algorithm line), `panel:` for the queue and version counts, timelines, PDF export.
5. An example deck reproducing the thesis figures 6 (find), 14 and 15 (square/power4), 16 (fact), plus tests and documentation updates (spec 8.8 and 9.1, README, report, SKILL.md).

Non-goals (can become later phases, see section 5):

- Running the real Gambit implementation at build time (an importer of its `--plot` state stream is sketched but not committed to).
- Interval analysis, vector bounds, constants and closures in contexts: the model tracks types, equivalence classes and known callee identity only, which is what ΛV in the thesis does.
- Compiling Scheme: authors write the CPS-shaped IR directly (text or Python). A tiny Scheme front end is listed as an option.
- Live controls in the slide (version limit input as in the blog): Lattice expresses alternatives with branches and detours instead.

---

## 3. Design

### 3.1 What the author writes

````markdown
# SBBV specializes `find` {#find-sbbv}

:::: columns
::: column {width=2fr}
```bbv-cfg {#src program="bbv/find.bbv" follow=trace}
```
:::
::: column {width=3fr}
```bbv-anim {#trace program="bbv/find.bbv" algorithm=sbbv limit=2 heuristic=similarity height=420}
panel: [queue, versions]
```
:::
::::
````

`program` names a file in the text IR below (`.bbv`), or a Python function returning a `Program` (`"file.py:fn"`, resolved with `ctx.call` like every other trace). A program can also be written inline in the block body when the block has no other YAML (`body: text` mode; see question 2). Functions, blocks and primitives are named; nothing is generated from Scheme.

Text IR, `bbv/find.bbv` (the `find` function of thesis figure 6, checks inlined):

```
function find(p, lst)
A:  if pair?(lst) goto B else goto L
L:  return #f
B:  if procedure?(p) goto D else goto E
E:  fail
D:  if pair?(lst) goto F else goto K
K:  fail
F:  tmp = car(lst)
    call p(tmp) -> G(p, lst)
G(p, lst, #res):
    if #res goto H else goto J
H:  if pair?(lst) goto I2 else goto I
I:  fail
I2: return car(lst)
J:  if pair?(lst) goto J2 else goto M
M:  fail
J2: lst = cdr(lst)
    goto A
```

Rules of the text IR (grammar in the spec once implemented):

- `function NAME(params)` opens a function; the first block is its entry. Blocks are `LABEL:` or `LABEL(params):`; without an explicit list the parameters are the variables live at the block, computed by the parser (so the common case needs no lists, as lambda-lifting would produce them).
- Instructions: `x = prim(args)`, `x = y`, `if TEST goto A else goto B` (TEST is a variable or a type test such as `fixnum?(x)`), `goto A` or `goto A(args)` (positional rebinding of the target's parameters), `call f(args) -> K(vars)` (the return point `K` receives `vars` plus `#res`), `return v`, `fail`.
- Primitives come from a table with a type signature and, for type tests, the narrowing rule for each branch: `fixnum?` narrows to `fx` / `!fx`, `fx+?` returns `fx | #f`, `##*` returns `fx | fl | bg`, `car` requires `pair` and returns `⊤`. Authors extend the table in YAML (`prims:`) or Python.
- Types: the thesis lattice by default, `fx bg fl bool nil pair str proc other`, written `fx`, `fx|fl`, `!fx`, `any`, `⊥`. Contexts print as in the figures (`;; n: fx | fl | bg`). Equivalence classes print `a/b: fx`.
- For ΛV, operators are ordinary functions of the program (thesis 3.1.2), for example `function *(a, b)` with a per-function `limit` override (`rts-version-limit` in the implementation). Calls to functions are `call`; calls to primitives are assignments. A program may mark functions `hidden` so they take part in the analysis but are not drawn (figure 16 draws only `fact`, the operators appear in the call text as `=[X]`).

A Python DSL builds the same objects (`Program`, `Function`, `Block`, instruction constructors) for authors who prefer to generate programs, and it is what the parser produces.

### 3.2 Package `lattice.bbv`

```
src/lattice/bbv/
  __init__.py     public names: Program, Function, Block, parse, sbbv, lv, VersioningTrace
  types.py        type lattice (bitset over primitive types), union, intersection, complement,
                  narrowing, printing; Context (var -> type, equivalence classes, own parameters)
  prims.py        primitive table: signature, result type, narrowing rules for tests
  ir.py           Program / Function / Block / instructions; text parser; liveness for implicit params
  sbbv.py         SBBV: versions, queue, getOrCreateVersion, merged chains, reachability, specialize
  lv.py           ΛV on top of sbbv.py: entries, exits, call sites, return points, cascades
  heuristics.py   similarity, arithmetic, random (thesis appendix A), pluggable distance functions
  trace.py        VersioningTrace: events -> frames, captions, panel, meta
  layout.py       per-frame positions ("block bands"), node sizes, shared box
```

The algorithms are written as plain loops that call an `emit(event, ...)` hook; `VersioningTrace` turns events into frames. Keeping the algorithm separate from the trace keeps the tests about correctness independent from the tests about frames, and lets a future importer produce frames from another source.

SBBV, faithful to chapter 2:

- `Version(block, context, body, contextAfter, merged)`; `block.allVersions` and `block.reachableVersions` as in figure 7. `getVersion` follows `merged` chains. The queue is FIFO (breadth first); `traversal` can later add the other orders of the implementation.
- Main loop: dequeue; skip unreachable or done; if `|reachableVersions| > limit` then `mergeSome`; specialize if still reachable. Reachability is recomputed by a search from the entry versions after every edge change (graphs have tens of nodes; the Even-Shiloach structure of the real implementation is not needed and would obscure the algorithm).
- `specialize` walks instructions: assignments update the context with the primitive's result type; a type test with a decided outcome becomes a `goto` and the test line is recorded as removed (drawn struck through in instruction granularity); `goto` filters the context to the target parameters (positional rebinding applied first); `fail` and `return` halt the block.
- Merge: the heuristic picks versions among the reachable ones; the union with widening (the lattice is finite, so union) creates or reuses a version; merged versions point to it; edges are redirected; unreachable versions drop out and may be reconnected later, which the trace reports as in the blog ("reachable again").
- Post-processing at the end: jump cascade removal is applied only to the final frame (`done` event) so that the animation stays honest about what the algorithm does.

ΛV, faithful to chapter 3 (each item names the algorithm it implements):

- Entry versions per (function, argument context); `markEntry`, `callSites`, `exitSites` (figure 17). Contexts carry the function's own parameter types so that exits refine the caller's arguments.
- `specializeCall` (2.7): the callee must be a single known function (the type of the callee variable includes function identities; `call f(...)` with a literal name is the common case). The return point is the version of the return block for `callContext ∩ exitSite.contextAfter`, one per exit site already reachable from that entry.
- `specializeExit` (2.6), `addReturnPoints` (2.8), `removeReturnPoints` (2.9), `mergeSome` with `redirectEdges` (2.10). Multi-source reachability is recomputed per entry point (one search per unmerged entry, as the implementation does).
- Generic entries of every function are enqueued when the queue first empties (as in `lambda-versioning.scm`), unused entries are cleaned up at the end, and return point indices are allocated at the end (`[0]`, `[1]`, ... per function) so that edge labels are stable across all frames: the labels use the final allocation from frame 0.
- Equivalence classes (`a/b`) are part of contexts from the start, since figure 15 needs them and they only affect narrowing and printing.
- `algorithm: sbbv` on a program with calls treats calls as opaque (result `⊤`, no interprocedural edges), which is what `--sbbv` does in the implementation; a deck can therefore show SBBV and ΛV on the same program.

Heuristics: `similarity` (Hamming per variable plus the specificity bias), `arithmetic` (contexts with a possible bignum are merged first, pure `fx` or `fl` contexts are kept apart, Hamming as tiebreaker), `random` (seeded from `ctx.seed`). Optionally the blog's backward score as `similarity-backward` (question 12).

### 3.3 Trace and frames

`VersioningTrace` is a `Trace` (spec 9.1) whose frames have this shape (full states; the frame store may switch to keyframes above the size threshold as usual):

```json
{
  "nodes": { "7": { "state": "queued", "pos": [312.0, 96.0], "marks": ["entry"] } },
  "edges": { "3->7": { "kind": "true", "state": "new" }, "5->9": { "kind": "return", "label": "[1]" } },
  "caption": "Block B has 3 versions, limit is 2: merge B2 and B3 into B4 (lst: fx | fl)",
  "panel": { "queue": ["A2", "F1"], "versions": { "A": 2, "B": 1 }, "checks": 4 },
  "focus": ["7", "9"]
}
```

Static tables go in `data` next to the store, not in every frame: `program` (functions, origin blocks with their code and colour index, source CFG edges) and `versions` (per version id: origin block, label such as `A2`, context lines, specialized code lines once known, kind: `version`, `return-point`). Node sizes are computed once per version from its final text so a box never resizes.

Events, each producing one frame with an automatic caption (`caption: none` disables, `events:` filters):

| Event | SBBV | ΛV | Frame shows |
|---|---|---|---|
| `start` | yes | yes | the entry version queued |
| `dequeue` | yes | yes | the version being processed (`active`) |
| `must-merge` | yes | yes | all versions of the block highlighted, caption gives count and limit |
| `merge` | yes | yes | candidates in `merge` state, result in `merged` state, redirected edges `new`, versions that became unreachable `gone` |
| `specialize` | yes | yes | code of the version filled, successor versions `queued`, `new` edges, versions reachable again |
| `entry` | | yes | a specialized entry point created for a call (star mark) |
| `exit` | | yes | a version marked as exit site |
| `return-points` | | yes | return points added (`new`) or removed (`gone`) for a call site, with the entry/exit pair in the caption |
| `generic-entries` | | yes | generic entries of the remaining functions queued |
| `done` | yes | yes | final specialized CFG, jump cascades removed, unreachable versions gone |

With `granularity: instruction`, `specialize` expands into one frame per instruction of the block (the code appears line by line, removed tests struck through, a decided `if` shown as `goto`), which is the blog's single-block canvas as an animation. Default is `block`.

`meta` per frame carries `{"event", "block": origin block id, "function", "versions": [ids], "line": <program line of the instruction, for instruction granularity>}` so that followers can use it: a `code` block showing the `.bbv` program highlights the current block's lines, and `bbv-cfg` highlights the origin block. An optional `algo_lines: true` puts in `meta["lines"]` the lines of a bundled pseudo-code listing (`lattice/bbv/pseudocode/sbbv.txt`, `lv.txt`, the thesis algorithms) so that a `code` block showing that listing follows the animation (question 10).

`until: N` stops after N events (`--partial`), `max_steps` guards non-termination (warning LT046 and a truncated animation rather than a hung build).

### 3.4 Layout: block bands

Decision 10 says graphs keep one layout and trees move because their shape changes. A specialized CFG is a tree-like case: versions appear and disappear. One Graphviz layout on the union of every version ever created would leave holes and drift far from the thesis figures. Per-frame Graphviz layouts would move everything on each step. The layout below is stable, cheap and reads like the figures:

1. The source CFG of each function is laid out once with Graphviz `dot` (`rankdir=TB`; `LR` as an option), through `ctx.layout`, giving every origin block a rank (row) and an x order. Without Graphviz, ranks come from a breadth-first search and x order from block order (the existing NetworkX fallback is not needed).
2. Functions are placed side by side, left to right, in program order (figure 14: `power4` then `square`); hidden functions take no space.
3. Per frame, for each row of a function, the live versions are sorted by (origin x order, creation id) and packed left to right with a fixed gap, then the row is centred in the function's column. Return points are versions of return blocks, so they get their own row under the call block, like `B1 B2 B3` in figure 14.
4. The box is the union over all frames (per function width and total height), so the SVG `viewBox` never changes; each frame is centred in it as `tree_layouts` does.
5. Positions are stored in the frame (`pos`), the runtime places nodes and draws edges from those positions. On a single step the runtime interpolates positions (same easing and duration as `tree-anim.js`); on any other move it places directly. Edges are straight or lightly curved segments from the bottom centre of the source to the top centre of the target; back edges (target row above or equal) curve around the outside of the column. Edge geometry is derived from node positions in the runtime, as `tree-anim` does, because it must follow the glide.

Node size comes from the text: label line, context lines (when `show` includes `context`) and code lines (when it includes `code`), measured with a fixed monospace advance width at build time, capped by `max_lines` with an ellipsis. `show: label|context|code` is a list; the default is `[label, context, code]` as in the figures, and a slide that only needs the shape can use `[label]` to fit many versions.

### 3.5 Runtime and styling

One runtime file `bbv.js` registers both `bbv-anim` and `bbv-cfg` (runtime files are deduplicated by name in `emit.assemble`). Structure copied from `tree-anim.js`: `mount` builds the SVG and the panel and caption slots once; `show` creates DOM for versions the first time they appear and reuses it; nodes that leave a frame get the `lt-gone` treatment (fade) and are hidden afterwards.

A node is a `<g class="lt-bbv-node st-STATE origin-K">` with a rounded rect, a label text (`A2`, star for entries), context lines in the muted italic style of `;;` comments, and code lines in the code font; a queued node shows the label and context and an ellipsis in place of code. Node states and edge kinds get classes styled in `lattice.css` from theme tokens: `queued` (dashed stroke), `active` (accent stroke, thick), `merge` (warn), `merged` (good), `new` (accent, fading), `gone` (opacity 0), `dim` (versions outside `focus`), `entry` (star badge), `exit` (double bottom rule). Origin colours: taken at build time from `ctx.palette["series"]` (the theme's plot series, so they follow the theme without new CSS tokens), lightened and stored per origin block in `data`, applied as the node fill; optional (`colors: origin|none`). Edge kinds: `goto` (solid), `true`/`false` (solid with `#t`/`#f` labels), `call` (dotted, drawn only with `call_edges: true`), `return` (dashed with `[i]` label); edge states `new`, `gone`, `redirected`.

Hovering a node shows a tooltip with the full context and code (pointer events inside `el` are allowed; useful when `show: [label]`). No keyboard handling. Print mode works unchanged since ids are only used for the arrowhead markers, which the core rewrites.

`bbv-cfg` draws the source CFG of one function (or all) with the same node drawing and the Graphviz edge routes of step 1 above; it is static (1 position) unless it follows a `bbv-anim`, in which case it has the leader's position count and highlights `meta[i]["block"]` (the origin being specialized) and, for merges, the block whose versions merge.

### 3.6 Options

`bbv-anim` (body: YAML, `extra="allow"` so unknown keys go to the program function when `program` is a Python reference):

| Option | Default | Meaning |
|---|---|---|
| `program` | required | `.bbv` file, or `file.py:function` returning a `Program`; inline text when the body is the program (question 2) |
| `algorithm` | `sbbv` | `sbbv` or `lv` |
| `limit` | `2` | version limit; per-function overrides with `limits: {"*": none}` |
| `heuristic` | `similarity` | `similarity`, `arithmetic`, `random` |
| `entry` | first function | function to start from (`$top-level` in the implementation) |
| `functions` | all | functions drawn; the others are analysed but hidden |
| `events` | all | event kinds kept as frames |
| `granularity` | `block` | `block` or `instruction` |
| `until` | none | stop after N events |
| `show` | `[label, context, code]` | node contents |
| `colors` | `origin` | `origin` or `none` |
| `call_edges` | `false` | draw call-site to entry edges |
| `direction` | `TB` | `TB` or `LR` |
| `panel` | none | keys among `queue`, `versions`, `checks`, `limit`, `merges` |
| `caption` | `auto` | `auto` or `none` |
| `algo_lines` | `false` | put pseudo-code line numbers in `meta` |
| `height` | none | canvas height in px |

`bbv-cfg`: `program`, `functions`, `show`, `colors`, `direction`, `height`; `follow=` as any component.

### 3.7 Diagnostics

Program errors (parse errors, unknown block, unknown primitive, a call to an unknown function, a `.bbv` file missing) are `ComponentError`s, reported as LT022 at the block (LT045 for the missing file), so no new codes are needed. Non-convergence within `max_steps` is a warning through `ctx.warn` (LT046). If a new code becomes necessary, the next free one is LT054.

---

## 4. Implementation strategy

Work is cut so that every phase leaves the suite green and something visible in an example.

**Phase 0, model and SBBV (2 to 3 days).** `types.py`, `prims.py`, `ir.py` with the text parser and liveness, `sbbv.py`, `heuristics.py`, `trace.py` with events and captions; `tests/test_bbv.py` checks the parser, narrowing, and the `find` example against figure 6 (two reachable versions of `A`, the loop `A2 → F → A2` carries no `procedure?` test, unreachable `pair?` tests gone), plus determinism (two runs give identical frames) and frame store validity. No rendering yet.

**Phase 1, component and runtime (2 to 3 days).** `layout.py` (block bands, sizes, shared box), `components/bbv.py` with `bbv-anim` and `bbv-cfg`, `runtime/components/bbv.js`, styles in `lattice.css` (existing tokens suffice; origin colours come from the build-time palette). Example `examples/07-basic-block-versioning` with the `find` slides (source CFG following the animation, code following it, a branch between `limit=2` and `limit=3`, a detour on the merge heuristic). Browser test in `tests/test_runtime.py` (mount, forward, backward, jump, scrub, print). Screenshots checked. Spec 8.8 and 9.1 rows, README table, report 3.10 and the roadmap, SKILL.md structure, changelog 15.

**Phase 2, ΛV (3 to 4 days).** `lv.py` with entries, exits, call sites, return points, cascades, generic entries, index allocation and hidden functions; equivalence classes; `algorithm: lv` in the component; return edges and star marks in the runtime. Example slides reproducing figures 14 and 15 (`square`/`power4`, then operators as hyperfunctions) and figure 16 (`fact` with hidden operators), a slide comparing `algorithm: sbbv` and `lv` on `fact`. Tests against the figures (three return points on the first call of `power4`, `Z` needs only `[1]`, `fact` has two entries with return points `[0]` and `[1]`).

**Phase 3, polish and options (1 to 2 days).** Instruction granularity, `until`, `events`, `focus`/`dim`, tooltips, `algo_lines` with the bundled pseudo-code, PDF check of the example, documentation coherence pass (`check_docs.py`, full reread), version bump to 0.4.0.

**Later, if wanted (not scheduled).** Importer for the Gambit `--plot` state stream (frames from `addNodeStep` calls, origin blocks from `multifId@@@blockId`, layout by block bands; needs the `.plot.html` file as input rather than Gambit at build time); a tiny Scheme front end (`define`, `if`, `let`, primitive and function calls) with CPS and lambda lifting into the IR; other traversal orders; the blog's backward-score heuristic.

Verification at each phase: `pytest` (all suites), `python scripts/build_examples.py`, `snapshot.py` on the new example, `lattice pdf` of the example, `python scripts/check_docs.py`.

---

## 5. Risks and how the design handles them

- **Frame count.** ΛV on `fact` with operators as functions produces a few hundred events. `events`, `until`, `functions` and `granularity` keep a slide to what it teaches; timelines let a slide jump through ranges; the keyframed store bounds data size. The example deck will report frame counts so we know the real numbers early (phase 2).
- **Layout legibility.** Rows can get wide when a block has many live versions with code shown. `show: [label, context]` and `limit` keep figures within the slide; the shared box scales the SVG, and `height` caps it. If rows still overflow, a second strategy (fixed slot per version over the whole run, holes allowed) is a small addition to `layout.py`.
- **Fidelity vs. simplicity.** The Python model mirrors the thesis algorithms, not the implementation's engineering (Even-Shiloach, RTS minimisation, constants). Tests pin the figures, which is what the slides must reproduce. Anything the model cannot express is reported as a `ComponentError` rather than approximated silently.
- **Text IR scope creep.** The grammar is deliberately line-based with six instruction forms. Anything richer (expressions, Scheme) is a front end that produces the same objects later.
- **Runtime computation.** Edge geometry from positions during a glide is the only computation in the browser, the same trade `tree-anim` makes.

---

## 6. Decisions (touch base of 2026-09-30)

Olivier answered the questions below; the plan above is implemented as written except where noted here.

| # | Decision |
|---|---|
| 1 | Built-in components (`src/lattice/components/bbv.py`, model in `src/lattice/bbv/`). |
| 2 | Text IR (`.bbv` files or inline) plus the Python DSL. No Scheme front end in this phase. |
| 3 | Thesis types with `#f` as its own type: `fx bg fl true false nil pair str proc other`. |
| 4 | Thesis figure style with the blog's origin colours as node fill. |
| 5 | Block bands layout, top to bottom by default, functions side by side. |
| 6 | Companions through followers (`bbv-cfg follow=`, `code follow=`). |
| 7 | Version limits as branches or detours; no live control in the component. |
| 8 | One frame per event by default; instruction granularity in phase 3. |
| 9 | Figures 14, 15 and 16 are all reproduced in the example. The thesis took liberties with types and heuristics to keep the figures short, so the real algorithm may yield slightly different results; the tests pin the properties that matter (return point counts, entries, checks removed), not the exact drawing. Implementation order (generic entries when the queue first empties, unused entries removed at the end). |
| 10 | `algo_lines` with bundled listings of the thesis pseudo-code. |
| 11 | Importer of the Gambit `--plot` stream: later, keep the frame format compatible. |
| 12 | Heuristics `similarity`, `arithmetic`, `random`; breadth first only. |
| 13 | Names as proposed; release 0.4.0. |
| 14 | All phases in one release, touch base after each phase. |
| 15 | Green light given. |

## 7. Questions asked at the touch base (kept for the record)

Answers that change the plan are marked (*shapes phase 0*).

1. **Built in or plugin?** The plan makes `bbv-anim` and `bbv-cfg` built-in components under `src/lattice/components/bbv.py` with the model in `src/lattice/bbv/`, documented in spec 8.8 like `tree-anim`. The alternative is a first packaged plugin (`plugins/lattice_bbv/`, activated with `plugins: [lattice_bbv]`), which keeps the core generic but adds packaging and a second test path. Recommendation: built in, since compiler talks are within the tool's stated domain. (*shapes phase 0*)

2. **How programs are written.** The plan offers the text IR of 3.1 in a `.bbv` file (or inline in the block body) and a Python DSL. Is the text IR the right primary form, and does the syntax read well to you (`if T goto A else goto B`, `call f(args) -> K(vars)`, `#res`)? Would you rather write a Scheme subset and have a small CPS front end (listed as later work)? (*shapes phase 0*)

3. **Type lattice.** Default to the thesis types (`fx bg fl bool nil pair str proc other`, printed `fx | fl | bg`, `!fx`) rather than the blog's `int float array`? Should `#f` be its own type (needed for `fx*?` returning `fx | #f`) or is `bool` enough? (*shapes phase 0*)

4. **Visual style.** Thesis figures (label, `;; ctx` header, code lines, `∗` entries, dashed `[i]` return edges, `#t`/`#f` edge labels) as the default, with the blog's origin colours as a light fill: agreed? Or should colours be off by default?

5. **Layout.** Block bands (rows are origin ranks, versions side by side, glide on single steps) as described in 3.4, top-to-bottom by default, functions side by side. Any preference for left-to-right, or for keeping every version at a fixed slot for the whole run (holes instead of shifting)?

6. **Companion panels.** Are `bbv-cfg follow=trace` (source CFG highlighting the current origin block) and `code follow=trace` (program text highlighting the current block) the pairings you want on slides, or would you rather have the source CFG drawn inside the same component (blog style, two panels in one canvas)?

7. **Version limit interactivity.** The blog lets the reader change the limit live. In Lattice the plan uses branches or detours (one `bbv-anim` per limit) rather than a control inside the component. Is that acceptable, or do you want a `limits: [1, 2, 3]` option that precomputes several runs and lets the presenter switch with a click (this complicates the position contract since runs have different frame counts)?

8. **Event granularity defaults.** Is one frame per event of the table in 3.3 the right default (roughly 2 to 3 frames per dequeued version), or should `dequeue` and `specialize` be one frame by default? Is instruction granularity (code appearing line by line, removed tests struck through) wanted in phase 1 or can it wait for phase 3?

9. **ΛV scope.** Which figures must the example reproduce exactly: 14 (power4/square with inlined operators), 15 (operators as hyperfunctions with `a/b` equivalence classes), 16 (fact with hidden operators)? Should hidden functions also be drawable on a detour slide ("what happens inside `*`")? Is the ordering of the implementation (generic entries enqueued when the queue first empties, unused entries removed at the end) what you want shown, or the simpler order of the thesis text?

10. **Following the algorithm text.** Do you want frames to carry lines into a bundled pseudo-code listing of algorithms 1.1 to 1.7 and 2.1 to 2.10 (`algo_lines`), so a `code` block showing the algorithm highlights the line being executed? If yes, should the listing be the thesis pseudo-code verbatim or the Python implementation itself (then the `code` block shows real source, as the AVL example does)?

11. **Importer for the real implementation.** Is reading a `.plot.html` produced by `gsi main.scm --plot` (the `addNodeStep` state stream) something you want in this phase, later, or not at all? It would give the real ΛV on real Scheme programs at the cost of a Gambit-side step and a less controlled layout.

12. **Heuristics.** Ship `similarity`, `arithmetic` and `random` as in the thesis. Also the blog's backward score (`similarity-backward`)? Any need for the traversal orders other than breadth first?

13. **Naming and version.** `bbv-anim` / `bbv-cfg`, package `lattice.bbv`, trace class `VersioningTrace`, example `07-basic-block-versioning`, release as 0.4.0. Alternatives: `cfg-anim`, `versioning-anim`.

14. **Time budget.** Phases 0 to 3 as scheduled total roughly two weeks of focused work. If you want something on screen sooner, phase 0 and 1 can ship SBBV alone as 0.4.0 and ΛV as 0.5.0.
