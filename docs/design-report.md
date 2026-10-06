# Lattice: Design Report

*Why Lattice is built the way it is, and where it is going. Current as of v0.22.0. What Lattice does exactly is defined in [`spec.md`](spec.md); how to use it is in the [README](../README.md); how to work on the code is in [`SKILL.md`](SKILL.md).*

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

Container fences close the innermost open container, as Pandoc's fenced divs do, rather than following markdown-it-container, where an outer fence needs more colons than every fence inside it. That rule made adding a level of nesting (a column inside a detour's slide, a callout inside the column) a matter of recounting the colons of every enclosing fence, and a `:::` quoted in a code block closed a real container. Counting fences instead, and skipping code blocks while doing so, lets every level use `:::`; decks written with decreasing counts parse as before. A forgotten fence is the weakness of the rule, since a closing fence then matches the wrong opener, so a closing fence may name its container, `::: /NAME`, and the build checks the name (decision 23).

Large lectures are split across files with `::include`; ids are global so any slide can link to any other, and shared material (a refresher, a proof) is included where it is needed, including inside a detour (decisions 2 and 3).

### 3.2 The deck is a graph, navigated with history (spec sections 5 and 7)

Every slide has at most one `next` edge (the main path), plus branch, detour and link edges. The main path makes the default behavior of "press right" obvious; the other edges are where non-linearity lives. Detours are scoped: their last slide returns automatically, so a presenter can dive in and come back without planning the way out.

Navigation follows the history model (decision 5). Left undoes the last move, like a browser's back button, because a structural "previous slide" is ambiguous at merge points and meaningless after a jump. Up ends the current excursion in one move, which is what a presenter wants after answering a question from a backup slide.

### 3.3 Steps are positions, not events (spec sections 6, 9 and 10)

Within a slide, fragments and animations advance with the same key. Every stepping element is a track with numbered positions, and a slide step is a row of positions. When several tracks share a slide, a `timeline` block orders them explicitly rather than guessing (decision 4); a code block can instead follow an animation, which covers the most common pairing without a timeline. Timeline lines are resolved against the positions left by the lines before them, so a range can start where its track is (`reveal ..end`, the rest of the fragments) and a long animation needs no frame counting (decision 26).

Runtimes always receive an absolute position. This single rule makes backward navigation, reloads on a given step and synchronized tracks straightforward, and it is why frames are stored as full states rather than as a chain of changes (decision 6). Authors still write deltas, which is the natural way to describe an algorithm step; the build expands them, and switches to keyframes only for very large animations.

### 3.4 Build time does the work (spec sections 8 and 9)

A component is a Python class that turns a block into HTML plus data, and optionally names a small JavaScript runtime. Algorithm traces run the real Python implementation at build time, so an animation cannot drift from the code shown on the next slide. Graph layouts are computed once over every element that ever appears, so nodes never jump between frames (trees and versioning drawings, whose shape is the point, are the exceptions of 3.7 and 3.10). Results are cached by their inputs and dependencies, which keeps rebuilds fast while editing.

### 3.5 Output is self-contained (spec section 11)

A single HTML file embeds styles, scripts, data, images and math fonts, and includes a library only when the deck uses it (Plotly alone is several megabytes). A directory output exists for very large decks; it trades the single file for separately cacheable assets and must be served over HTTP.

### 3.6 Built-in components

Code with highlighting, stepping, diffs and morphing; plots with matplotlib, Vega-Lite and Plotly; Graphviz diagrams; math; animated graphs, arrays, trees and grids; basic block versioning and abstract interpretation run on small programs (3.10 and 3.11). The list with options is spec section 8.8, and `examples/` shows each one in use.

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

