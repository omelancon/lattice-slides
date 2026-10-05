---
name: lattice-development
description: Onboarding and working rules for the Lattice codebase, a Python library that compiles Markdown into non-linear HTML slide decks for computer science talks (slide graph with detours, branches and links; animated graph, array, tree and grid traces; basic block versioning and abstract interpretation animations; code stepping and morphing; plots; presenter view; PDF export). Use this skill before any work in the Lattice repository, even small edits, including changing the parser, graph resolution, components, the JavaScript runtime, themes, examples, tests or documentation, adding a component or diagnostic, fixing a rendering bug, preparing a release, or answering questions about how Lattice works internally.
---

# Working on Lattice

Lattice turns Markdown into one self-contained HTML deck whose slides form a graph. Python does all heavy work at build time (parsing, layout, plots, algorithm traces); the browser only replays precomputed states. Keep that split in mind: almost every design decision follows from it.

This file is for contributors. It explains where things live, how to verify changes, and how to keep the documentation coherent. It deliberately does not repeat the authoring syntax or the contracts; it points to the document that owns each topic.

## Documentation map (read the owner, do not copy it)

| Document | Owns | Read it when |
|---|---|---|
| `README.md` | User-facing usage: install, CLI, syntax cheat sheet, keys, examples list, release status | You need to know what users see, or you changed anything user-visible |
| `docs/spec.md` | The normative definition: grammar (section 3), Deck model (4), graph resolution (5), steps, timelines and detour steps (6), navigation state machine (7), Python component contract (8, the `arrow` component in 8.9, code segments in 8.10, `code-morph` in 8.11), frames (9), JS runtime contract (10), output format (11), diagnostics (12), changes since draft 1 (15) | Before changing behavior. The spec wins over every other document |
| `docs/design-report.md` | Why: goals and non-goals, design rationale (section 3), technology choices (5), the roadmap (6) and the decisions table (7) | You are about to make a design choice, or want to know what is planned |
| `docs/SKILL.md` (this file) | How to work on the code: structure, setup, verification, pitfalls, release and documentation upkeep | Always, first |
| `user_manual/manual.md` | The user manual, a Lattice deck: every feature shown live, with its syntax, options and keys | You changed anything user-visible: the manual must show it (built like the examples, checked by the suite) |
| `docs/todo.md` | What waits on Olivier (things to look at or decide) and small items left for later; larger plans belong to the roadmap | You finish a task (add what is left open) or look for something to do |
| `docs/implementation-report-*.md` | The record of the latest release: what was built, decided and verified, and what was not | You need the history of a recent change; write a new one for each release (see the last section) |
| `docs/archive/` | Earlier plans, reading notes and implementation reports, kept as written (its `README.md` lists them) | You need the history behind an older feature; do not update these files |

## Setup

```bash
pip install -e ".[dev]"          # core + pytest, matplotlib, playwright
playwright install chromium      # browser tests, screenshots and PDF export
playwright install firefox       # optional: layout checks of the versioning drawings (see Pitfalls)
dot -V                           # Graphviz CLI; needed for dot diagrams, .dot graphs and the overview map
pytest                           # the full suite, including browser tests; must pass before and after your change
python scripts/build_examples.py # rebuilds examples/*/talk.html and user_manual/manual.html
```

Python 3.10 or newer. Without Graphviz, animated graphs fall back to a NetworkX layout and the overview map is empty; without Chromium the browser tests and the PDF export test skip, so a green run without Chromium proves less than it seems. Playwright looks for the Chromium build of its own version: where a Chromium is preinstalled (a sandbox, a CI image), install the Playwright release that matches it, or the browser tests skip silently. Check that `pytest -rs` reports no skips.

## Project structure

