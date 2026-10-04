# Lattice: todo

This todo list is intended for Olivier to pick future directions, not for immediate implementation.

Updated 2026-10-04, after 0.13.0 (`implementation-report-2026-10-04.md`). Items are tagged with the version that raised them. The items left open by the versioning and abstract interpretation phases (`archive/todo.md`) are carried over below; plans larger than an item are in the roadmap (`design-report.md`, section 6).

## Waiting on Olivier

- [ ] 0.5: review of the two abstract interpretation slides of example 07 (contexts show every live variable, including `n`; see the 0.5.0 addendum of `archive/implementation-report.md`).
- [ ] 0.6.0: a look at the arrow and at the Keybindings grid of the presenter view in Firefox (only Chromium was available in the session; the geometry uses `getBoundingClientRect`, `Range.getBoundingClientRect` and `getBBox`, which both engines support).
- [ ] 0.6.0: try the detour step of example 01 (`at=1` on the invariant detour of "Nothing here is linear") and the skip keys on a long animation (example 06 or 07) to judge the playback interval (30 to 90 ms per step, `playSteps` in `lattice.js`).
- [ ] 0.7: a look at the rich captions, the aligned contexts and the chips of example 07 on your screen (checked in Chromium and Firefox at 1280x720; fonts fall back on the build machine), and at the dark theme, whose `--lt-type` and `--lt-range` tokens were chosen without a monitor.
- [ ] 0.7: `one-block-steps` keeps `height=460`: now that a narrow column honours the height, the drawing sits in the middle of its canvas with room above and below; lower the height if you prefer the caption closer to the drawing.
- [ ] 0.7.2: read the user manual (`user_manual/manual.html`) once as a user would; wording and chapter order are open to change, and every slide was sized at 1280x720 in Chromium.
- [ ] 0.8.0: try the slide "Badges that wait for their turn" of the manual. A hidden badge keeps its place, like a fragment, so with two `badge=next` detours the second badge appears one row below where the first one was; say if you would rather have waiting badges take no space (then the slide's layout would shift as they come and go).
- [ ] 0.9.0: try placed badges (`::detour-badge`) on your two-column slide; the manual's slide "Badges where you want them" places one live badge per column.
- [ ] 0.11.0: replace the `<span class="tail">` of `src/background.md` with `from_anchor: left`, and the `:nth-child` targets with segments in `programs/sum-to-n.scm`. A bullet still has no id of its own, so `from` names it with a selector (`li:nth-child(2)`) or an id on a span; on a two-line bullet `left` is the middle of the whole item, not of its first line.
- [ ] 0.11.0: the length of the handles of an anchored end (0.45 of the distance, between 40 and 260 slide pixels, `curveOf` in `arrow.js`) was tuned on two slides; say if the curves bulge too much or too little.
- [ ] 0.12.0: watch the bug-fix slide of example 05 and the manual's "Code that changes" and "Morphing named segments" on your screen, in Chromium and in Firefox (only Chromium was available here; the morph uses `ch` units, `overflow: clip`, CSS transitions of `transform` driven by custom properties, and `round()` inside `@supports`). Fonts fell back to DejaVu Sans Mono on the build machine.
- [ ] 0.12.0: judge the timing: 600 ms per step, leaving tokens fade during the first 40 %, survivors glide from 20 to 80 %, arrivals fade in during the last 40 %; skip playback uses one 140 ms glide. Say if the phases should overlap less, or the default be shorter.
- [ ] 0.12.0: try `code-morph` on one of your own bug fixes. The alignment keeps the longest common runs of tokens, so when two runs cross only one survives (in example 05, `del self.items[` fades out and back in while `self.order.pop(0)` glides); say whether that reads well or needs a smarter pairing.
- [ ] 0.12.0: `mark=true` tints arriving tokens with `--lt-add-bg` for 1.6 s; it is off by default, as you asked. Look at it once in the manual ("Morphing named segments").
- [ ] 0.12.1: the manual's "Extending Lattice: a plugin file" now shows each highlighted range (steps 1 and 2 used to show dimmed code only); look at it once, and at a PDF of a deck of yours with a long `code-steps`.
- [ ] 0.13.0: with `intervals` off (the default), constants bound through `goto B(i=0)` and call arguments still enter the target context with their singleton (`b: fx {0}` in the operator entries of example 07's `fact`), while every other interval is stripped. Fixing it is one `without_range()` in `Goto` (`sbbv.py`) and in `specialize_call` (`lv.py`); it was left as is so that example 07 stays byte-identical. Say if you prefer the fix.
- [ ] 0.13.0: the two `findv` slides of example 07 and the manual's "Intervals and vector lengths" were sized in Chromium at 1280x720; the `⟦x⟧` brackets come from the fallback font of the build machine, check them on yours (an ASCII `|x|` is a one-line change in `intervals.py` if they look wrong). The `findv` drawing is dense (24 versions of five context lines); `show: [label]` with the tooltips is the alternative.
- [ ] 0.13.0: `checks` now counts every `if` left (the loop test, `if #res` and the overflow tests included), as agreed; the captions say "tests left". Say if you want the type tests counted apart.

## Later, if wanted

Authoring and parsing:
- [ ] A `:::` line quoted inside a fenced block closes an enclosing `:::` container (SKILL.md, Pitfalls); the container rule of `markdown.py` could skip fenced blocks when it looks for its closing marker.
- [ ] A `{.reveal}` line before a `::: detour` container is still ignored without a word (the badge is not a fragment). Either make the badge a fragment of the reveal track (a step-table change) or warn; `badge=step` covers the case that motivated it.

Navigation and presenter view:
- [ ] Arrow labels: a `label_at` option (tail, middle, head). A label beside the middle of a `from` arrow can overlap text when the two boxes are close; `curve` moves it for now. A tail label near the slide edge is pushed back inside and then sits over its own line, which shows through the spaces of the label.
- [ ] Ids on list items and inline spans (`[text]{#id}`, the attrs plugin of mdit-py-plugins), so that an arrow can leave a bullet without a selector.
- [ ] The manual's samples of `arrow` blocks ("Arrows that move", "Arrow anchors") show red error boxes: Pygments has an `arrow` lexer, which the Markdown lexer uses inside the sample fence.
- [ ] Segments in `bbv-cfg` and `bbv-anim` drawings (a block or an instruction as an arrow target).
- [ ] Detour steps inside a tour: a detour step enters its detour as anywhere else and the tour successor applies only at the last step; decide whether a tour should be able to turn detour steps off.

Output:
- [ ] matplotlib plots get random SVG ids at every build (`clip-path="url(#p...)"`), so rebuilding an unchanged deck changes its HTML (seen in examples 02 and 03 during the 0.12 cleanup). Setting matplotlib's `svg.hashsalt` in the plot component would make rebuilds byte-identical (report section 2, goal 6).

Code (0.12):
- [ ] Highlights per position in a `code-morph` (a `steps:`-like list of lines or segments per version); today a `code` follower of a morph highlights nothing.
- [ ] `diff-steps` could honour the per-version `lang` that `code-morph` reads (it ignores the key, as before).
- [ ] Characters wider than one column (LT060): count East Asian wide characters as two columns instead of warning, if a deck ever needs them.
- [ ] Character-level alignment of identifiers (`xs` to `xs2`): whole tokens are replaced today, by design.
- [ ] A hash change to an adjacent step of the same slide is treated as a step and animates (the host's `hashchange` handler); harmless, but the spec says jumps do not animate.

Basic block versioning and abstract interpretation (from `archive/todo.md`, plus 0.7; the Gambit importer, a Scheme front end, jump cascade removal and other traversal orders are on the roadmap):
- [ ] A `code` panel key: the version of the current frame with its specialized code (removed tests struck through) listed in the panel, for slides that draw `show: [label, context]` (discussed on 2026-10-02, not needed yet since `show` covers it).
- [ ] The blog's backward-score heuristic, as another `heuristic` value.
- [ ] Nicer edge routing when a wrapped rank puts a target on a second line (edges cross the first line).
- [ ] Abstract interpretation: interprocedural calls (calls are opaque), boolean blindness, a `hide` option to drop variables such as `n` from the drawn contexts.
- [ ] Vectors (0.13): `make-vector(n, x)` could give its result the symbol of a fresh class with `n` as its length (today the length is unknown); two bounds per side (a numeric and a symbolic one) would keep `fx+?(i, 2)` decidable at the price of a longer widening chain; a symbolic bound in a lower position is dropped under addition by design (the paper's rule).
- [ ] Vectors (0.13): the merge heuristics only break ties with intervals (a fraction added to the Hamming distance); the thesis's `similarity` (appendix A.2) weighs interval widths in its specificity term, which would change tie-breaks of existing decks.

## Notes for whoever picks this up

- Release step 5 of SKILL.md (removing `.lattice-cache/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`) is for Olivier's working tree.