The analysis that SBBV extends works on a fixed graph, so its animation keeps the source CFG still and changes the annotation inside the blocks: contexts gain intervals, grow by union with widening and shrink at conditionals. Reusing the `bbv-cfg` drawing and the `bbv.js` runtime (with per-frame context lines) keeps the three techniques visually comparable on consecutive slides, which is the point of showing them together. Intervals live inside the type values rather than beside them, so one context class serves all three algorithms; the versioning algorithms drop intervals unless asked (`intervals`), because the paper's sections 3.2 and 3.3 add them to SBBV but the figures of the thesis chapters are drawn without them. Widening uses thresholds because that is what reproduces the thesis's own chain (decision 13), and the chain is shown in the panel rather than as a drawn lattice.

### 3.12 Pointing at things, and pausing an animation (spec sections 3.9, 6.4, 7.2, 8.9 and 8.10)

Left undoes the last move, but a deck opened on a deep link has no history to undo. Rather than stopping, PREV then falls back to the structural predecessor (tour, main path, `next` edges, branches, detour origin) without recording anything, so the presenter can keep walking backward and the history model stays untouched (decision 15). Skipping ten steps or jumping to the last step of a slide are step moves, so they never touch history; the intermediate steps are played quickly instead of jumped over, because an animation that disappears is harder to follow than one that runs fast.

A detour step lets an animation pause for a refresher and resume where it left off. It is a row of the step table that repeats the previous row and names a detour: entering happens only when NEXT arrives on it, since steps are positions and must be reachable by the scrubber, the hash and a reload without side effects. Backward moves skip such rows, which would otherwise cost a dead key press. Skip moves roll over detour steps by default, since their purpose is to get somewhere fast; a `blocking` detour step stops them, for material that must not be bypassed, and an explicit key (`skip-detour`) remains the one way past it without entering, so a presenter is never trapped.

A badge announces its detour from the first step, which gives the game away when the detour is a question the presenter means to ask later: a slide that reveals some code and then pauses on two questions would show both at once. `badge=step` and `badge=next` show the badge from the step before its detour step on, or only at the step before each of its detour steps, so the badge appears when Right is about to enter it. This is display only, like a reveal fragment: no new step, no change to `at` numbering or to navigation, and the runtime decides from the step alone, so the scrubber, a reload, the preview and the PDF agree. The runtime finds the step in `stepDetours`, which the deck already carries, rather than a step index stamped into the badge at build time, because badges are rendered before steps are compiled; a lookup in a table the build produced is not the computation the runtime is kept from. Both values are an error on a detour that is not a step, rather than a silent `true`, since the author asked for something that cannot happen (decision 17).

A badge is drawn where its detour is written, and a detour must sit at the top level of the slide, so a badge could not go in a column. Allowing detours inside columns would bury their slides in the column markup; instead, `::detour-badge{ref=ID}`, a leaf directive like `::include`, places a badge of a detour declared at the top level (decision 18). A placed badge replaces the default one rather than requiring a `badge=ref` value, so the detour's `badge` mode stays a default that its badges inherit; a badge may override its label and mode, which lets one detour have several badges that differ, but not its key, `at` or `blocking`, since those belong to the detour and to the step table, which must not depend on where badges are drawn.

The `arrow` component is the one place where the runtime measures: element boxes exist only in the browser, so an arrow pointing at an element has to be laid out there. Everything else about it is decided at build time, including its default direction, a fixed angle of 315 degrees (decision 14): a direction computed from the layout at runtime would make the drawing depend on the window and on timing, and would be the first step down a path the project avoids. Anchors follow the same line: `from_anchor` and `to_anchor` are angles fixed by the author (a side is an angle), the build turns names into numbers, and the runtime only intersects a ray with a box.

An arrow is only as stable as its target. Line numbers and token positions (`.lt-line[data-line="2"] > :nth-child(10)`) move silently when the source file is edited, and cannot name an expression that spans several tokens. Named segments (decision 19) put the name in the source, inside comments, so the file stays the single source of truth and still runs: `#|@i-init|# (i 0) #|@end|#`. Block comments are recognized whatever the language, since the delimiters are distinctive and some files are shown as `text`; languages with line comments only use a whole-line form. The markers vanish from the slide, line numbers keep counting the file as written (so `lines=` matches the editor), and Pygments' output is wrapped rather than re-rendered, so code without markers renders exactly as before. A segment is an element id like any other, checked for duplicates on its slide (LT058), and highlights accept it beside line ranges.