```
src/lattice/
  cli.py          commands: new, build (--dir), check, serve, graph, pdf
  build.py        pipeline orchestration and plugin loading
  markdown.py     markdown-it setup: containers (fences counted, code blocks skipped, `::: /NAME`), leaf
                  directives (::include, ::detour-badge), [[links]], $math$
  parser.py       Loader: files, includes, h1 segmentation, detours, ids, slide attributes
  attrs.py, ids.py  attribute blocks and slug ids
  body.py         BodyBuilder: blocks, reveal, containers, detour badges (default and placed), branch
                  menus, notes, timelines, component placeholders
  graph.py        next resolution, edges, keys, main path, reachability, tours
  timeline.py     timeline parsing, step compilation (ranges resolved against the current positions), detour
                  steps (and LT055 for badges tied to them)
  render.py       component rendering, cache, tracks
  emit.py         deck JSON, single-file HTML, directory output, image embedding
  graphs.py       graph loading, Graphviz layouts, overview map layout, tree layouts per frame
  anim.py         Trace, GraphTrace, ArrayTrace, TreeTrace, GridTrace, deltas, frame stores
  bbv/            basic block versioning and abstract interpretation: types.py (lattice, contexts, symbol
                  remapping), intervals.py (widening, symbolic bounds), prims.py, ir.py (programs, .bbv syntax, liveness), sbbv.py,
                  lv.py, absint.py, heuristics.py, trace.py (events to frames and captions), rich.py (the caption
                  markup), layout.py (block bands), pseudocode/ (the thesis algorithms, for code following)
  pdf.py          PDF export: pdf step selection, the page plan (tour and appendix), driving Chromium
  model.py        dataclasses and pydantic front matter
  diagnostics.py  Diagnostic, BuildError
  themes.py       theme table: CSS file, Pygments style, palette for components
  server.py       dev server: polling watcher and server-sent events for reload
  components/     base.py (contract, registry, RenderContext), code.py, segments.py (segment markers in code),
                  morph.py (code-morph: units, alignment, segment replacement), scheme.py (the Scheme highlighting
                  filter), visual.py (plot, dot, math, arrow), animations.py, bbv.py
  runtime/
    lattice.js    navigation state machine (with the structural predecessor, skip playback and detour
                  steps), reveal and badge visibility per step, overlays, enlarged elements (the zoom
                  card, its input rules and sync), presenter view (preview, scrubber, keybindings),
                  print mode, component host
    lattice.css   layout and component styles; themes/*.css hold custom properties only
    components/   one runtime per animated or interactive component (arrow.js measures element boxes and list markers;
                  code-morph.js places units on a grid and moves them with CSS transitions)
    vendor/       KaTeX, Vega, Vega-Lite, Plotly (with licenses), embedded only when used
tests/            pytest suites (see Verification)
examples/         seven decks with their built talk.html; they double as integration tests
user_manual/      the user manual deck (manual.md, manual.html) with its demo sources and plugin
scripts/          build_examples.py, snapshot.py (drive a deck in Chromium, take screenshots),
                  check_docs.py (mechanical documentation checks)
docs/             this file, the spec, the design report, the todo list, the latest implementation report;
                  archive/ holds earlier plans, notes and reports
```

The build pipeline, in order: `Loader.load` (files, includes, slides, detours, ids) then `BodyBuilder.build` per slide, then `resolve_graph`, then `render_components` (which also compiles steps), then `check_steps` (LT053), then wiki-link title substitution, then `emit_html` or `emit_dir`. `lattice pdf` then opens the single-file output in Chromium with `?print` and prints the pages of `pdf_plan`. Errors stop the build between phases (`diags.raise_if_errors()`), so structural errors never trigger component execution.

## Invariants worth protecting

Each of these was decided deliberately; the reasoning is in the report (sections 3 and 7) or the spec. Breaking one usually breaks several features at once.

