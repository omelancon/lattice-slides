# Lattice: todo

This todo list is intended for Olivier to pick future directions, not for immediate implementation.

Updated 2026-10-02, after the 0.11.0 implementation (`implementation-report-2026-10-02.md`, sections 9 to 12). The items left open by the versioning and abstract interpretation phases (`archive/todo.md`) are carried over below; everything done in those phases stays recorded there.

## Waiting on Olivier

- [ ] 0.6.0: a look at the arrow and at the Keybindings grid of the presenter view in Firefox (only Chromium was available in the session; the geometry uses `getBoundingClientRect`, `Range.getBoundingClientRect` and `getBBox`, which both engines support).
- [ ] 0.6.0: try the detour step of example 01 (`at=1` on the invariant detour of "Nothing here is linear") and the skip keys on a long animation (example 06 or 07) to judge the playback interval (30 to 90 ms per step, `playSteps` in `lattice.js`).
- [ ] 0.7: a look at the rich captions, the aligned contexts and the chips of example 07 on your screen (checked in Chromium and Firefox at 1280x720; fonts fall back on the build machine), and at the dark theme, whose `--lt-type` and `--lt-range` tokens were chosen without a monitor.
- [ ] 0.7: `one-block-steps` keeps `height=460`: now that a narrow column honours the height, the drawing sits in the middle of its canvas with room above and below; lower the height if you prefer the caption closer to the drawing.
- [ ] 0.5: review of the two abstract interpretation slides (contexts show every live variable, including `n`; see the archived report addendum).

- [ ] 0.7.2: read the user manual (`user_manual/manual.html`) once as a user would; wording and chapter order are open to change, and every slide was sized at 1280x720 in Chromium.
- [ ] 0.8.0: try the slide "Badges that wait for their turn" of the manual. A hidden badge keeps its place, like a fragment, so with two `badge=next` detours the second badge appears one row below where the first one was; say if you would rather have waiting badges take no space (then the slide's layout would shift as they come and go).
- [ ] 0.9.0: try placed badges (`::detour-badge`) on your two-column slide; the manual's new slide "Badges where you want them" places one live badge per column. (Since 0.11.0, ids on badges and other blocks are checked for duplicates on a slide, LT058.)
- [ ] 0.11.0: replace the `<span class="tail">` of `src/background.md` with `from_anchor: left`, and the `:nth-child` targets with segments in `programs/sum-to-n.scm`. A bullet still has no id of its own, so `from` names it with a selector (`li:nth-child(2)`) or an id on a span; on a two-line bullet `left` is the middle of the whole item, not of its first line.
- [ ] 0.11.0: the length of the handles of an anchored end (0.45 of the distance, between 40 and 260 slide pixels, `curveOf` in `arrow.js`) was tuned on two slides; say if the curves bulge too much or too little.

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
- [ ] `archive/reading-notes.md` still cites the older `docs/this_phase/` paths of the thesis and the Gambit sources; harmless in an archive, fix if the files are ever moved.

Basic block versioning and abstract interpretation (from `archive/todo.md`, plus 0.7):
- [ ] A `code` panel key: the version of the current frame with its specialized code (removed tests struck through) listed in the panel, for slides that draw `show: [label, context]` (discussed on 2026-10-02, not needed yet since `show` covers it).
- [ ] Importer for the Gambit `--plot` state stream (`.plot.html`).
- [ ] Scheme front end producing `.bbv` programs.
- [ ] Jump cascade removal in the `done` frame.
- [ ] Other traversal orders; the blog's backward-score heuristic.
- [ ] Nicer edge routing when a wrapped rank puts a target on a second line (edges cross the first line).
- [ ] Abstract interpretation: interprocedural calls (calls are opaque), boolean blindness, a `hide` option to drop variables such as `n` from the drawn contexts.

## Notes for whoever picks this up

- `check_docs.py` enforces version agreement across README, spec, report, `__init__.py` and `pyproject.toml`; the highest diagnostic code is LT058.
- Release step 4 of SKILL.md (removing `.lattice-cache/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`) is for Olivier's working tree.
