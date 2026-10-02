# Lattice: Design Report

*Why Lattice is built the way it is, and where it is going. Current as of v0.7.1. What Lattice does exactly is defined in [`spec.md`](spec.md); how to use it is in the [README](../README.md); how to work on the code is in [`SKILL.md`](SKILL.md).*

---

## 1. Summary

Lattice is a Python library and CLI that compiles Markdown into a self-contained HTML/CSS/JS presentation. Unlike linear slide tools (reveal.js, Marp, Slidev), a Lattice deck is a **directed graph of slides**: the presenter can branch into detours, skip optional material, jump between related topics and return, all while keeping a sensible main path for normal use.

It targets computer science talks and lectures, so first-class support for **code, plots, graphs, animated algorithm traces and diagrams** is a core requirement, delivered through a component system that plugins extend rather than hard-coded features.

---

## 2. Goals and Non-Goals

### Goals

1. **Plain Markdown first.** A deck with no special syntax still compiles to a working linear presentation.
2. **Non-linear navigation.** Slides form a graph with a default path, branches, detours and links.
3. **Extensible content.** New data representations (plot types, animations, custom visualizations) are added as components without touching the core.
4. **Build-time Python, runtime JS.** Heavy work (layout, plotting, tracing algorithms) happens in Python at build time; the browser only replays precomputed data. This keeps output fast, deterministic and offline-capable.
5. **Single-file output.** One HTML file that works from a USB stick with no network.
6. **Reproducibility.** The same source produces the same output (stable layouts, seeded randomness).

### Non-Goals

- A WYSIWYG editor.
- Real-time collaboration or audience voting servers.
- Arbitrary server-side code execution during the talk.
- Screen reader support and accessibility features: decks are for personal use and are not published online (decision 8).
- Importing reveal.js or Marp Markdown (decision 9).

---

## 3. Design Overview

Each subsection gives the reasoning; the rules themselves are in the spec section cited.

### 3.1 Authoring stays close to Markdown (spec sections 2 and 3)

Slides are cut at level-1 headings rather than at `---` separators, because `---` already means a thematic break in CommonMark and the title is what authors look for when scanning a file (decision 1). Everything Lattice adds reuses conventions from the Markdown ecosystem: `{#id .class key=value}` attribute blocks, `:::` containers, `[[wiki links]]` and fenced blocks whose info string names a component. A fence named after a language falls back to syntax highlighting, so ordinary code blocks keep working.

Large lectures are split across files with `::include`; ids are global so any slide can link to any other, and shared material (a refresher, a proof) is included where it is needed, including inside a detour (decisions 2 and 3).

### 3.2 The deck is a graph, navigated with history (spec sections 5 and 7)

Every slide has at most one `next` edge (the main path), plus branch, detour and link edges. The main path makes the default behavior of "press right" obvious; the other edges are where non-linearity lives. Detours are scoped: their last slide returns automatically, so a presenter can dive in and come back without planning the way out.

Navigation follows the history model (decision 5). Left undoes the last move, like a browser's back button, because a structural "previous slide" is ambiguous at merge points and meaningless after a jump. Up ends the current excursion in one move, which is what a presenter wants after answering a question from a backup slide.

### 3.3 Steps are positions, not events (spec sections 6, 9 and 10)

Within a slide, fragments and animations advance with the same key. Every stepping element is a track with numbered positions, and a slide step is a row of positions. When several tracks share a slide, a `timeline` block orders them explicitly rather than guessing (decision 4); a code block can instead follow an animation, which covers the most common pairing without a timeline.

Runtimes always receive an absolute position. This single rule makes backward navigation, reloads on a given step and synchronized tracks straightforward, and it is why frames are stored as full states rather than as a chain of changes (decision 6). Authors still write deltas, which is the natural way to describe an algorithm step; the build expands them, and switches to keyframes only for very large animations.

### 3.4 Build time does the work (spec sections 8 and 9)

A component is a Python class that turns a block into HTML plus data, and optionally names a small JavaScript runtime. Algorithm traces run the real Python implementation at build time, so an animation cannot drift from the code shown on the next slide. Layouts are computed once over every element that ever appears, so nodes never jump between frames. Results are cached by their inputs and dependencies, which keeps rebuilds fast while editing.

