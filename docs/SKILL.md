---
name: lattice-development
description: Onboarding and working rules for the Lattice codebase, a Python library that compiles Markdown into non-linear HTML slide decks for computer science talks (slide graph with detours, branches and links; animated graph, array, tree and grid traces; basic block versioning and abstract interpretation animations; code stepping; plots; presenter view; PDF export). Use this skill before any work in the Lattice repository, even small edits, including changing the parser, graph resolution, components, the JavaScript runtime, themes, examples, tests or documentation, adding a component or diagnostic, fixing a rendering bug, preparing a release, or answering questions about how Lattice works internally.
---

# Working on Lattice

Lattice turns Markdown into one self-contained HTML deck whose slides form a graph. Python does all heavy work at build time (parsing, layout, plots, algorithm traces); the browser only replays precomputed states. Keep that split in mind: almost every design decision follows from it.

This file is for contributors. It explains where things live, how to verify changes, and how to keep the documentation coherent. It deliberately does not repeat the authoring syntax or the contracts; it points to the document that owns each topic.

## Documentation map (read the owner, do not copy it)

| Document | Owns | Read it when |
|---|---|---|
| `README.md` | User-facing usage: install, CLI, syntax cheat sheet, keys, examples list, release status | You need to know what users see, or you changed anything user-visible |
| `docs/spec.md` | The normative definition: grammar (section 3), Deck model (4), graph resolution (5), steps, timelines and detour steps (6), navigation state machine (7), Python component contract (8, the `arrow` component in 8.9), frames (9), JS runtime contract (10), output format (11), diagnostics (12), changes since draft 1 (15) | Before changing behavior. The spec wins over every other document |
| `docs/design-report.md` | Why: goals and non-goals, design rationale (section 3), technology choices (5), the roadmap (6) and the decisions table (7) | You are about to make a design choice, or want to know what is planned |
| `docs/SKILL.md` (this file) | How to work on the code: structure, setup, verification, pitfalls, release and documentation upkeep | Always, first |

## Setup

```bash
pip install -e ".[dev]"          # core + pytest, matplotlib, playwright
playwright install chromium      # browser tests, screenshots and PDF export
playwright install firefox       # optional: layout checks of the versioning drawings (see Pitfalls)
dot -V                           # Graphviz CLI; needed for dot diagrams, .dot graphs and the overview map
pytest                           # the full suite, including browser tests; must pass before and after your change
python scripts/build_examples.py # rebuilds examples/*/talk.html
```

Python 3.10 or newer. Without Graphviz, animated graphs fall back to a NetworkX layout and the overview map is empty; without Chromium the browser tests and the PDF export test skip, so a green run without Chromium proves less than it seems.

## Project structure