- **Build time does the work, the browser replays.** Components produce data; runtimes render it. Do not add computation to the runtime that could run in Python. The one exception is `arrow.js`, which measures element boxes because they exist only in the browser; even its default direction is a fixed angle, not a computed one (report, decision 14).
- **Positions are absolute.** `show(inst, position, info)` must render any position in any order (spec 10.2). Backward navigation, the presenter scrubber and preview, PDF export, reloads and timelines all depend on it. This is also why a detour step (spec 6.4) is entered only when NEXT arrives on it: reaching the same position any other way has no side effect. This is also why frame stores hold full states (spec 9.3). Motion between positions (tree nodes gliding) is an effect of `info.animate` only, never state.
- **Passive windows stay passive.** The preview pane and print mode (`?preview`, `?print`) must not read keys, save to `sessionStorage`, update the hash, broadcast or open an enlarged element; otherwise they would steer the presenter's deck.
- **Navigation is the history model** (spec 7.2): Left undoes the last move, Up returns from the latest excursion. With an empty history Left walks the structure backward without recording anything, and skip moves never touch history either. Any change to `actions` in `lattice.js` must keep `tests/test_runtime.py`, which encodes the worked trace of spec 7.3, green.
- **Ids are global** across files, detours are nested only, and `#` is the only slide boundary (report section 7, decisions 1 to 3).
- **Registered components take precedence over Pygments lexers** (spec 3.13). Never register a component under a common language name; that is why the diff component is `diff-steps`.
- **Output is self-contained.** Images, fonts, data and libraries are embedded in single-file mode. Heavy libraries are embedded only when an instance requires them (`RenderResult.requires`).
- **Columns contain their content.** Nothing may paint outside its column or below the slide body; `tests/test_layout.py` checks every example slide at its first and last step. A component option such as `height` must be honoured in every layout mode (the animation panels switch to a column under 760 px of container width).
- **Diagnostics have stable codes.** Codes are never reused or renumbered; the current highest is LT063. New code, new row in spec section 12.

## Common tasks

**Add a built-in component.** Write the class in `components/` (spec 8.2), register it in `components/__init__.py`, add a runtime in `runtime/components/` if it has positions or interactivity (spec 10), add styles to `lattice.css` using theme custom properties, add a row to spec 8.8 and to the README components table, add a test, and use it in an example so the layout test covers it.