### 3.5 Output is self-contained (spec section 11)

A single HTML file embeds styles, scripts, data, images and math fonts, and includes a library only when the deck uses it (Plotly alone is several megabytes). A directory output exists for very large decks; it trades the single file for separately cacheable assets and must be served over HTTP.

### 3.6 Built-in components

Code with highlighting, stepping and diffs; plots with matplotlib, Vega-Lite and Plotly; Graphviz diagrams; math; animated graphs, arrays, trees and grids; basic block versioning and abstract interpretation run on small programs (3.10 and 3.11). The list with options is spec section 8.8, and `examples/` shows each one in use.

### 3.7 Trees move, graphs do not (spec sections 9.1 and 9.4)

A graph animation colors a fixed drawing, so one layout over every element keeps nodes still and the eye on what changes. A tree animation is about the shape itself: an insertion pushes nodes aside and a rotation lifts one node over another, so positions must change (decision 10). They are still computed in Python, per frame, in one shared box; the runtime only interpolates between two known positions on a single step. The binary layout places nodes by in-order rank, which a rotation preserves: nodes move only up or down, which is what a rotation means.

`TreeTrace` snapshots the author's own node objects rather than asking for a new description of the tree, so the animation runs the implementation students use, as graph traces already do.

### 3.8 The presenter sees what comes next (spec section 7.5)

The preview pane is a second, passive copy of the deck rather than a cloned slide, because only a real copy mounts components and shows their true state at a given position. It renders exactly what NEXT would show, including the next step of an animation. The scrubber sets the step directly: steps are positions, not history, so scrubbing never changes where Left or Up lead.

### 3.9 A PDF is a tour, printed (spec section 11.5)

A PDF is linear, so the export follows a tour and moves the rest of the graph into an appendix: detours, branch options not taken and linked backup slides (decision 11). Chromium prints what the runtime rendered, so every component looks as it does on screen, including plots drawn in the browser. Each page is a static copy of a rendered slide, and all copies are printed in one pass, which keeps links between pages working inside the PDF; printing each position separately and merging the files would lose them and need a PDF library.

### 3.10 Basic block versioning runs at build time (spec section 9.5)

Compiler talks want to show an algorithm that rewrites a graph while it traverses it, which no fixed drawing conveys. Rather than asking authors to hand-draw frames, Lattice runs a faithful model of Static Basic Block Versioning and Lambda Versioning (the algorithms of the thesis, chapters 2 and 3) on a small program written in a CFG language, and records one frame per event with an automatic caption. Authors control what is shown (limit, heuristic, hidden functions, event kinds, instruction-level frames) rather than how it is drawn, and every slide stays true to the algorithm.

Versions of one block are drawn on that block's row, in creation order, with positions recomputed per frame and gliding on single steps (decision 12). One Graphviz layout over every version ever created would leave holes when versions merge and would not read like the figures of the thesis; per-frame Graphviz layouts would move everything at every step. Block bands keep the source CFG's shape visible in the specialized CFG, which is what the technique is about. The style copies the thesis figures (context header, code, starred entries, dashed indexed return edges), with the blog post's origin colours as a fill so that versions of the same block are recognized at a glance.

Companions are followers: `bbv-cfg` highlights the origin block being specialized, and a `code` block follows either the program or the bundled pseudo-code of the algorithm through a `meta=` key, so a single mechanism pairs the animation with what the audience reads.

### 3.11 Abstract interpretation is the same drawing, annotated (spec section 9.6)

The analysis that SBBV extends works on a fixed graph, so its animation keeps the source CFG still and changes the annotation inside the blocks: contexts gain intervals, grow by union with widening and shrink at conditionals. Reusing the `bbv-cfg` drawing and the `bbv.js` runtime (with per-frame context lines) keeps the three techniques visually comparable on consecutive slides, which is the point of showing them together. Intervals live inside the type values rather than beside them, so one context class serves all three algorithms; the versioning algorithms simply drop intervals, as the thesis's implementations do. Widening uses thresholds because that is what reproduces the thesis's own chain (decision 13), and the chain is shown in the panel rather than as a drawn lattice.