```
src/lattice/
  cli.py          commands: new, build (--dir), check, serve, graph, pdf
  build.py        pipeline orchestration and plugin loading
  markdown.py     markdown-it setup: containers, ::include, [[links]], $math$
  parser.py       Loader: files, includes, h1 segmentation, detours, ids, slide attributes
  attrs.py, ids.py  attribute blocks and slug ids
  body.py         BodyBuilder: blocks, reveal, containers, branch menus, notes, timelines, component placeholders
  graph.py        next resolution, edges, keys, main path, reachability, tours
  timeline.py     timeline parsing, step compilation, detour steps
  render.py       component rendering, cache, tracks
  emit.py         deck JSON, single-file HTML, directory output, image embedding
  graphs.py       graph loading, Graphviz layouts, overview map layout, tree layouts per frame
  anim.py         Trace, GraphTrace, ArrayTrace, TreeTrace, GridTrace, deltas, frame stores
  bbv/            basic block versioning and abstract interpretation: types.py (lattice, contexts),
                  intervals.py (widening), prims.py, ir.py (programs, .bbv syntax, liveness), sbbv.py,
                  lv.py, absint.py, heuristics.py, trace.py (events to frames), layout.py (block bands),
                  pseudocode/ (the thesis algorithms, for code following)
  pdf.py          PDF export: pdf step selection, the page plan (tour and appendix), driving Chromium
  model.py        dataclasses and pydantic front matter
  diagnostics.py  Diagnostic, BuildError
  themes.py       theme table: CSS file, Pygments style, palette for components
  server.py       dev server: polling watcher and server-sent events for reload
  components/     base.py (contract, registry, RenderContext), code.py, visual.py (plot, dot, math, arrow),
                  animations.py, bbv.py
  runtime/
    lattice.js    navigation state machine (with the structural predecessor, skip playback and detour
                  steps), overlays, presenter view (preview, scrubber, keybindings), print mode, component host
    lattice.css   layout and component styles; themes/*.css hold custom properties only
    components/   one runtime per animated or interactive component (arrow.js measures element boxes)
    vendor/       KaTeX, Vega, Vega-Lite, Plotly (with licenses), embedded only when used
tests/            pytest suites (see Verification)
examples/         seven decks with their built talk.html; they double as integration tests
scripts/          build_examples.py, snapshot.py (drive a deck in Chromium, take screenshots),
                  check_docs.py (mechanical documentation checks)
docs/             this file, the spec and the design report
```

The build pipeline, in order: `Loader.load` (files, includes, slides, detours, ids) then `BodyBuilder.build` per slide, then `resolve_graph`, then `render_components` (which also compiles steps), then `check_steps` (LT053), then wiki-link title substitution, then `emit_html` or `emit_dir`. `lattice pdf` then opens the single-file output in Chromium with `?print` and prints the pages of `pdf_plan`. Errors stop the build between phases (`diags.raise_if_errors()`), so structural errors never trigger component execution.

## Invariants worth protecting

Each of these was decided deliberately; the reasoning is in the report (sections 3 and 7) or the spec. Breaking one usually breaks several features at once.

- **Build time does the work, the browser replays.** Components produce data; runtimes render it. Do not add computation to the runtime that could run in Python. The one exception is `arrow.js`, which measures element boxes because they exist only in the browser; even its default direction is a fixed angle, not a computed one (report, decision 14).
- **Positions are absolute.** `show(inst, position, info)` must render any position in any order (spec 10.2). Backward navigation, the presenter scrubber and preview, PDF export, reloads and timelines all depend on it. This is also why a detour step (spec 6.4) is entered only when NEXT arrives on it: reaching the same position any other way has no side effect. This is also why frame stores hold full states (spec 9.3). Motion between positions (tree nodes gliding) is an effect of `info.animate` only, never state.
- **Passive windows stay passive.** The preview pane and print mode (`?preview`, `?print`) must not read keys, save to `sessionStorage`, update the hash or broadcast; otherwise they would steer the presenter's deck.
- **Navigation is the history model** (spec 7.2): Left undoes the last move, Up returns from the latest excursion. With an empty history Left walks the structure backward without recording anything, and skip moves never touch history either. Any change to `actions` in `lattice.js` must keep `tests/test_runtime.py`, which encodes the worked trace of spec 7.3, green.
- **Ids are global** across files, detours are nested only, and `#` is the only slide boundary (report section 7, decisions 1 to 3).
- **Registered components take precedence over Pygments lexers** (spec 3.13). Never register a component under a common language name; that is why the diff component is `diff-steps`.
- **Output is self-contained.** Images, fonts, data and libraries are embedded in single-file mode. Heavy libraries are embedded only when an instance requires them (`RenderResult.requires`).
- **Columns contain their content.** Nothing may paint outside its column; `tests/test_layout.py` checks every example slide.
- **Diagnostics have stable codes.** Codes are never reused or renumbered; the current highest is LT054. New code, new row in spec section 12.

## Common tasks

