# Implementation report: arrows at the parts of a CFG (Lattice 0.26.0, 2026-10-06; patch 0.26.1, section 4)

Pointing an arrow at a block or an edge of a versioning drawing meant a CSS selector into the runtime's SVG (`[data-instance="preface/avg-graph"] .lt-bbv-node[data-vid='4']`, the first `.lt-bbv-edge.k-goto`): an internal version number instead of the block's label, an edge found by its order in the page, and nothing the build could check. An arrow end may now name a part of a component, `COMP.NAME`: `cfg.B`, `cfg.A->L`, `cfg.L->B:false`, resolved and checked at build time. The rules are in spec 8.2 (the `part` hook), 8.9 (parts as arrow ends) and 9.5 (what the versioning drawings name), with 10.4, 12 and 15; the rationale is decision 35 of the design report. The design and Olivier's answers are in the project document `claude/v0.26-design.md`.

## 1. What was built

- **The `part` hook** (`components/base.py`). A component MAY define `part(result, name) -> Part(selector, drawn, warning)`. It reads the render result only, so a cached build resolves names without rendering again, and the cache format is unchanged. `selector` matches the part's elements inside the component's element; `drawn` gives, per position, whether something of the part is drawn (`None`: always); `warning` is reported as LT046. A name that denotes nothing raises `ComponentError`, reported as LT063. `Part` is exported from `lattice`.
- **The arrow** (`components/visual.py`, `render.py`).
  - `Arrow.render` splits `IDENT.REST` into the component id and the name. It cannot resolve it: the component may render later on the slide.
  - `_resolve_parts` in `render.py`, after every component of the slide has rendered: a component id of the slide makes the end a part (its class must have `part`); otherwise an HTML or SVG element name keeps the end a CSS selector (`li.done`); anything else is LT063. The step gets `to_part` (or `from_part`), the selector. A `bullet` anchor on a part is LT063.
  - `_check_part_positions`, after the step table is compiled: an arrow step whose part is drawn at none of the slide steps that show that arrow step is LT046. Absence at some of them is silent.
- **The versioning drawings** (`components/bbv.py`, `_Drawing`), shared by `bbv-cfg`, `abstract-interp-anim` and `bbv-anim`:
  - a node is a block label (in `bbv-anim`, all versions of the block) or, in `bbv-anim`, a version label, optionally `FUNCTION/`; an edge is `X->Y[:kind]`, every drawn edge from a node of `X` to a node of `Y`, `Y` looked up in the function of `X` unless qualified; kinds `goto`, `true`, `false`, `return`, `call`, with `#t` and `#f`;
  - errors name what exists: "no block 'Z'; the blocks are A, L, B, ...", "no edge A->E in this drawing; A goes to B (true), L (false)", "block B has the versions B1, B2", "write f/A or g/A", "has edges of several kinds (false, true): write ...";
  - a name that is a block and a version label of another block names the block, with LT046;
  - frames are decoded from the frame store, full or keyframed (`anim.frames_of`), and each frame's drawn nodes and edges are those `bbv.js` draws (`call` edges only with `call_edges`). A fixed CFG reports `drawn=None`.
- **Runtime.**
  - `bbv.js`: edge groups carry `data-key` and an invisible `<rect class="lt-bbv-edge-mark">` at the middle of the curve (on a back edge, the middle of its lane), sized from the label's length in the 12 px code font so that it covers `#t`, `#f` or `[1]`, and a point when the edge has no label. After each `show`, the drawing dispatches `lt-relayout`: `{animate: true, follow: 380}` when nodes glide, `{animate}` otherwise.
  - `arrow.js`: an end with a part looks up the component element by its instance, unites the `getBoundingClientRect` boxes of what the selector matches, and shows no arrow, without a console warning, when nothing matches.
  - `lattice.css`: the mark is invisible and takes no pointer events.
- **Docs**:
  - spec 8.2, 8.8 (the arrow row), 8.9, 9.5 (a paragraph "Parts"), 10.4, 12 (LT063 extended) and a 0.26 row in 15;
  - README (the arrow row), `docs/USER_SKILL.md` (feature map rows, a "Rules that bite" line), SKILL.md (structure, tests table, a pitfall on the markup contract);
  - design report (a rationale paragraph in the arrow section, roadmap v0.26 and two follow-ups under "Later", decision 35), todo;
  - manual: a new slide "Arrows at a CFG" (`bbv-arrows`), an arrow walking through a block, a branch edge, the back edge and a return edge of `find`;
  - the 0.25.0 report copied to `docs/archive/` and listed in its README; version 0.26.0.

## 2. Decisions taken with Olivier (design document, section 11)

Both phases in one release; `COMP.NAME` with `->`, `:kind` and `fn/`; LT063 extended rather than a new code; an edge is pointed at its middle; a generic hook rather than code specific to the versioning drawings; a block of `bbv-anim` is the union of its drawn versions; a part absent at some steps is hidden silently, LT046 only for a step that can never show it; a block wins over an equal version label, with LT046; `#t` and `#f` accepted; a manual slide as the demo.