### 3.12 Pointing at things, and pausing an animation (spec sections 6.4, 7.2 and 8.9)

Left undoes the last move, but a deck opened on a deep link has no history to undo. Rather than stopping, PREV then falls back to the structural predecessor (tour, main path, `next` edges, branches, detour origin) without recording anything, so the presenter can keep walking backward and the history model stays untouched (decision 15). Skipping ten steps or jumping to the last step of a slide are step moves, so they never touch history; the intermediate steps are played quickly instead of jumped over, because an animation that disappears is harder to follow than one that runs fast.

A detour step lets an animation pause for a refresher and resume where it left off. It is a row of the step table that repeats the previous row and names a detour: entering happens only when NEXT arrives on it, since steps are positions and must be reachable by the scrubber, the hash and a reload without side effects. Backward moves skip such rows, which would otherwise cost a dead key press. Skip moves roll over detour steps by default, since their purpose is to get somewhere fast; a `blocking` detour step stops them, for material that must not be bypassed, and an explicit key (`skip-detour`) remains the one way past it without entering, so a presenter is never trapped.

The `arrow` component is the one place where the runtime measures: element boxes exist only in the browser, so an arrow pointing at an element has to be laid out there. Everything else about it is decided at build time, including its default direction, a fixed angle of 315 degrees (decision 14): a direction computed from the layout at runtime would make the drawing depend on the window and on timing, and would be the first step down a path the project avoids.

### 3.13 One vocabulary for what the algorithms say (spec section 9.5)

A versioning or abstract interpretation frame has three places that talk: the context lines inside the nodes, the caption under the drawing and the panel beside it. Plain text made them all look alike, and a caption such as "B: i: fx [0, 127] ∪ fx [1, 128] = fx [0, 128]" asked the audience to parse it. The three now share one vocabulary (decision 16): the operation of the frame comes first as a badge whose colour says what kind of event it is (specialization, removal or merge, growth, completion), versions are chips filled with the origin colour of their block so that a caption points at the node it names, variables, types and intervals each have a colour, and removed tests are struck through in the caption as in the node. The build still decides every word: `trace.py` writes the caption with a small inline markup and the runtime only turns spans into styled text, which keeps captions strings for the frame stores, the presenter view and the PDF. Inside the nodes the `;;` comment notation of the thesis stays, with the types aligned in a column, because telling a context from code at a glance is what the notation is for.

---

## 4. Use Cases

### 4.1 Algorithms lecture with optional depth

A lecturer teaches Dijkstra. The main path covers intuition, an animated trace and complexity. From the complexity slide a detour offers a heap refresher, and a link leads to a proof of correctness. If students look lost, the lecturer takes the detour; otherwise it is skipped. Afterwards, students explore every detour themselves through the overview. (`examples/02-shortest-paths`)

### 4.2 Conference talk with backup slides

A 20-minute talk has a tight main path, plus backup slides (benchmark details, threat model, related work) that are off the path. During questions the speaker presses `g`, types "bench", jumps to the backup slide, then returns with Up.

### 4.3 Choose-your-own tutorial

A workshop starts with a branch: the audience picks one of three approaches. Each branch is its own sequence, and all converge on a shared comparison slide. The same deck serves sessions with different audiences. (`examples/03-sorting-workshop`)

### 4.4 Code walkthrough

A code review talk includes the real source file with `code-steps`, highlighting the parts discussed in order, then `diff-steps` walks through the refactoring version by version. Because code is included from files, the repository's tests guarantee the slides show working code. (`examples/05-refactoring-a-cache`)

### 4.5 Data results presentation

A research group presents benchmark results. Plots are generated from the latest CSV at build time, and interactive Vega-Lite or Plotly charts allow hovering on outliers during discussion. Rebuilding after a new benchmark run updates every figure.

### 4.6 Data structures course

A lecture on balanced trees animates each insertion and rotation from the actual implementation used in the lab assignment, and grids show a maze search and a dynamic programming table filling up. (`examples/06-trees-and-grids`)

### 4.7 Compiler lecture on specialization