Bullets are the other common target, and the same reasoning applies: `#facts > li:nth-child(2)` is a selector the build cannot check, and the left side of a two-line item is the middle of the whole item, not its bullet. Lists are visible to the build, so `facts[2]` names an item (from 1, like the numbers of an ordered list and `nth-child`, with `[-1]` for the last and `[2][1]` to descend into a nested list) and the build checks that the item exists (LT063); the bracket form is not a CSS selector, so no working target changes meaning. The `bullet` anchor puts an end at the item's marker and leaves to the left, a fixed direction like the sides, rather than one aimed at the other end, which could cross the item's text. A marker has no box in the page, so the runtime has to measure it, and the browser's own discs are drawn at positions that are neither proportional to the font size nor the same in Chromium and Firefox. Text markers are exact: an outside text marker ends where the item's content starts, and its width is how far the first character moves when the marker is set inside for one measurement, identical in both engines. The built-in bullets are therefore text (`•`, `◦`, `▪` and an en space, which keeps them where the discs were), set with `list-style-type` under `:where()`, so any theme or plugin rule on lists still wins, and lists styled by a plugin (`list-style: none`, markers in `::before`) are untouched. Drawing markers with absolutely positioned `::before` elements was considered and rejected for that reason: it would have overridden every author rule on lists (decision 25).

### 3.13 One vocabulary for what the algorithms say (spec section 9.5)

A versioning or abstract interpretation frame has three places that talk: the context lines inside the nodes, the caption under the drawing and the panel beside it. Plain text made them all look alike, and a caption such as "B: i: fx [0, 127] ∪ fx [1, 128] = fx [0, 128]" asked the audience to parse it. The three now share one vocabulary (decision 16): the operation of the frame comes first as a badge whose colour says what kind of event it is (specialization, removal or merge, growth, completion), versions are chips filled with the origin colour of their block so that a caption points at the node it names, variables, types and intervals each have a colour, and removed tests are struck through in the caption as in the node. The build still decides every word: `trace.py` writes the caption with a small inline markup and the runtime only turns spans into styled text, which keeps captions strings for the frame stores, the presenter view and the PDF. Inside the nodes the `;;` comment notation of the thesis stays, with the types aligned in a column, because telling a context from code at a glance is what the notation is for.

### 3.14 Code that changes in place (spec section 8.11)

A bug fix is a change of a few tokens, and the audience should see those tokens change, not a second pane replace the first. `code-morph` treats the code as units (words and single symbols) on a monospace grid: every unit is an element at a row and a column, and a version is a set of positions. Python aligns consecutive versions (lines first, then the units of each changed region, so a unit can survive onto another line), gives every surviving unit one identity, and ships the positions; the runtime sets two numbers per unit and lets CSS transitions do the motion (decision 21). Nothing is measured, since a monospace grid needs no measuring, and nothing is diffed in the browser. A morph highlights as a `code` block does, per position (decision 27): the bands and segment marks are a layer per position painted under the units, built in Python with the rest, because the text copy on top must stay transparent for the arrows and units already use their opacity to fade.

Spaces are gaps, not units. Indentation is then a column, so code that moves into a new block slides right instead of being deleted and retyped. Transitions rather than a frame loop because they continue from wherever an interrupted change left the units, which is what the skip keys need, and because the final values are the same inline values a direct `show` writes, so the end state cannot depend on the path. A transparent copy of the current text over the units keeps selection working and carries the segments, which therefore have their final boxes as soon as the position changes; arrows re-measure when the morph announces a move (`lt-relayout`) and glide with the code's own timing.

Two authoring forms share that pipeline. `versions:` is the input of `diff-steps`, so a slide can switch between the static, marked-up view and the morph; a version may change language, matched on text alone. `file` with `steps:` writes the code once, with segment markers, and each step gives new text to named segments, so the surrounding code has a single source and the segment's name follows its text (an arrow at the bug points at the fix). By default the block keeps the height of its tallest version (`room=max`), so nothing else on the slide moves; `room=fit` is there for when the reserved space would look empty.