One refinement during the work: the design said a head that is an element name stays a selector. A component id that is also an element name (`#code`, `#map`, `#text`) would then never name parts, so the order is: a component id of the slide first, then an element name, then LT063 (spec 8.9).

## 3. Verification

- `pytest -rs`: 327 passed, no skips, in Chromium (307 before). New tests:
  - `test_bbv.py`: blocks and edges of a CFG with every kind, on a fresh and two cached builds; each LT063 case (unknown block, missing edge, wrong kind, unknown component, a kind on a node, a function not drawn, an unknown kind, a component without parts, `bullet` on a part); both ends as parts, `li.done` kept as a selector, a component id that is an element name; functions sharing a block; edges of several kinds; versions of a run (block, version, edge sets, `drawn`); the LT046 of a step never seen; a block winning over a version label; an abstract interpretation.
  - `test_runtime.py`: `test_arrow_at_parts_of_a_cfg` (heads beside a block, a labelled branch, a back edge and a return edge; the mark covers its label or is a point; the same paths on a fresh load of each step, in the preview and in print); `test_arrow_follows_versions_of_a_run` (hidden before its version exists, beside a version halfway through its glide and after it, around both versions of a block). Each ran four times in a row without a failure.
- `test_columns_change_width_however_a_step_is_reached` (0.24.0) failed on the first full run of the session, on the 0.25.0 sources as on these (an arrow 3 px off after a skip playback), and passed on every rerun; its deck has no versioning drawing. Left as is, noted in the todo.
- Every slide of example 07, at steps 0 and 3, is pixel-identical before and after the change of `bbv.js`.
- Screenshots in Chromium of the manual slide at its four steps, of test decks on `bbv-cfg` (blocks, branch, back and return edges), `bbv-anim` (a block's versions, a version appearing at frame 22, edge sets, the back edge) and `abstract-interp-anim`.
- Examples and the manual rebuilt; `check_docs.py` reports no problem; `lattice check --strict` passes on the manual and every example.

## 4. Not verified, and left open

- Only Chromium was available (`getBoundingClientRect` of SVG groups and of a zero-size `rect`).
- The mark of a labelled edge is sized from the label's length, not measured; a wider code font could let a head touch the end of a long `[1] [2]` label.
- `if x goto L else goto L` draws a single `true` edge (`_program_table` gives both successors the kind `true`); found here, not changed.
- Instruction lines as targets (`cfg.B[2]`) and parts of the other animations are follow-ups (roadmap, "Later").
- The manual's sample of an `arrow` block shows the red boxes of Pygments' `arrow` lexer, like the other arrow slides (todo).
- `docs/implementation-report-2026-10-06-d.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.

## 4. Patch 0.26.1: arrows at an unlabelled edge in Firefox

Found on the defense deck (`src/preface.md`, the step "jump" of `cfg-parts`, `to: avg-graph.A->L`): in Firefox the arrow at an unlabelled edge was drawn at the top left of the slide, while Chromium placed it beside the edge. The arrows at blocks and at labelled edges were right in both browsers.

- **Cause.** The mark of an unlabelled edge is a `rect` of size 0 (section 1). Firefox gives an SVG element without area an empty box at the origin, from `getBoundingClientRect` and from `getBBox` alike; Chromium reports the rect's position. `partBox` in `arrow.js` united those boxes, so the head aimed at the origin.
- **Fix** (`arrow.js`, `clientBox`). The box of an element of a part is its `getBoundingClientRect`, unless it is an SVG element without area: then it is the point of its own coordinates (a rect's `x` and `y`; `getBBox` for another element) mapped to the page by `getScreenCTM`. Boxes with an area are measured as before, so blocks, labelled edges, code, list items and bullets are unchanged; in Chromium the mark of an unlabelled edge gives the same point as before.
- **Test.** `test_arrow_at_an_unlabelled_edge_in_firefox` (`test_runtime.py`) builds the deck of `test_arrow_at_parts_of_a_cfg` and, in Firefox, checks the head beside the back edge `g.J2->A`, stepped to and loaded at that step, against the mark's position computed from its attributes and CTM (not from the box the browser reports). It fails on the 0.26.0 runtime (the head at y = 127, near the top of the slide) and passes with the fix. It skips, saying why, where Playwright's Firefox is not installed (optional in `docs/SKILL.md`, Setup).
- **Verification.** `pytest -rs`: 328 passed, no skips, with Chromium and Firefox for Playwright installed. The defense deck's three arrows (`avg-graph.B`, `avg-graph.A->L`, `avg-graph.L`) checked in Firefox and Chromium at 1280x720 and 1920x1080, stepped to and loaded by URL. Examples and manual rebuilt; `scripts/check_docs.py` clean.
- **Docs.** Version 0.26.1 (README, spec, design report, manual, this report); SKILL.md (the test in the suites table, a line in the pitfall on parts); todo. No rule changed, so spec section 15 has no row for this patch.