A lecture on ahead-of-time optimization of dynamic languages shows Static Basic Block Versioning specializing `find` while the source CFG highlights the block at hand, then a branch lets the lecturer pick the version limit the audience asks about, and Lambda Versioning shows entry points and return points growing across two functions. (`examples/07-basic-block-versioning`)

### 4.8 Abstract interpretation lecture

Before versioning, a lecture shows the classical analysis on `sum-to-n`: the panel lists the successive values of the loop counter, union after union until widening jumps to the next threshold, and `fact` shows a comparison narrowing the loop body's context. The same program files then serve the SBBV and ΛV slides. (`examples/07-basic-block-versioning`)

### 4.9 Handouts

After the lecture, the teacher exports the main path to PDF with the detours as an appendix and posts it. Students who missed a detour find it at the end, one click away from the slide that leads to it.

---

## 5. Technology Choices

| Concern | Choice | Reason |
|---|---|---|
| Markdown parsing | markdown-it-py with mdit-py-plugins | CommonMark compliant, token stream with source lines, container and math plugins, easy custom rules |
| Validation of options and front matter | pydantic | Typed validation with precise error messages |
| HTML generation | Python f-strings | The page has a single fixed structure; a template engine would add a dependency without adding flexibility yet |
| Code highlighting | Pygments | Build time, no runtime JavaScript, hundreds of languages |
| Graph layout | Graphviz CLI (`dot`), NetworkX fallback | Stable, high-quality layouts without compiled Python bindings; the fallback keeps graphs working without Graphviz |
| Static plots | matplotlib (optional extra `plot`) | Ubiquitous, produces SVG that inherits the slide fonts |
| Interactive plots | Vega-Lite and Plotly, vendored | Work offline; embedded only when used |
| Math | KaTeX, vendored, rendered in the browser | Fast and dependable offline; build-time rendering would require Node.js |
| Runtime | Vanilla JavaScript, no build step | Small, readable, no framework lock-in; runs as a module or a classic script |
| Dev server | Standard library HTTP server, polling watcher, server-sent events | No extra dependencies; fast enough for decks |
| Browser tests and screenshots | Playwright with Chromium (extra `dev`); Firefox optionally, for layout checks | Tests the real navigation and layout; the two engines resolve flex sizes differently |
| PDF export | Chromium through Playwright (extra `pdf`) | Prints what the runtime renders, with vector text and internal links; no PDF library needed |

---

## 6. Roadmap

**v0.1 (done).** Parsing with `#` boundaries, attributes, includes, links, detours, branches, reveal, notes, timelines and followers; graph resolution and diagnostics; the history-based navigation; overview, go-to, tours and presenter view; code, code steps, matplotlib plots, Graphviz diagrams, math, graph and array animations; plugin API; single-file output, cache, dev server and CLI.

**v0.2 (done).** Vega-Lite and Plotly backends, `diff-steps`, directory output, image embedding, the graph-shaped overview map; columns that contain their content (0.2.1); built-in theme validation and the remaining diagnostics (0.2.2).

**v0.3 (done).** Tree traces (insertions, rotations) and grid traces (maze search, dynamic programming tables); PDF export following a tour, with detours, branch options and linked slides as an appendix and animations exported as selected frames; presenter view with a preview of what comes next and a step scrubber.

**v0.4 (done).** Basic block versioning: a build-time model of SBBV and ΛV on programs written in a small CFG language, `bbv-anim` with one frame per event (block or instruction granularity), automatic captions, the block bands layout, `bbv-cfg` as a follower, `code` following the program or the bundled pseudo-code of the algorithms.

**v0.5 (done).** Abstract interpretation: integer intervals in abstract values with threshold widening and comparison narrowing, parameter annotations and comparison tests in `.bbv` programs, `abstract-interp-anim` with per-frame contexts, dead edges and the widening chain in the panel.

**v0.6 (done).** Navigation: Left walks the structure backward when the history is empty, skip keys that play ten steps quickly or jump to the last step, a Keybindings section in the presenter view; detour steps, so an animation can pause for a refresher; the `arrow` component.