### 3.15 A closer look that is not a step (spec sections 7.7 and 9.5)

The versioning drawings are dense by nature: a CFG of fourteen versions, each with its context, does not fit a slide at a readable size, so authors draw labels only and the details sit in a tooltip nobody in the room can see. A click on a block now enlarges it: the block grows out of its place to most of the slide, with everything it holds (context, code, exit context), and the slide blurs behind it. Two properties keep it from fighting the rest of the design. It is not a position: opening and closing it touches neither the step nor the history, the URL or the storage, so "steps are positions" (section 3.3) still holds, and closing it on any key, instead of acting on the key, means the presenter never navigates by accident while pointing at a block. And it is the core's, not the component's: components may not listen to keys (spec 10.2), and the "any key closes" rule must win over navigation, so the core owns the card, the blur, the input rules and the presenter sync, and a component only hands it an element through a `zoom` hook (decision 24). The enlarged block shows the current step, not the end of the run, and its size comes from the build like every node size, so the browser only draws.

---

## 4. Use Cases

### 4.1 Algorithms lecture with optional depth

A lecturer teaches Dijkstra. The main path covers intuition, an animated trace and complexity. From the complexity slide a detour offers a heap refresher, and a link leads to a proof of correctness. If students look lost, the lecturer takes the detour; otherwise it is skipped. Afterwards, students explore every detour themselves through the overview. (`examples/02-shortest-paths`)

### 4.2 Conference talk with backup slides

A 20-minute talk has a tight main path, plus backup slides (benchmark details, threat model, related work) that are off the path. During questions the speaker presses `g`, types "bench", jumps to the backup slide, then returns with Up.

### 4.3 Choose-your-own tutorial

A workshop starts with a branch: the audience picks one of three approaches. Each branch is its own sequence, and all converge on a shared comparison slide. The same deck serves sessions with different audiences. (`examples/03-sorting-workshop`)

### 4.4 Code walkthrough

