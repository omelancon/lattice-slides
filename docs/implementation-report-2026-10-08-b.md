# Implementation report: paths through calls (Lattice 0.31.0, 2026-10-08)

The defense slide "Example: polynomial and square" (`phd_defense/src/lv.md`) runs ΛV on `polynomial-square.bbv`, whose `main()` reads its argument (`x = read()`), and wanted to light the way a flonum takes through the whole program once the run is done. `paths` was refused with `algorithm: lv`, `input` needed parameters, and a variable computed on the way (`x = read()`) was never narrowed. The rules are in spec 9.5 (Paths, the walk, the frame's `lit`), with 8.8 and 15; the rationale is design decision 41 (decision 38 amended in place). The design was reviewed by Olivier before the work (`claude/v0.31-design.md` in the project): one walk for SBBV and ΛV, only the edges taken are lit, `reads_exhausted` with `any` by default and a list repeated as a pattern, unused indices faded, version 0.31.0 with this program in the manual. During the work he added `overflow: maybe | never | always`, to show a fixnum path where no overflow happens.

## 1. What was built

- **The walk** (`bbv/paths.py`, new): an abstract run of the program on the versions of the final graph, with a path context of its own. A state is a version, the position in `reads` and an activation; contexts are joined per state (widened with `intervals`).
  - Entering a version requires its entry context to meet the path's types on every variable; the path context becomes their intersection.
  - Instructions run again through the specializer's own transfer functions, now shared: `assign_context`, `move_context`, `exit_context` and `goto_context` were extracted from `Specializer.specialize` (`sbbv.py`), and `return_context_of` from `LambdaVersioning.return_context` (`lv.py`). `specialize` and `reconcile_call_site` call them, so their behaviour is unchanged (the suite is green before and after the extraction). `read()` takes the next type of `reads`, then of `reads_exhausted`; `overflow` adjusts the result of the operations marked `overflow` in the primitive table (`fx+?`, `fx-?`, `fx*?`; new `Prim.overflow` field).
  - Kept tests follow the outcomes the path context allows; removed tests and `goto` follow their edge.
  - Calls are matched by **summaries per activation** (the callee's entry version, the read position and the entry context; with `intervals`, the entry version and position only). An activation is walked once; its exits are its summary, given back to every call site that started it through that call site's return edge for the exit, at the call and whenever the summary grows. The exits of the entry function's own activation end the path. Opaque calls (SBBV, unknown callee) follow their return edge with `#res: any`.
- **Frames** (`bbv/trace.py`): `paths` accepts `algorithm: lv`; new keys `reads`, `reads_exhausted`, `overflow`; `input` optional (and `{}`); `versions` takes `FUNCTION/LABEL` and reports an ambiguous label. A walked path lights the edges it took (call edges included, drawn with `call_edges`); a return edge carries `lit`, the indices it was taken for (for `versions`, the indices of its listed exits), resolved with the labels in `finalize`. The caption names the inputs, the reads (`(read) → fl, fx`) and `overflow` when not `maybe`, and joins the chips with `→` when every version has at most one transition in and out (an exit to its return point counting as one, for `versions` too). `meta.blocks` spans every drawn function, which `bbv-cfg` already handled.
- **Runtime** (`bbv.js`, `lattice.css`): `edgeLabel` draws a label with `lit` as `tspan`s, `.lt-bbv-edge-lit` (green, bold) and `.lt-bbv-edge-unlit` (35 % fill opacity); the text is unchanged, so the edge's mark keeps its size.
- **Manual**: "Writing a path" updated (no "SBBV only", the new semantics), a new slide "Paths through calls" (`bbv-paths-calls`) on `user_manual/programs/polynomial-square.bbv` with `reads: [fl]` and `reads: [fx]` plus `overflow: never`, call edges on and an arrow at the lit `[2]`; the options table row.
- **Docs**: spec (above); README (`bbv-anim` row, version); `docs/USER_SKILL.md` (the paths row, a "Rules that bite" line on `end-N` and quoting `#f`); `docs/SKILL.md` (`paths.py` in the structure, a pitfall on the shared transfer functions, test rows); design report (decisions 38 and 41, roadmap v0.31); todo (the 0.28.0 ΛV and may-reach items done, four 0.31.0 items); the 0.30 report moved to `docs/archive/` and listed in its README; version 0.31.0.

**Change from the agreed design.** The design capped a call stack (`depth`, default 8). Tests showed the number of stacks grows as the call sites to the power of the depth: a doubly recursive `fib` needed 71,000 states and 4 s per path at depth 8. Summaries per activation match calls and returns exactly at any depth and end on their own (the same `fib`: under 0.3 s), so there is no `depth` key. Olivier was told during the work; the todo asks whether he wants the key anyway.

## 2. Results on the defense program (limit 3, `arithmetic`, entry `main`)

| Path | Versions (walk order) | Lit return indices | Tests |
|---|---|---|---|
| `reads: [fl]` | M1 → A1 → S1 → V1 → X1 → B3 → F1 → G1 → H1 → N3 | A1->B3 [2], M1->N3 [3] | 2 |
| `reads: [fx]` | M1 A1 S1 T1 U1 W1 B1 B5 C1 C2 F2 D1 J1 R1 E1 N1 N2 | A1->B1 [0], A1->B5 [1] (not [3]), M1->N1 [0] [2] (not [4]), M1->N2 [1] | 5 |
| `reads: [fx]`, `overflow: never` | M1 → A1 → S1 → T1 → U1 → B1 → C1 → D1 → R1 → N2 | A1->B1 [0], M1->N2 [1] | 3 |
| `versions:` as in the request | as `reads: [fl]`, same edges and lit indices | | 2 |

The first row is the expected result of the request, edge for edge. The SBBV paths of the 0.28 tests give the same versions as before.

**The defense slide** (not touched): with three paths after the run, the timeline must stop the run at its `done` frame before the final arrows, and the path frames come last. Checked on a copy of the slide built here:

```yaml
paths:
  - reads: [fl]
    caption: "(read) returns a flonum"
  - reads: [fx]
  - reads: [fx]
    overflow: never
```

with `- null` appended to the steps of `ex-notes`, and the end of the timeline:

```
ex-lv ..end-3                   # the rest of the run, up to its done frame
ex-idx-u 1                      # the four exit sites of square, with their followers
ex-idx-u end, ex-notes 20       # the return edge of index 0
ex-notes 21                     # B5 is passed at two indices
ex-lv end-2, ex-notes end       # the path of a flonum read()
ex-lv end-1                     # the path of a fixnum read()
ex-lv end                       # the path of a fixnum that does not overflow
```

## 3. Verification

- `pytest -rs`: 397 passed, 1 skipped (the optional Firefox test; Playwright's Firefox is not installed here), in Chromium. Before the change: 367 passed and the same skip. New tests:
  - `test_bbv.py`: the defense program by `reads: [fl]` (versions, edge kinds, labels and lit indices, caption, marks, meta across functions), by `reads: [fx]` (returns matched to their indices, C2->F3 left out), `overflow` never and always, the same path by `versions`, `input` optional or `{}` and `reads: []`, a hidden `square` walked through, reads in a loop with every form of `reads_exhausted` and its `error`, `input` with `reads`, a value computed on the way (the 0.28 todo case), an SBBV path through an opaque call, recursion (`fib`, timed), `FUNCTION/LABEL`, intervals on a loop, a ΛV deck with a follower and arrows (and LT022 for a bad `reads_exhausted`); the error table extended (the `lv` row is now valid).
  - `test_runtime.py`: `test_bbv_path_through_calls_lights_its_return_indices` (lit and faded `tspan`s, labels and marks the same as in the `done` frame, call edges on the path, the follower, back and forth).
- `python scripts/check_docs.py`, examples and manual rebuilt, `lattice check` of the manual without problems.
- Screenshots at 1280x720: the manual's "Paths through calls" at its two path frames (the arrow moved twice to clear the headings and X1), and the copy of the defense slide at its `done` frame and its first path frame.
- Not done: Firefox (the `tspan` labels use no browser-specific code); the dark theme (`--lt-good` is defined in both themes).