**v0.7 (done).** Rich text in the versioning and abstract interpretation animations: operation badges, version chips in origin colours, coloured types, intervals, keywords and removed tests in captions, nodes and panel; drawings keep their height in narrow columns; origin colours survive a version being hidden and shown again.

**Later.**
- Spatial mode: slides placed on a canvas, with pan and zoom transitions that make detours "dive in".
- Plugin hooks beyond components (new syntax, generated slides, custom checks).
- Custom themes as folders, and layout templates.
- Pyodide for live Python, Mermaid diagrams, preloading of neighbor slides, editor integration.
- Basic block versioning: an importer for the state stream of the Gambit implementation (`--plot`), a Scheme front end producing `.bbv` programs, jump cascade removal in the final frame, other traversal orders.

---

## 7. Design Decisions

Decisions taken while writing the specification, and since.

| # | Question | Decision |
|---|---|---|
| 1 | Slide separator | A level-1 ATX heading (`#`) starts a slide. A bare `#` (or `# {attrs}`) makes an untitled slide. Setext level-1 headings are rejected. |
| 2 | Detour definition | Detours are nested slides only. Slides may live in other files (through `include`) and are referenced by global ids. |
| 3 | Multi-file decks | Yes: a root file uses `::include{file=...}` to splice in other Markdown files, at top level or inside a detour. |
| 4 | Combined steps | Yes. A slide with two or more independent tracks must declare a `timeline` block, otherwise the build fails. Followers (`follow=`) do not count as independent tracks. |
| 5 | History semantics | History model: Left undoes the last move; Up returns to the origin of the latest excursion and discards it; returning restores the step the slide was left at, so backward moves land on the last step. |
| 6 | Frame format | Delta-style authoring, full states emitted at build time, automatic fallback to keyframes plus deltas above a size threshold. |
| 7 | Security | Personal use: Python referenced by a deck runs at build time without any trust flag. |
| 8 | Accessibility | Not supported. |
| 9 | Import from other tools | Not supported. |
| 10 | Tree layout | Positions per frame, computed at build time in one shared box; in-order layout for binary trees. Graphs keep one layout for all frames. |
| 11 | PDF contents | The tour (default: main path), then an appendix of detours, branch options not taken and linked off-path slides. Steps per slide: `last` by default, a `pdf` attribute otherwise, numbered from 0 as in the URL. |
| 12 | Versioning animations | Built-in components, not a plugin. Programs in a text CFG language (or Python objects). The thesis type lattice with `#f` as its own type. Thesis figure style with origin colours. Block bands layout, top to bottom by default, functions side by side, positions per frame. Companions through followers. Version limits compared with branches or detours, not a live control. One frame per event by default. |
| 13 | Abstract interpretation | Component `abstract-interp-anim` on the `bbv-cfg` drawing. Intervals for integers only, inside the type values; they decide `fx` versus `fx | bg`. Threshold widening at every join (thesis thresholds, `sign`, `none`). Direct comparison tests only (no tracking of boolean temporaries). Entry contexts from parameter annotations. Entry context in the block, exit context in the tooltip. Widening chain as a panel list. |
| 14 | Arrow component | Built in, named `arrow` (registered names win over the obscure Pygments `arrow` lexer). Targets by element id or CSS selector, resolved in the browser, which also measures the geometry: the only runtime layout in Lattice. Default direction: a fixed angle of 315 degrees (the arrow comes from the lower right), never a direction computed from the layout. Steps make it a track. |
| 15 | Backward navigation without history | PREV falls back to the structural predecessor (tour, main path, `next`, branch, detour origin) and records nothing. Skip moves are step moves, clamped to the slide, played quickly. Detour steps are entered only by NEXT and skipped by PREV; a `blocking` detour step stops a skip playback, and `skip-detour` (Shift+Down) is the explicit way over a detour step. |
| 16 | Rich text of the versioning animations | One vocabulary for captions, node contexts and the panel: badge for the operation (colour by category), chips in origin colours for versions, a colour each for variables, types and intervals, keywords coloured, removed tests struck through. The build writes captions with an inline backtick markup (`lattice.bbv.rich`); the runtime styles it. The `;;` notation stays in the nodes, with the types aligned. |
