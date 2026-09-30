# Lattice: Design Report

*Why Lattice is built the way it is, and where it is going. Current as of v0.2.2. What Lattice does exactly is defined in [`spec.md`](spec.md); how to use it is in the [README](../README.md); how to work on the code is in [`SKILL.md`](SKILL.md).*

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

Code with highlighting, stepping and diffs; plots with matplotlib, Vega-Lite and Plotly; Graphviz diagrams; math; animated graphs and arrays. The list with options is spec section 8.8, and `examples/` shows each one in use.

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

### 4.6 Data structures course (planned)

A lecture on balanced trees animates each insertion and rotation from the actual implementation used in the lab assignment. This needs a tree trace (roadmap, section 6).

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
| Browser tests and screenshots | Playwright with Chromium (extra `dev`) | Tests the real navigation and layout |

---

## 6. Roadmap

**v0.1 (done).** Parsing with `#` boundaries, attributes, includes, links, detours, branches, reveal, notes, timelines and followers; graph resolution and diagnostics; the history-based navigation; overview, go-to, tours and presenter view; code, code steps, matplotlib plots, Graphviz diagrams, math, graph and array animations; plugin API; single-file output, cache, dev server and CLI.

**v0.2 (done).** Vega-Lite and Plotly backends, `diff-steps`, directory output, image embedding, the graph-shaped overview map; columns that contain their content (0.2.1); built-in theme validation and the remaining diagnostics (0.2.2).

**v0.3 (next).**
- More traces: trees (insertions, rotations) and grids (maze search, dynamic programming tables).
- PDF export following a tour, with detours as an appendix and animations exported as selected frames.
- Presenter view: preview of the next slide and a scrubber for animations.

**Later.**
- Spatial mode: slides placed on a canvas, with pan and zoom transitions that make detours "dive in".
- Plugin hooks beyond components (new syntax, generated slides, custom checks).
- Custom themes as folders, and layout templates.
- Pyodide for live Python, Mermaid diagrams, preloading of neighbor slides, editor integration.

---

## 7. Design Decisions

Decisions taken while writing the specification.

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