**Add a built-in component.** Write the class in `components/` (spec 8.2), register it in `components/__init__.py`, add a runtime in `runtime/components/` if it has positions or interactivity (spec 10), add styles to `lattice.css` using theme custom properties, add a row to spec 8.8 and to the README components table, add a test, and use it in an example so the layout test covers it.

**Add a diagnostic.** Emit it through `diags.error` or `diags.warn` with a new code, add the row to spec section 12, and add a test asserting the code appears.

**Change the syntax or semantics.** Change the spec section that owns the rule first, then the code, then the README summary if users see it. Add a row to the changelog table of spec section 15 pointing to that section.

**Add a theme property.** Define it in every file of `runtime/themes/`, and if Python components need it (plots), in the palette of `themes.py`.

**Change the runtime.** `lattice.js` is one module with no build step. It is concatenated with component runtimes into the page; it must also work as a deferred classic script (directory output).

## Verification

Run `pytest` after every change; it takes about twenty seconds. The suites:

| File | Covers |
|---|---|
| `test_parsing.py` | attributes, ids, includes, links, reveal, containers |
| `test_graph.py` | next resolution, detours, branches, keys, tours |
| `test_steps.py` | tracks, timelines, detour steps, followers, deltas, frame stores, tree and grid traces, tree layouts |
| `test_bbv.py` | the type lattice and intervals, the `.bbv` syntax, SBBV and ΛV against the thesis figures (6, 14, 16), abstract interpretation against figures 1, 2 and 4, frames, layout, the components |
| `test_output.py` | plot backends, diff-steps, the arrow component, images, directory output, overview map, library inclusion |
| `test_pdf.py` | `pdf` steps and LT053, the page plan (tour, appendix, back links), a real export in Chromium |
| `test_cli.py` | CLI commands and building every example |
| `test_runtime.py` | the navigation state machine (the spec 7.3 trace, backward walking without history, skip keys, detour steps), the presenter preview, scrubber and keybindings, the arrow geometry, the tree, grid, versioning and abstract interpretation runtimes, in Chromium |
| `test_layout.py` | no content spills out of a column, on every example slide |