**Add a diagnostic.** Emit it through `diags.error` or `diags.warn` with a new code (a component's warning through `ctx.warn(msg, code)`, so that a cached build reports it again), add the row to spec section 12, and add a test asserting the code appears.

**Change the syntax or semantics.** Change the spec section that owns the rule first, then the code, then the README summary if users see it. Add a row to the changelog table of spec section 15 pointing to that section.

**Add a theme property.** Define it in every file of `runtime/themes/`, and if Python components need it (plots), in the palette of `themes.py`.

**Change the runtime.** `lattice.js` is one module with no build step. It is concatenated with component runtimes into the page; it must also work as a deferred classic script (directory output).

## Verification

Run `pytest` after every change; it takes about a minute and a half, most of it in Chromium. The suites:

| File | Covers |
|---|---|
| `test_parsing.py` | attributes, ids, includes, links, reveal and `.reveal-with`, containers and their fences (bare and named closing fences, mixed, code blocks skipped, LT061, LT062), leaf directives |
| `test_graph.py` | next resolution, detours, branches, keys, tours |
| `test_steps.py` | tracks, timelines (open ranges `..STOP`, `end-N`, strides, lockstep ranges and their errors), detour steps and the badges of their detours (modes, placed badges, LT055 and LT056), followers, deltas, frame stores, tree and grid traces, tree layouts |
| `test_bbv.py` | the type lattice and intervals, the `.bbv` syntax, SBBV and ΛV against the thesis figures (6, 14, 16), abstract interpretation against figures 1, 2 and 4, intervals in SBBV and ΛV, the symbolic bound rules of the paper and `findv` against its figure 7, frames, layout, the components (`clickable`, `clickable_show` and the sizes of enlarged blocks) |
| `test_output.py` | plot backends, diff-steps, the arrow component, images, directory output, overview map, library inclusion |
| `test_segments.py` | code segment markers (both forms, spaces, line numbers, errors), wrapping of Pygments output, segment highlights, LT058, arrow anchor options, arrows at list items and bullets (the item path, LT063) |
| `test_morph.py` | `code-morph` at build time: units and alignment (every version rebuilt from the data, survivors across lines, moves, tabs, a language change), the steps form (cumulative replacements, indentation, removed lines, nesting errors), options, LT059, LT060, the cache |
| `test_pdf.py` | `pdf` steps and LT053, the page plan (tour, appendix, back links), a real export in Chromium |
| `test_cli.py` | CLI commands, building every example, the user manual building without warnings and using every component |
| `test_runtime.py` | the navigation state machine (the spec 7.3 trace, backward walking without history, skip keys, detour steps, badges that wait for their detour step, placed in columns), the presenter preview, scrubber and keybindings, the arrow geometry (anchors, segments as targets, bullets checked against the pixels of their markers, items without their nested lists), the tree, grid, versioning and abstract interpretation runtimes, enlarged blocks (keys and clicks that close without moving, the current step shown, `clickable=off`, passive windows, the presenter pane and sync), `code-morph` (the same geometry however a position is reached: fresh load, jumps, animated, interrupted and skipped steps, preview, print; an arrow following a segment), in Chromium |
| `test_layout.py` | no content spills out of a column or below the slide body, at the first and last step of every slide of the examples and the manual |

Tests prove structure, not appearance. After any visual change (CSS, runtime rendering, a component's HTML, an example), rebuild the examples and look at screenshots of the affected slides:

```bash
python scripts/build_examples.py
python scripts/snapshot.py examples/04-custom-components/talk.html /tmp/shots "ArrowRight*4" --shots=4
```

Take the screenshot after the last edit, not before it. A column overlap once shipped because a stylesheet was changed after the slide had been checked. `snapshot.py --presenter` shows the presenter view. For print changes, export a deck (`lattice pdf examples/02-shortest-paths/talk.md -o /tmp/t.pdf --tour short`) and look at its pages, for example after `pdftoppm -png`.

## Pitfalls

- **Stale renders.** The cache key includes a hash of the Lattice sources, so library changes invalidate it; `--no-cache` or deleting `.lattice-cache/` forces a clean render when you doubt it.
- **Container fences are counted, not compared.** `_container_rule` in `markdown.py` replaces mdit-py-plugins' container plugin: a bare closing fence closes the innermost container whatever its colons, and the end of a container is found by counting the fences after it while skipping code blocks (`_code_fence` also looks behind list and quote markers). The loader reports the problems the rule records in `env["fence_problems"]` (LT061, LT062), so a new caller of `md.parse` on deck sources must report them too. The examples and most of the manual still use decreasing counts, which parse the same; keep both styles working.
- **Attribute values are strings.** Lists and mappings go in the YAML body of a block, not in `{...}`. Extra options of animation components are read as YAML scalars (spec 8.2).
- **DOT keywords.** `graph`, `node`, `edge`, `digraph`, `subgraph` and `strict` cannot be bare node names in `dot` blocks.
- **Line-based references.** `code-steps` steps, `lines=` ranges and `meta["line"]` in traces point at line numbers. Editing a referenced file (for example `examples/04-custom-components/lattice_plugins.py`) can silently shift highlights; recheck those slides, or name the code with segment markers (spec 8.10), which move with the code.
- **Segment markers are read everywhere.** A comment holding only `@word` (`/*@param*/`, or a line `// @ts-ignore`) is a segment marker; an unclosed one fails the build with LT022. `markers=false` on the block shows such text as written; the manual uses it to display the syntax.
- **Code HTML is wrapped, not re-rendered.** `segments.wrap_line` relies on Pygments' `nowrap` output being a flat run of `<span class="X">` and text per line; a line of another shape is left without its segments. Code without markers must render byte for byte as before.
- **Counting key presses** in `snapshot.py`: a slide with `n` steps needs `n` presses to leave it (steps 1 to `n-1`, then the move).
- **Step numbers differ by audience.** The URL hash and the `pdf` attribute count steps from 0; the HUD and the presenter view show them from 1.
- **Element ids in component HTML** are duplicated in the PDF (one copy per page). Print mode renames ids and `url(#...)` or `href="#..."` references inside each copy; a component that refers to its ids another way (for example from CSS) breaks in print.
- **Versioning programs.** `tests/test_bbv.py` pins properties of the thesis figures (which versions exist, which tests disappear, how many return points), not exact drawings: the thesis took liberties with types and heuristics to keep its figures short, so the algorithm's real output differs in details. When changing `sbbv.py` or `lv.py`, rerun the example and look at the captions; a wrong cascade shows up as return points that flicker between frames.
- **Intervals are off by default in SBBV and ΛV.** `Specializer.type_of` strips them unless `intervals` is on, so a change to `prims.py` result rules must keep working without intervals; constants bound through `goto` and call arguments do keep their singleton (example 07 shows `b: fx {0}`), a known leak kept for the examples. With intervals on, every assignment goes through `result_of` (which passes the argument names for `vector-length` and applies `refined`), and `merge_contexts` widens the older version against the newer: a loop that does not converge is a merge that joined without widening.
- **A symbolic bound names a class representative.** `⟦x⟧` in a range is the representative of the class holding the vector, in that very context. Every `Context` operation that changes classes or names (`set`, `equate`, `restrict`, `rename`, `union`, `intersection`, and ΛV's `return_context` across a call) must end with `_remap`, or symbols point at variables that no longer exist; `test_symbols_follow_the_class_of_their_vector` pins the cases. The fixnum width of symbols comes from `intervals.fixnum_bits()`, set by `using_fixnum_bits` around a run: code outside a run sees the default (61).
- **The drawing of `bbv.js` must never rescale between frames.** Its SVG keeps its aspect ratio, so anything that changes the canvas size (a panel growing with the queue, a caption wrapping to a second line) rescales the whole drawing. The panel has a fixed width, `.lt-ga-main` does not shrink, and the caption shrinks its text to fit the space left (`fitCaption`). Check both Chromium and Firefox after touching that layout; Firefox resolves these flex sizes differently.
- **Node elements are reused across frames.** `bbv.js` rewrites the class attribute of a node at every frame, including when it hides it; anything the node must keep (its origin colour) lives in the node record, never in the current classes. A colour that survives forward playback and vanishes after stepping back is this bug.
- **Captions are marked up, not HTML.** The versioning and abstract interpretation captions carry the backtick spans of `bbv/rich.py` (spec 9.5); tests compare them through `rich.plain` or on the markup itself, and a note written in `sbbv.py`, `lv.py` or `absint.py` uses the helpers rather than f-strings of raw names and types.
- **Arrow targets are measured, not styled.** `arrow.js` reads `getBoundingClientRect` of the target's contents and draws in slide units; a change to `.lt-slide` positioning or to how the viewport is scaled (`fit`) must keep `test_arrow_runtime_points_at_its_targets` green. The classes of its SVG are `lt-arrow-box`, `lt-arrow-line` and `lt-arrow-text`: `.lt-arrow` already belongs to the graph animation's arrowheads.
- **Morph units are placed, not laid out.** A `code-morph` unit sits at `--c` columns (`ch`) and `--r` rows (`1.5em`, the line height of `.lt-code pre`) from the origin of the text; a change to the font, the line height or the padding of `.lt-code` must be mirrored in the `.lt-morph-*` rules of `lattice.css` (the stage is `content-box`, against the global `border-box`), or the block stops looking like a `code` block at rest. A unit that is hidden keeps its last position; the stage clips (`overflow: clip`) so that it never adds scrolling. Compare a morph and a `code` block of the same text in a screenshot after such a change.
- **Bullets are text markers.** `arrow.js` measures a marker by setting its item's `list-style-position` to `inside` for one measurement: the first character moves by the marker's width, and an outside marker ends where the content starts. That is exact only for text markers, so the built-in bullets are `list-style-type` strings (`•`, `◦`, `▪`, each with an en space) in `lattice.css`, under `:where()` so that theme and plugin rules on lists win. Do not switch back to `disc` or draw markers with `::before` (which would override plugins' own `::before` markers, such as the manual's `checklist`). `test_arrow_at_bullets` compares the arrow's end with the marker's pixels; run it in Firefox too after touching this (`p.firefox`, after `playwright install firefox`).
- **Arrows re-measure on `lt-relayout`.** A runtime that moves content without changing its box dispatches it (spec 10.4); `arrow.js` handles it in a microtask, after every `show` of the step. A new component that moves text an arrow may point at should dispatch it too.
- **An enlarged element is not a position.** The zoom card of spec 7.7 never touches `nav`, the hash or `sessionStorage`, and `render` closes it first thing, so a sync, a hash change or the scrubber cannot leave a stale card over a new step. Its input handlers run before everything else (`onKey` checks it before overlays; a capture-phase `pointerdown` swallows the press, its `mousedown` and its `click`), so a new handler that must act while a card is open has to be placed before them. A component offers elements through its controller's `zoom(inst, key)`, which must build a new element from the position last shown: the same hook serves a local click and the other window's request. In `bbv.js`, `drawNode` and `nodeState` are shared by the drawing and the enlarged copy; a change to what a node shows goes there once, and to `layout.node_size`, which sizes both.
- **Writing style.** The project owner avoids em dashes in prose; use colons, commas or parentheses.

## Release

1. Bump the version in `src/lattice/__init__.py` and `pyproject.toml` (patch for fixes, minor for features), and in the introductions of the README, the spec, the report and the manual (`check_docs.py` enforces it).
2. `pytest`, then `python scripts/build_examples.py`, then check screenshots of anything visual (the manual included).
3. Write the implementation report of the release, a `docs/implementation-report-*.md` named after its date (a patch release adds a section to the report of its minor version; a second minor release on the same date adds `-b` to the name), and update `docs/todo.md` with what is left open.
4. Run the documentation coherence pass below.
5. Remove `.lattice-cache/`, `__pycache__/`, `*.egg-info/` and `.pytest_cache/`.

## Keeping the documentation coherent

Do this after every major task (a feature, a fix that changes behavior, a release), not only when something looks wrong. Documentation drifts one small edit at a time, and each document is read by someone who trusts it.

1. **Reread every document in full:** `README.md`, every file in `docs/` except `docs/archive/`, `user_manual/manual.md`, and any README inside `examples/`. Skimming misses contradictions; they hide in examples and tables.
2. **Check each statement against the code and against its owner** in the documentation map above. The spec owns behavior; the report owns rationale and plans; the README owns user-facing usage; this file owns contributor workflow.
3. **Remove duplication.** When a fact appears in two places, keep it in its owner and replace the other occurrence with a reference (for example "see spec section 7.6"). A user-facing summary in the README is acceptable only if it links to the owning section and adds no facts of its own.
4. **Fix contradictions in place.** Update the text that is wrong rather than appending corrections elsewhere. Spec section 15 is a changelog table that points to the amended sections; it must not hold rules found nowhere else.
5. **Keep statuses aligned.** The version in `src/lattice/__init__.py` and `pyproject.toml`, the version named in the README and at the top of the spec and the report, and the roadmap (report section 6) must agree. The spec does not keep its own list of planned features; section 14 points to the roadmap.
6. **Check references.** Run `python scripts/check_docs.py`. It verifies that cited sections, repository paths, component names, CLI commands and flags exist, that the diagnostic codes in the code match spec section 12, and that versions agree. It cannot judge prose, so it complements steps 1 to 5 and does not replace them.
7. **Archive what is no longer current.** When a new implementation report is written, the previous one moves to `docs/archive/` (`git mv`) once its rules live in the spec, its reasons in the report and its open items in the todo; add it to `docs/archive/README.md`. Archived files are history: do not update them, and do not cite them from the live documents except as history.
8. **Update this file** when the structure, setup, test suites or release steps change.