A code review talk includes the real source file with `code-steps`, highlighting the parts discussed in order, then `diff-steps` walks through the refactoring version by version, and a bug is fixed in place with `code-morph`, the audience watching the faulty comparison turn into the right one. Because code is included from files, the repository's tests guarantee the slides show working code. (`examples/05-refactoring-a-cache`)

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
| Markdown parsing | markdown-it-py with mdit-py-plugins | CommonMark compliant, token stream with source lines, math and front matter plugins, easy custom rules (containers are a rule of Lattice's own, spec section 3.2) |
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

**v0.7.1 and v0.7.2 (done).** Scheme highlighting of binding sites; the user manual, a deck of its own in `user_manual/` that shows every feature live and is built and checked with the examples.

**v0.8 to v0.10 (done).** Badges that wait for their detour step (`badge=step`, `badge=next`), so a slide does not announce its questions before their turn; badges placed anywhere on the slide with `::detour-badge` (in a column, for instance), several per detour; `.reveal-with`, which reveals a block on the same step as the previous fragment.

**v0.11 (done).** Named segments in code, written as markers in comments of the source, so arrows and highlights point at `i-init` rather than a line and a token; arrow anchors, so an arrow leaves and enters at a chosen side or angle.

**v0.12 (done).** `code-morph`: code whose text changes in place between positions, tokens gliding to their new places, from versions (a language each, if wanted) or from new text for named segments of one file; arrows follow the code as it moves. 0.12.1 fixes the scrolling of tall code blocks to their highlight, on screen and in the PDF.

**v0.13 (done).** Vector bound checks in SBBV and ΛV, from sections 3.2 and 3.3 of the paper (thesis appendix D): intervals in the versioning algorithms with widening at merges, the `vec` type, vector lengths as symbolic bounds `⟦v⟧-i` tied to the class of the vector, the bound-check and overflow-check elimination of `findv` (figure 7), intervals as tie-breakers of the merge heuristics. Also in the abstract interpreter, since the three share their transfer functions.

**v0.14 (done).** Container fences that nest without counting colons: a bare `:::` closes the innermost open container, code blocks are skipped, and `::: /NAME` closes a container and checks its name.

**v0.15 (done).** Enlarged blocks: a click on a block of a versioning or abstract interpretation drawing (or of the source CFG) enlarges it with all its details at the current step, over a blurred slide; any key or a click outside closes it without moving; shared by the presenter and audience windows.

**v0.16 (done).** Arrows at list items and their bullets: `facts[2]` names an item (nested and from the end), `from_anchor=bullet` leaves from its marker, both checked at build time; bullets are text markers, measured exactly.

**v0.17 (done).** Shorter timelines: open ranges from the current position (`reveal ..end`, `trace ..+2`), positions counted from the last (`end-1`), strides (`by 2`) and several ranges on one line advancing in lockstep.

**v0.18 (done).** Highlights in `code-morph`: lines and segments per version or step, a default for every position, and `changed` for the rows where new tokens arrived; example 05 uses it.

**v0.19 (done).** Sub-bullets revealed one by one (`{.reveal}` on the line after an item's text), and LT059 quiet for morph positions that differ only by their highlights; both came from preparing a defense slide.

**v0.20 (done).** Widening thresholds that name the fixnum range (`[sign, maxfix]`), and predicates of a `prims` option usable in an `if`; for the defense slide that analyses `findv`.

**v0.21 (done).** `vector_bounds: false` drops the symbolic vector bounds (lengths become numbers up to maxfix), and threshold names take offsets (`maxfix-1`); the defense's `findv` now checks overflow with `fx+?`, and the analysis removes that check without symbols.

**v0.22 (done).** A `null` step of `arrow` is a position without an arrow, so one arrow block can appear for a few steps of a slide only; for the defense slide that explains why four checks of `findv` are redundant.

**Later.**
- Spatial mode: slides placed on a canvas, with pan and zoom transitions that make detours "dive in".
- Plugin hooks beyond components (new syntax, generated slides, custom checks).
- Custom themes as folders, and layout templates.
- Pyodide for live Python, Mermaid diagrams, preloading of neighbor slides, editor integration.
- Enlarged elements for other components: graph and tree nodes, code blocks, plots (the core layer and the `zoom` hook are generic).
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
| 13 | Abstract interpretation | Component `abstract-interp-anim` on the `bbv-cfg` drawing. Intervals for integers only, inside the type values; they decide `fx` versus `fx | bg`. Threshold widening at every join (`machine` thresholds, `sign`, `none`). Direct comparison tests only (no tracking of boolean temporaries). Entry contexts from parameter annotations. Entry context in the block, exit context in the tooltip (and, since 0.15, in the enlarged block). Widening chain as a panel list. |
| 14 | Arrow component | Built in, named `arrow` (registered names win over the obscure Pygments `arrow` lexer). Targets by element id or CSS selector, resolved in the browser, which also measures the geometry: the only runtime layout in Lattice. Default direction: a fixed angle of 315 degrees (the arrow comes from the lower right), never a direction computed from the layout. Steps make it a track. |
| 15 | Backward navigation without history | PREV falls back to the structural predecessor (tour, main path, `next`, branch, detour origin) and records nothing. Skip moves are step moves, clamped to the slide, played quickly. Detour steps are entered only by NEXT and skipped by PREV; a `blocking` detour step stops a skip playback, and `skip-detour` (Shift+Down) is the explicit way over a detour step. |
| 16 | Rich text of the versioning animations | One vocabulary for captions, node contexts and the panel: badge for the operation (colour by category), chips in origin colours for versions, a colour each for variables, types and intervals, keywords coloured, removed tests struck through. The build writes captions with an inline backtick markup (`lattice.bbv.rich`); the runtime styles it. The `;;` notation stays in the nodes, with the types aligned. |
| 17 | Badges of detour steps | `badge=step` (from the step before the detour step on) and `badge=next` (only at the step before each of its detour steps) beside `true` and `false`. Display only, like a reveal fragment; the runtime reads the step from `stepDetours`. The footer's Down hint follows the first detour's badges. An error (LT055) on a detour that is not a detour step. |
| 18 | Placed badges | `::detour-badge{ref=ID}`, a leaf directive, places a badge of a detour of the same slide anywhere (columns, callouts, lists); the detour stays at the top level and needs an explicit id. A placed badge replaces the default one; it inherits the label and mode and may override them, not the key, `at` or `blocking`. Errors are LT056. |
| 19 | Named segments in code | Markers in comments of the source (`@NAME` ... `@end`), block comments of any language inline, line comments on lines of their own; removed from the display with the spaces they leave. Line numbers count the file as written. Segments are `.lt-seg` spans, one piece per line, the first with the id. Usable by arrows and in highlights. Ids unique per slide (LT058); `markers=false` to show markers. |
| 20 | Arrow anchors | `from_anchor` and `to_anchor`: a side, `center` or an angle in degrees, with the convention of `angle`; the end sits where the ray from the box center at that angle leaves the box, and the curve leaves or enters along it. Cubic curves, reducing to the earlier quadratic without anchors. |
| 21 | Code that changes | `code-morph`: units (words and single symbols, spaces as gaps) on a monospace grid, aligned in Python by lines then by the units of each changed region, matched on class and text (text alone across a language change); one element per surviving unit, placed with `ch` and line units and moved by CSS transitions in three phases (out, glide, in; 600 ms); a transparent text copy for selection and segments; `room=max` by default; `versions:` as `diff-steps`, or `file` with cumulative `steps:` replacing named segments; `lt-relayout` for arrows. `diff-steps` unchanged. |
| 22 | Vector bound checks | Paper sections 3.2 and 3.3 in `sbbv`, `lv` and `absint`. `intervals` off by default in the versioning algorithms (on, the `fact` example's `return 1` becomes a distinct exit contract). A merge is the union with widening of the older version against the newer. One bound per side (the paper's domain; two bounds would be more precise but walk the whole numeric widening chain before the symbol remains). A symbolic bound names the class representative of its vector, so equal shapes are equal contexts structurally; every context operation remaps symbols and widens those whose vector left or whose class is no longer exactly `vec`. Narrowing keeps the symbolic candidate for upper bounds and the numeric one for lower bounds (the paper's `minhi` by value does not reproduce figure 7; `vallo(⟦v⟧-i)` is `-i`, a typo in the paper). Symbolic upper bounds widen to `⟦v⟧`, then to their numeric value. Intervals add a fraction to the Hamming distance of the heuristics. `fixnum_bits` 61 (3-bit tags). `checks` counts every test left. |
| 23 | Container fences | A bare closing fence closes the innermost open container, whatever the colons, as in Pandoc; the end of a container is found by counting fences, skipping code blocks. An optional named closing fence, `::: /NAME` (the `/` cannot start a container name), checks the container it closes, like `@end NAME` for code segments. Mismatches and stray fences are errors (LT061); a container never closed is a warning (LT062), as markdown-it closes it at the end of its block. Decks written with decreasing colon counts parse as before. |
| 24 | Enlarged blocks | `clickable` (default on) and `clickable_show` (default `label`, `context`, `code` and `after`, the exit context) on `bbv-anim`, `bbv-cfg` and `abstract-interp-anim`. The card is a core feature (`api.zoom`, a controller hook `zoom(inst, key)`) because only the core may read keys; it is not a position (no history, hash or storage) and any render closes it. Any key closes it and does nothing else, except bare modifiers and Ctrl, Meta or Alt combinations (left to the browser); a press outside the card is swallowed. It fits 80% of the slide, magnifying at most 4.5 times, over the slide pane (never the presenter panel), and is mirrored between the presenter and audience windows. It shows the current step (queued versions, partial specialization, the frame's context), sized at build time. |
| 25 | Arrows at list items and bullets | `LIST[N]` names item `N` of the list with id `LIST` (from 1, negative from the end, `[N][M]` into the first nested list), checked at build time on the slide's HTML (LT063). The anchor `bullet` puts an end a gap left of the item's marker, at its vertical middle, leaving or entering to the left; valid only on a list item (`LIST[N]` or the id of an `<li>`), not on a whole list or a selector (LT063). An item's box leaves out its nested lists. Built-in bullets are text markers (`list-style-type` strings under `:where()`), measured by setting the marker inside for one measurement; drawn `::before` markers were rejected because they would override author rules on lists. |
| 26 | Timeline ranges | A range MAY omit its start, `..STOP`: it starts from the track's current position (known at build time, since positions are resolved line by line) and leaves it out, so `reveal ..end` reveals the rest and `t ..+N` plays `N` positions in `N` steps where `t +N` jumps them in one. A relative stop exists only for open ranges: after an explicit start (`2..+3`) it would be ambiguous (LT049), and relative starts (`+1..end`) were left out as a second way to write the same thing. `end-N` wherever `end` is accepted. `by K` keeps every `K`-th position and always ends on the stop. Several ranges on one line advance in lockstep and must have the same length (LT031, which used to forbid a second range). An empty open range is a warning (LT030) and adds no step unless its line sets other tracks; a value out of range is LT025 once per line. |
| 27 | Highlights in a morph | `highlight` takes the targets of `code` (lines, ranges, segments) per version or per step, for that position only (a `code-steps` list, not cumulative like the replacements), with the option as the default of every position; line numbers count the rows of the version shown. `changed` lights the rows holding units that did not survive from the position before, which is what the audience just watched arrive. A position's own targets are checked against its version (LT022); the default's lines must exist wherever it applies, its segments somewhere. Bands and segment marks are a layer per position, built in Python and painted under the units in two slots that cross-fade with the units' phases; units and line numbers outside the lit rows are dimmed by a class. A block without highlights renders as before. `highlight` in a `diff-steps` version is LT022 rather than ignored. |
| 28 | Attribute lines inside list items | An attribute line inside an item applies to the next block of that item, so a nested list can be revealed item by item. Written on the line after the item's text, where CommonMark reads it as the last line of the item's paragraph (so the list stays tight), or as a paragraph of its own; one followed by text applies to that paragraph, as at the top level. Fragments keep the document order (an item before the items nested in it). A line not followed by a block of the item stays text, as before. LT059 compares highlights too, since a morph that repeats its text to move a highlight is now a normal use. |
| 29 | Thresholds that name the fixnum range | A list of thresholds MAY name `machine`, `sign`, `maxfix` and `minfix`, resolved with `fixnum_bits`. The `machine` thresholds stay the thesis's (sign, 8, 32 and 64 bits), which figure 2 depends on; an index bounded by a vector length (at most maxfix) would otherwise widen past maxfix to `2^63-1` at a join and read `fx \| bg`. The `prims` option is applied before the program is checked, since a declared predicate could not be tested in an `if` before. |
| 30 | Lengths without symbols | `vector_bounds: false` keeps symbols out of every context rather than hiding them in the display: `vector-length` gives `fx [0, maxfix]` and annotations naming a length are widened at the entry, so the analyses run as before the paper's section 3.3 (figure 7 keeps the check against the second length read). Since the interpreter widens at every join, the bound `i < len` gives after a test survives only if a threshold sits on it: threshold names take an offset (`maxfix-1`) rather than widening only at loop heads, which would have changed the thesis figures' algorithm. |
| 31 | Arrows absent at some positions | A `null` step rather than a `visible` range or one block per arrow: an arrow is already a track with one position per entry, so leaving a position empty keeps the timeline the only place that says when (`why ..+4`, `why end`). The arrow shown after an empty position is placed, not glided from the last one, because a glide from an arrow the audience no longer sees would come from nowhere. |
