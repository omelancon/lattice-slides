# Implementation report: merge heuristics on their own (Lattice 0.33.0, 2026-10-08)

The versioning animations show merges as one event among many, on a whole CFG. `bbv-merge` isolates the decision: a set of contexts of one block, merged two by two by the merge heuristic until the version limit holds, each merge in two steps (the pair picked, then the merge), on a complete graph whose edges show how far apart the contexts are. The design and Olivier's answers are in the project (`claude/v0.33-design.md`): edge size is the stroke width, thick for the nearest pairs; every node has the size of the largest node of the run; placements `circle` (default) and `distance` now, the others later; `random` has no distance, so it draws no edge and shows no distance, and nothing can set one; in `circle` the result of a merge takes the older context's place; placement `distance` with `random` is an error; contexts are listed in the block's body; version 0.33.0 with a manual slide.

## 1. What was built

- **The run** (`bbv/merging.py`, new). `MergeRun` builds a one-block program (the given `block` of `program` or `source`, or a synthetic block `NAME(vars): fail`), creates one version per context with `Specializer.get_or_create`, makes every one a root, and calls `Specializer.merge_some` with the chosen limit and heuristic (and the merge of SBBV, widening with `intervals`). It records the `must-merge` and `merge` events, plus, for each merge, whether the union is a new version and which version holds it. Nothing of the merge loop is copied, so the pair picked, the reuse of an existing context and the labels are those of `bbv-anim` by construction.
  - A union may be a context merged away earlier: it resolves to the version that context was merged into, and the run can end below the limit. The caption says "their union is C6, merged into C5 earlier" (found on the first test set, where `C1 ∪ C4` is `C6`'s context and `C6` had been merged into `C5`).
  - Frames: `start`, then `pick` and `merge` per merge, then `done` (`2m + 2` positions). Marks and edge states are those of `bbv-anim` (`merge`, `merged`, `gone`, `new`), plus the edge state `merge` for the pair and `dim` for the other edges in a pick frame. Captions use the rich markup (`limit`, `closest pair` or `random pair`, `merge`, `done`); the panel offers `contexts`, `limit`, `merges`, `distance`. `meta` carries `event` and `algo` (lines 5, 53 to 54, 55 to 57 of `sbbv.txt`), and with a program `block`, `function`, `lines`, `line`, so a pseudocode listing or a `bbv-cfg` can follow.
  - Widths: `x = log10(1 + d)` clamped to `log_range` (by default the least and greatest `x` over every edge of the run), mapped linearly onto `edge_width` (default `[1, 7]`), the nearest pair at the maximum.
  - Code: each context, merged ones included, is specialized by a fresh `Specializer` (`specialize` on a version outside the run), so its successors never reach the merge run; the node shows the body with decided tests struck through, and the enlarged block the exit context. A context item may give `code:` lines by hand.
- **Placements.**
  - `circle`: contexts evenly on an ellipse, from the top, clockwise (two contexts side by side). For each width ratio from 1 to 4 (step 0.125) the smallest radius with no two boxes closer than 28 px, for every count of nodes the run shows; the ratio whose drawing fits the room largest wins (the room as for `rank_wrap=auto`, or `fit_aspect`). In a merge frame a new result takes the older context's place, and the next frame spaces the nodes evenly again (they glide).
  - `distance`: classical scaling (power iteration on the double-centred squared targets) then 300 SMACOF iterations, in pure Python (no new dependency), on targets from 1 to 3 node diagonals given by the clamped logs; over every context of the run, so nodes never move. The rotation (5° steps), a scale down to 0.65 and a horizontal stretch up to 1.5 are chosen to fit the room, the least distorted drawing winning unless another is 2 % larger; overlapping boxes are then pushed apart along their axis of least overlap.
- **Component** (`components/bbv.py`, `bbv-merge`, on the `bbv.js` runtime). Options as in the spec row (8.8), errors as in spec 9.5. `random` with `edges`, `edge_width`, `log_range`, `edge_labels`, the panel key `distance` or `placement: distance` is a component error. `colors=context` gives each initial context a colour of the palette and a merged context the mix of its pair. `fit_aspect` (shared with the bands' parsing, now `_aspect`) sets the room the placement aims at, for a drawing in a column; the room computation of `rank_wrap=auto` became `_room`, used by both. Parts: a label (`h.C1`) and an edge `A--B` (`h.C1--C2`).
- **Runtime** (`bbv.js`). `bbv-merge` registers `showMerge`, which reuses `node`, `nodeState`, the panel, the caption and the glide; `placeMerge` draws each edge as a straight segment from border to border (none when the boxes overlap, as when the result covers the faded older context), its label and mark at the middle. The glide and the end of a frame (`glide`, `finish`) were factored out of `show`, unchanged except that the last tick of a glide places the nodes exactly at their target (the eased value left `37.599999` where a fresh load draws `37.6`; this also applies to `bbv-anim`). Caption tones for `closest pair` and `random pair`.
- **CSS.** `.lt-bbv-edge.st-merge path` takes `--lt-warn` (the colour of `mk-merge`); `.lt-bbv-dist path` has round caps. The width of a distance edge is an inline style, so the `stroke-width` of the edge states of `bbv-anim` never applies to it.
- **Manual**: a slide "Choosing what to merge" (`bbv-merge`): block `A` of `find.bbv`, four contexts, limit 1, `similarity`, `fit_aspect="7:4"` in a two-thirds column; a row in "Versioning options".
- **Docs**: spec 8.2 (parts), 8.8 (row, panel placement), 9.5 (Merge heuristics; Enlarging a block), 15; design report (roadmap v0.33, decision 43, later items); README (row, a sentence, version); `docs/USER_SKILL.md` (a feature row, a pitfall); `docs/SKILL.md` (structure, test rows, a pitfall); todo; the 0.32 report moved to `docs/archive/`.

## 2. Distances seen on the test contexts

Six contexts of `x` and `y` (`fx`, `fl`, `fx | fl`, `any`, `pair`, `nil` combinations):

| Heuristic | Distances | log10(1 + d) |
|---|---|---|
| `similarity` | 1.7M to 13.2M | 6.2 to 7.1 |
| `arithmetic` | 16 to 480k | 1.2 to 5.7 |

Hence the default `log_range: auto`: a fixed range would draw every `similarity` edge at almost one width.

## 3. Verification

- `pytest -rs`: 439 passed, 1 skipped (the Firefox check, Firefox not installed); 408 before, 31 new tests (30 in `test_bbv.py`, 1 in `test_runtime.py`).
- The instance data of every versioning drawing of example 07 and of the manual is identical to 0.32.0's (compared through `build_deck`, both versions building their own sources).
- `scripts/check_docs.py` clean; examples and manual rebuilt.
- Screenshots in Chromium at 1280x720 of the manual slide at every position, and of a scratch deck with both placements, both distance heuristics, `random`, code and `colors=context`: no overlap, no console error. Firefox was not available.

## 4. Not done, or left open

- Placements `row` (merge tree order), `grid` and `manual`, and contexts read from a `bbv-anim` run: in the todo, as agreed.
- In `circle`, the result of a merge covers the faded older context for one frame, so only the other context is seen fading (Olivier's choice of place); to judge on screen.
- `placement=distance` is honest but less compact than `circle` (a run of six contexts places ten nodes); its text is smaller at the same height.
- No git commit (see the todo).

## 5. Lattice 0.33.1 (2026-10-09): a merge in three steps

Olivier's review: a result spawned over the older context did not read as a merge. Each merge now takes three steps.

- **Frames** (`bbv/merging.py`): `pick` (unchanged); `merge`, the pair at its meeting point (the place of the context that remains, or of an existing result drawn elsewhere, or halfway between the two for a result not drawn yet), the contexts that leave marked `absorbed`, the result `merged` (`arrive: true` when it was not drawn yet), the contexts left alone `dim` with only their edges, dimmed; `settle`, everything back in the placement, the result still `merged`, the edges of a new result `new`; the last settle is the `done` frame. A run of `m >= 1` merges has `3m + 1` positions. Meeting points are computed after the placement (`_meet`), from the pick frame; the circle places every other frame from its order of contexts (`orders`), and a new result takes the older context's place in that order. A settle caption names what the merge left (`C6 in place of C2 and C3`, `C6 absorbed into C5`); `meta` event `settle`, `algo` line 5.
- **Runtime** (`bbv.js`): the steps of `bbv-merge` glide for 650 ms (`MERGE_GLIDE`, also set as `--lt-glide` on the component). Absorbed contexts are moved first in the drawing, so that they pass under the one they meet; the style is flushed after the move and before the classes change, since a moved element starts no transition (the first attempt made the pair vanish at once). The click and the zoom ignore absorbed contexts, and `part()` no longer matches them.
- **CSS**: `mk-absorbed` keeps the merge border and fades out after the glide (`opacity` transition delayed by `--lt-glide`); `mk-arrive` fades the new result in after the glide (a CSS animation, on animated steps only); the others use `mk-dim` (opacity 0.3).
- **`distance_magnitude`** (default `false`, Olivier's request the same day): every distance shown (edge labels, the pick caption, which reads `log₁₀ distance 6.48`, and the panel) is its log10 with two decimals (`-∞` for 0); merges and widths keep the raw distance. With `random` it is an error, like the other distance options.
- **Docs**: spec 8.8, 9.5 (frames, placement, parts, edges) and 15; README, manual slide text, `docs/USER_SKILL.md`, `docs/SKILL.md` (tests, the pitfall of moving elements), design report (decision 43), todo.
- **Verified**: `pytest -rs` 441 passed, 1 skipped (Firefox not installed; 4 new tests); frames checked for both placements (meeting points, the others in place, settle in the layout), Chromium screenshots during the glide of a new result and of an absorbed context, and at rest.