Tests prove structure, not appearance. After any visual change (CSS, runtime rendering, a component's HTML, an example), rebuild the examples and look at screenshots of the affected slides:

```bash
python scripts/build_examples.py
python scripts/snapshot.py examples/04-custom-components/talk.html /tmp/shots "ArrowRight*4" --shots=4
```

Take the screenshot after the last edit, not before it. A column overlap once shipped because a stylesheet was changed after the slide had been checked. `snapshot.py --presenter` shows the presenter view. For print changes, export a deck (`lattice pdf examples/02-shortest-paths/talk.md -o /tmp/t.pdf --tour short`) and look at its pages, for example after `pdftoppm -png`.

## Pitfalls

- **Stale renders.** The cache key includes a hash of the Lattice sources, so library changes invalidate it; `--no-cache` or deleting `.lattice-cache/` forces a clean render when you doubt it.
- **Container nesting.** An outer container needs more colons than its children (`::::` around `:::`). With equal counts, the first `:::` closes the outer container and the rest of the file parses oddly.
- **Attribute values are strings.** Lists and mappings go in the YAML body of a block, not in `{...}`. Extra options of animation components are read as YAML scalars (spec 15).
- **DOT keywords.** `graph`, `node`, `edge`, `digraph`, `subgraph` and `strict` cannot be bare node names in `dot` blocks.
- **Line-based references.** `code-steps` steps, `lines=` ranges and `meta["line"]` in traces point at line numbers. Editing a referenced file (for example `examples/04-custom-components/lattice_plugins.py`) can silently shift highlights; recheck those slides.
- **Counting key presses** in `snapshot.py`: a slide with `n` steps needs `n` presses to leave it (steps 1 to `n-1`, then the move).
- **Step numbers differ by audience.** The URL hash and the `pdf` attribute count steps from 0; the HUD and the presenter view show them from 1.
- **Element ids in component HTML** are duplicated in the PDF (one copy per page). Print mode renames ids and `url(#...)` or `href="#..."` references inside each copy; a component that refers to its ids another way (for example from CSS) breaks in print.
- **Versioning programs.** `tests/test_bbv.py` pins properties of the thesis figures (which versions exist, which tests disappear, how many return points), not exact drawings: the thesis took liberties with types and heuristics to keep its figures short, so the algorithm's real output differs in details. When changing `sbbv.py` or `lv.py`, rerun the example and look at the captions; a wrong cascade shows up as return points that flicker between frames.
- **Intervals are only for the abstract interpreter.** `Specializer.type_of` strips them (`intervals = False`), so SBBV and ΛV contexts never carry one; a change to `prims.py` result rules must keep working without intervals.
- **The drawing of `bbv.js` must never rescale between frames.** Its SVG keeps its aspect ratio, so anything that changes the canvas size (a panel growing with the queue, a caption wrapping to a second line) rescales the whole drawing. The panel has a fixed width, `.lt-ga-main` does not shrink, and the caption shrinks its text to fit the space left (`fitCaption`). Check both Chromium and Firefox after touching that layout; Firefox resolves these flex sizes differently.
- **Container nesting again.** A detour holding slides that use `::::` columns needs `:::::` fences (see `examples/07-basic-block-versioning`).
- **Arrow targets are measured, not styled.** `arrow.js` reads `getBoundingClientRect` of the target's contents and draws in slide units; a change to `.lt-slide` positioning or to how the viewport is scaled (`fit`) must keep `test_arrow_runtime_points_at_its_targets` green. The classes of its SVG are `lt-arrow-box`, `lt-arrow-line` and `lt-arrow-text`: `.lt-arrow` already belongs to the graph animation's arrowheads.
- **Writing style.** The project owner avoids em dashes in prose; use colons, commas or parentheses.

## Release

1. Bump the version in `src/lattice/__init__.py` and `pyproject.toml` (patch for fixes, minor for features).
2. `pytest`, then `python scripts/build_examples.py`, then check screenshots of anything visual.
   (The version must also appear in the introductions of the README, the spec and the report; `check_docs.py` enforces it.)
3. Run the documentation coherence pass below.
4. Remove `.lattice-cache/`, `__pycache__/`, `*.egg-info/` and `.pytest_cache/`.

## Keeping the documentation coherent

Do this after every major task (a feature, a fix that changes behavior, a release), not only when something looks wrong. Documentation drifts one small edit at a time, and each document is read by someone who trusts it.

1. **Reread every document in full:** `README.md`, every file in `docs/`, and any README inside `examples/`. Skimming misses contradictions; they hide in examples and tables.
2. **Check each statement against the code and against its owner** in the documentation map above. The spec owns behavior; the report owns rationale and plans; the README owns user-facing usage; this file owns contributor workflow.
3. **Remove duplication.** When a fact appears in two places, keep it in its owner and replace the other occurrence with a reference (for example "see spec section 7.6"). A user-facing summary in the README is acceptable only if it links to the owning section and adds no facts of its own.
4. **Fix contradictions in place.** Update the text that is wrong rather than appending corrections elsewhere. Spec section 15 is a changelog table that points to the amended sections; it must not hold rules found nowhere else.
5. **Keep statuses aligned.** The version in `src/lattice/__init__.py` and `pyproject.toml`, the version named in the README and at the top of the spec and the report, and the roadmap (report section 6) must agree. The spec does not keep its own list of planned features; section 14 points to the roadmap.
6. **Check references.** Run `python scripts/check_docs.py`. It verifies that cited sections, repository paths, component names, CLI commands and flags exist, that the diagnostic codes in the code match spec section 12, and that versions agree. It cannot judge prose, so it complements steps 1 to 5 and does not replace them.
7. **Update this file** when the structure, setup, test suites or release steps change.
