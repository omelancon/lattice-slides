---
name: lattice-authoring
description: How to write, build and check slide decks with Lattice (the lattice-slides package), which compiles Markdown into one self-contained, non-linear HTML deck for computer science talks (detours, branches, links, reveal steps and timelines, code walkthroughs and morphs, arrows, plots, Graphviz, graph, array, tree and grid animations, basic block versioning and abstract interpretation animations, presenter view, PDF export). Use this skill whenever you create or edit a Lattice deck or any Markdown file meant for `lattice build`, `lattice serve` or `lattice pdf` (a talk, a lecture, a thesis defense), even for a one-slide change, and whenever a request mentions slides together with `::: detour`, ```timeline, `code-morph`, `bbv-anim` or a talk.md, main.md or manual.md. It is not for changing the Lattice library itself: that is docs/SKILL.md.
---

# Authoring decks with Lattice

Lattice turns Markdown into **one self-contained HTML file** whose slides form a **graph**: a main path, detours that return by themselves, branches where the presenter picks, links to backup slides. Python does all the work at build time (layout, plots, algorithm traces, the versioning models); the browser only replays precomputed positions. Keep that in mind when something looks wrong: the fix is almost always in the Markdown or in a trace function, never in the HTML.

This file is for agents that *use* Lattice to build talks. It summarises the model, the workflow and every feature, and points to where each one is documented. It does not repeat the full syntax: read the owner of a topic before using a feature for the first time.

## Where the documentation is

All paths below are relative to the root of the Lattice repository. A deck project usually has its own clone of it (the PhD defense project keeps one in `lattice-slides/`, installed into `.venv` by its makefile), so look there; the installed package ships the code, not the documentation.

| Document | Use it for |
|---|---|
| `user_manual/manual.md` | **The first stop.** The user manual is itself a deck: every feature has a slide that uses it live, with its syntax beside it. Read the source of the slide you need. Open `user_manual/manual.html` in a browser to see it run (`#/SLIDE-ID` in the URL jumps to a slide) |
| `docs/spec.md` | The exact rules, when the manual is not enough: grammar (section 3), graph resolution (5), steps and timelines (6), navigation (7), components and every option (8, the table in 8.8), animation frames and the program language (9), the JavaScript runtime contract (10), output and PDF (11), every diagnostic (12) |
| `README.md` | A one-screen summary of the syntax, the components, the keys and the seven examples |
| `examples/*/talk.md` | Real decks to copy patterns from (list below), each with its built `talk.html` |
| `docs/design-report.md` | Why things are the way they are, and the roadmap (section 6): check it before concluding that a feature is missing |

In the feature map below, **manual `id`** means the slide with that id in `user_manual/manual.md` (search for `{#id`), and spec sections are those of `docs/spec.md`.

## Workflow

1. **Set up once.** `pip install -e ".[plot,pdf]"` from the Lattice checkout (matplotlib for `plot`, Playwright for PDF and screenshots), then `playwright install chromium`. Graphviz (`dot -V`) is a system package; without it `dot` blocks fail, animated graphs fall back to a NetworkX layout and the overview map is empty. Python 3.10 or newer. In a deck project that provides a makefile (the defense project does), use it instead: `make` clones or updates the checkout, builds the venv and the deck; then `. .venv/bin/activate` for the commands below.
2. **Start a deck** with `lattice new my-talk` (writes `my-talk/talk.md`), or split a large one into files joined by `::include` (manual `includes`).
3. **Check after every edit:** `lattice check talk.md --strict`. It prints `file:line:col: severity LTnnn: message` and exits 1 on errors (and, with `--strict`, on warnings). Fix every warning: LT015 (unreachable slide), LT020 (unknown fence name), LT026 (a track never advanced) and LT030 (a timeline cue that changes nothing) are usually real mistakes. Look codes up in manual `all-diagnostics` or spec section 12.
4. **Check the structure:** `lattice graph talk.md` prints every slide and edge (`--dot` for Graphviz). Use it after adding detours, branches, `next=` or tours.
5. **Build:** `lattice build talk.md` writes `talk.html` next to the source (`-o` to choose, `--dir out` for a served directory). The human previews with `lattice serve talk.md` (reloads on save).
6. **Look at it.** A clean build proves structure, not appearance: overflowing columns, arrows pointing at the wrong token, unreadable animations all build fine. Take screenshots with `scripts/snapshot.py` from the Lattice checkout and look at them after the last edit:

   ```bash
   python scripts/snapshot.py talk.html /tmp/shots "ArrowRight*12" --shots=3,7,12
   python scripts/snapshot.py talk.html /tmp/shots "ArrowRight*3" --presenter   # the presenter view
   ```

   It presses the keys, prints the navigation state after each (`{slide, step}`), saves `NN.png` for the presses listed in `--shots` (all of them by default) and reports JavaScript errors. It always opens the deck at its start slide, so count presses from there: a slide with `n` steps needs `n` presses to leave it (`lattice graph` lists the main path). Two timing traps: it waits 450 ms after a press, while a `code-morph` step or a change of column widths moves for 600 ms by default, so shoot one press later (append a key that does nothing, such as `Shift`, and list that one in `--shots`); and `End` or Shift+Right *play* the steps quickly rather than jump, and the next key cancels the playback, so press `ArrowRight` the right number of times instead. A human can open any position directly with `talk.html#/slide-id/step` (steps from 0).
7. **PDF**, if asked: `lattice pdf talk.md -o talk.pdf [--tour NAME] [--steps first|last|all] [--no-appendix]`, and the per-slide `pdf="0,3,end"` attribute (manual `pdf-export`, spec section 11.5). Inspect pages with `pdftoppm -png`.

Renders are cached in `.lattice-cache/` next to the root file. When a result looks stale (after updating Lattice, or editing a file a trace imports indirectly), pass `--no-cache`.

## The model in five terms

- **Slide**: everything from one level-1 `#` heading to the next. `##` and below stay inside the slide.
- **Scope**: the root deck or a detour. `next` edges stay inside a scope; the **main path** follows them from the start slide.
- **Track**: something on a slide that changes with steps: the reveal track (fragments), each component with several positions (an animation, `code-steps`, a moving `arrow`, `code-morph`), and the widths of named columns. A **follower** (`follow=ID`) copies its leader's position.
- **Step**: one row of the slide's table of track positions. With one independent track, Right just advances it; with two or more, a `timeline` block orders them.
- **Excursion**: a detour, a link, go-to or the overview. Up returns from it; Left undoes the last move (spec section 7.2).

## Feature map

### Deck and slides

| Feature | Syntax in brief | Where |
|---|---|---|
| Front matter (title, theme, aspect, start, tours, keys, transitions, plugins, build options) | YAML at the top of the root file only | manual `front-matter`, spec section 2.2 |
| Several files | `::include{file="parts/x.md" offpath=true}` at top level or in a detour | manual `includes`, spec section 2.3 |
| Slides, ids | `# Title {#id .class}`, bare `#`; ids are global across files | manual `slides-and-ids`, spec sections 3.3 and 3.6 |
| Slide attributes | `next=id\|back\|none`, `offpath=true`, `layout=title`, `transition=fade`, `pdf=...`, helper classes `.center`, `.fullbleed`, `.small` | manual `slide-attributes`, spec section 3.5 |
| Text, tables, math, images | CommonMark + GFM tables, `$x$`, `$$x$$`, `![alt](file.svg)` (embedded) | manual `text-and-math` and `images-and-code`, spec section 3.1 |
| Speaker notes | `::: notes` (links in notes are clickable in presenter view) | manual `links-and-notes`, spec section 3.14 |

### The slide graph

| Feature | Syntax in brief | Where |
|---|---|---|
| Main path and `next` resolution | implicit successor in the same scope, or `next=` | manual `the-graph`, spec section 5.2 |
| Detours | `::: detour {#id label=... key=k}` holding slides; the last one returns to the origin | manual `detours`, spec section 3.9 |
| A detour as a step of its slide | `at=N` on the detour, or a `detour ID` line in a timeline; `blocking` stops the skip keys | manual `navigation-details` and `timelines`, spec section 6.4 |
| Badges that wait or move | `badge=next`, `badge=step`, `badge=false`; `::detour-badge{ref=id}` placed in a column or item | manual `badge-steps`, `placed-badges`, `badge-inheritance`, spec section 3.9 |
| Branches | `::: branch {layout=cards}` holding one list of `[[target\|label]] {key=k} description`; give each option `next=` to converge | manual `branches`, spec section 3.10 |
| Links | `[[id]]`, `[[id\|label]]` (an excursion; Up comes back) | manual `links-and-notes`, spec section 3.7 |
| Backup slides, tours, overview, go-to | `offpath=true`; `tours: {short: [ids], full: main}`; keys `o`, `g`, `t` | manual `backup-and-tours`, spec section 5.7 |

### Steps

| Feature | Syntax in brief | Where |
|---|---|---|
| Fragments | `{.reveal}` on the line before a block (a list reveals item by item, also nested lists); `{.reveal-with}` joins the previous fragment | manual `fragments`, spec section 3.12 |
| Tracks and followers | an `#id` on every stepping component; `follow=LEADER` | manual `steps-and-tracks`, spec sections 6.1 and 6.2 |
| Timelines | ```` ```timeline ```` with one line per step: `reveal 2`, `trace 1..end`, `code +1, trace 5`, `detour heaps` | manual `timelines`, spec sections 3.15 and 6.3 |
| Timeline ranges | `..end` (from where the track is), `..+2`, `end-1`, `by 2`, several ranges in lockstep | manual `timeline-ranges`, spec section 6.3 |
| Columns that make room | `::: column {#src}` and a timeline line `width src=0 viz=1fr` | manual `columns-room` (and its detour `columns-room-how`), spec section 3.8 |

### Layout and style

| Feature | Syntax in brief | Where |
|---|---|---|
| Columns, callouts, custom containers | `::: columns` / `::: column {width=2fr}`, `::: callout {kind=tip}`, any other name is `<div class="NAME">` | manual `containers`, spec section 3.8 |
| Closing fences | a bare `:::` closes the innermost container; `::: /column` also checks the name | manual `closing-fences`, spec section 3.2 |
| Themes | `theme: default\|dark`, `aspect: 16:9`; theme custom properties `--lt-*` for your CSS | manual `themes` |

### Components

A fenced block whose name is a registered component renders it; any other name is a code language for Pygments (spec section 3.13). The full option list of every built-in component is spec section 8.8; the authoritative schemas are the pydantic `Options` models in `src/lattice/components/`.

| Component | What it does | Where |
|---|---|---|
| ```` ```python {highlight=2 title=...} ````, `code` | highlighted code, inline or from `file`, `lines`, `symbol`; `follow=` an animation to highlight the lines its frames name | manual `code-blocks` |
| `code-steps`, `diff-steps` | one highlighted range per step; versions of a file with added and removed lines | manual `code-steps` |
| named segments | `#\|@name\|# ... #\|@end\|#` or a line `# @name` in the code file: an id for arrows and highlights that survives edits | manual `code-segments`, spec section 8.10 |
| `code-morph` | code that changes in place (`versions:` or `file` + `steps:` replacing segments), `highlight` per position, `changed` | manual `code-morph`, `morph-segments`, `morph-highlights`, spec section 8.11 |
| `arrow` | points at an id, `list[2]`, a segment, a part of a versioning drawing (`cfg.B`, `cfg.A->L`, `cfg.L->B:false`; in `bbv-anim` `B` is all versions, `B1` one) or a CSS selector; `angle`, `length`, `from`, `from_anchor`/`to_anchor` (sides, angles, `bullet`); `steps:` makes it a track, `null` hides it | manual `dot-and-math`, `arrows`, `arrow-anchors`, `arrow-bullets`, `bbv-arrows`, spec sections 8.9 and 9.5 |
| `plot` | CSV shorthand (`data x y group logy`), `source="f.py:fn"`, raw `spec:`; `backend=matplotlib\|vega\|plotly` | manual `plots`, `plot-sources` |
| `dot`, `math` | Graphviz diagram (themed), display math | manual `dot-and-math` |
| `graph-anim`, `array-anim`, `tree-anim`, `grid-anim` | animations from your Python trace function (`source="traces.py:fn"`), one position per frame; `panel:`, `panel_at` | manual `graph-anim`, `graph-anim-options`, `array-anim`, `tree-anim`, `grid-anim` |
| writing a trace | `GraphTrace`, `ArrayTrace`, `TreeTrace`, `GridTrace` from `lattice`; `t.frame(nodes=..., panel=..., caption=..., meta={"line": 4})`; frames are deltas | manual `writing-traces`, `states`, spec sections 9.1 and 9.2 |
| `bbv-anim` | Static Basic Block Versioning (`algorithm=sbbv`) or Lambda Versioning (`lv`) run on a `.bbv` program; `limit`, `show`, `panel`, `intervals=true`, `granularity=instruction` | manual `compiler-animations`, `bbv-anim`, `bbv-blocks`, `bbv-options`, `bbv-intervals`, spec section 9.5 |
| `bbv-cfg` | the source CFG, static or following a `bbv-anim`; arrows name its blocks and edges | manual `bbv-anim`, `bbv-blocks`, `bbv-arrows` |
| `abstract-interp-anim` | the classical analysis with intervals, widening (`thresholds`) and narrowing; `history: [B.i]` | manual `lv-and-absint`, `absint-options`, spec section 9.6 |
| the `.bbv` program language | `function f(x)`, blocks `A:`, `if pair?(x) goto B else goto C`, `goto L(acc=x)`, `call f(x) -> K`, annotations `n: fx [0, ⟦v⟧-1]`; the primitives and block parameters are only in the spec | manual `bbv-language`, spec section 9.5, programs in `examples/07-basic-block-versioning/programs` |
| following the algorithm | a `code` block with `file="lattice:bbv/pseudocode/sbbv.txt" meta=algo follow=ID` | manual `bbv-instructions` |
| enlarging and reading versioning drawings | click a block; `clickable=off`, `clickable_show`; colours, borders, captions | manual `bbv-zoom`, `reading-the-drawing` |

### Presenting and output

| Feature | Where |
|---|---|
| Keys (Right, Left, Shift+Right skips, Down, Up, End, Home, `o`, `g`, `p`, `t`), rebinding with `keys:` | manual `presenting-keys`, spec section 7.6 |
| History: Left undoes, Up returns from an excursion | manual `history`, spec section 7.2 |
| URL `#/slide-id/step`, transitions | manual `navigation-details`, spec section 7.4 |
| Presenter view (`p`): notes, timer, scrubber, preview of the next step | manual `presenter-view`, spec section 7.5 |
| Single file or directory output | manual `output`, spec sections 11.1 and 11.4 |
| PDF export with an appendix of detours and branches | manual `pdf-export`, spec section 11.5 |

### Extending

| Feature | Where |
|---|---|
| A `lattice_plugins.py` next to the root file, or `plugins:` in the front matter | manual `plugins`, spec section 8.1 |
| A static component (`@register`, `Options`, `body = "text"` or `"yaml"`, `RenderResult`) | manual `checklist-demo`, spec sections 8.2 to 8.4, `user_manual/lattice_plugins.py` |
| An animated component with its own JavaScript runtime (`mount`, `show(inst, position, info)`) | manual `animated-component`, `call-stack-demo`, `runtime-contract`, spec section 10 |

Write a plugin only when no built-in component fits; most needs are met by a trace function for one of the animation components, or by a custom container plus CSS.

## Examples to copy from

| Folder | Shows |
|---|---|
| `examples/01-getting-started` | slides, fragments, code, a moving arrow, a detour that is a step (`at=1`), a link to an off-path slide, Graphviz |
| `examples/02-shortest-paths` | a multi-file deck (`parts/`, `shared/`), BFS and Dijkstra animations with code following, a timeline, a plot |
| `examples/03-sorting-workshop` | dark theme, branches that converge, array animations |
| `examples/04-custom-components` | two local plugins, one with its own runtime |
| `examples/05-refactoring-a-cache` | `code-morph` with an arrow that follows, `diff-steps`, an image, Vega and Plotly charts |
| `examples/06-trees-and-grids` | AVL rotations traced from real code, a maze, an LCS table, `pdf=` |
| `examples/07-basic-block-versioning` | abstract interpretation, SBBV with the source CFG following, the pseudo-code following, a branch on the version limit, Lambda Versioning |

## Rules that bite

These are the mistakes that build cleanly or produce a confusing error. Each one is a property of the design, so work with it rather than around it.

- **Only `#` makes a slide.** Content before the first `#` of a file or detour is LT002; a `#` inside a container is not a slide (LT041). Includes and detours sit at the top level of a slide (a detour cannot go in a column: place its badge there with `::detour-badge`). A detour's badge is never a reveal fragment: an attribute line before `::: detour` is ignored with warning LT065; use `badge=step` or `badge=next`.
- **Paths are relative to the file that names them**, not to the root file. A part in `parts/` that runs a trace in the deck's folder writes `source="../algos.py:fn"`.
- **Attribute lines go directly before their block**, with no blank line in between: `{.reveal}` then the list. Inside a list item, put it on the line after the item's text to reveal the nested list.
- **Attribute values are strings.** Lists and mappings go in the YAML body of a component (`panel: [queue]`, `show: [label, context]`), not in `{...}`. Giving the same option in both places is LT036.
- **Two stepping things need a timeline and ids.** Two independent tracks without a `timeline` is LT023; a stepping component without `#id` cannot be named (LT033). A timeline line moves only the tracks it names; the others hold their position. Read spec section 6.3 before writing a non-trivial timeline, and count the resulting steps.
- **Prefer named segments to line numbers.** `lines=`, `highlight=7-8`, `code-steps` ranges and selectors such as `.lt-line[data-line="3"]` silently point elsewhere when the file changes. Mark the code (`#|@name|# ... #|@end|#`) and use the name. Any comment holding only `@word` is read as a marker, so `markers=false` is how to display such text as written.
- **Point at a CFG by name, never by selector.** `cfg.B`, `cfg.A->L` and `cfg.L->B:false` (also `#t`, `#f`) are checked at build time (LT063); a selector into the drawing (`.lt-bbv-node[data-vid='4']`) uses an internal number and breaks silently when the program changes. `COMP.NAME` is a part only when `COMP` is a component id of the slide; `li.done` stays a CSS selector. In `bbv-anim` an arrow at a version is hidden while that version is not drawn, so check the steps where you expect it (LT046 flags a step where it can never appear).
- **One id per thing on a slide.** Element ids, component ids and segment names share a namespace per slide (LT058), and slide and detour ids are global across files (LT007).
- **Branch options converge only if told to.** A branch slide has no `next`, so the main path ends there (slides after it are reached only through the options). Give every option an explicit `next=` to the slide where they meet; an explicit `next` wins over every implicit rule, `offpath=true` included (spec section 5.2). Check with `lattice graph`.
- **Multi-line `code-morph` replacements keep indentation only from the start of a line.** A segment whose replacement spans several lines should start at the indentation of its own line; for one that starts mid-line, the further lines of the replacement are shown exactly as written in the YAML, with no indentation added (spec section 8.11). Only a screenshot shows this.
- **DOT keywords** (`graph`, `node`, `edge`, `digraph`, `subgraph`, `strict`) cannot be bare node names in `dot` blocks or `.dot` files.
- **Step numbers differ by audience:** the URL and `pdf=` count from 0, the HUD and the presenter view from 1.
- **Columns are meant to contain their content** (a table wider than its column scrolls inside it), so a column holding too much is a layout problem that only a screenshot shows. An animation narrower than 760 px puts its panel below the drawing (except `array-anim`) unless `panel_at=right`. Big animations need a `height=` or a column that makes room (`width` cues); check the screenshot.
- **Name the closing fences of long containers** (`::: /column`, `::: /detour`): a forgotten fence otherwise swallows the following slides, and the name turns that into error LT061 at the right line.
- **Heavy libraries are opt-in.** KaTeX is embedded only for math, Vega and Plotly only for those backends (Plotly adds about 4.4 MB); a single file over 50 MB is LT032 (use `--dir`).
- **Versioning drawings scale to fit their box.** Many versions per rank or `direction=LR` in a narrow column shrink node text until it is unreadable. Without `height=` a drawing shrinks to the room the slide leaves (up to 430 px), so a paragraph under it makes it smaller; with `height=` it keeps that size. Give the drawing room (a wider column, `height=`, a `width` cue), draw less (`show: [label, context]`, `functions:`, `wrap=`), or switch `direction`, then check the screenshot. Clicking a block enlarges it, but the audience should not need to.
- **The versioning models are faithful, not tuned for figures.** `bbv-anim` runs the real algorithm, so its output can differ in details from a hand-drawn thesis figure; adjust the program, the `limit` or the options rather than expecting a picture to match.
- **Writing style.** The project owner avoids em dashes in prose, slides included: use colons, commas or parentheses.

## When Lattice lacks something

Check the manual, spec section 8.8 and the roadmap (design report section 6) first: many requests are already an option. If the feature really is missing, do not hide a workaround in the deck (raw HTML spans, selectors into Pygments tokens, CSS offsets): it breaks on the next edit. Write the need down for the Lattice developers, with the slide that needs it, what today's syntax forces you to do and a sketch of the syntax you would want; the defense project keeps such requests in a `lattice_improvements.txt` at its root. Then use the least fragile workaround, or leave the slide simpler, and say so.

## A skeleton to start from

````markdown
---
title: My Talk
author: Me
tours:
  short: [intro, idea, thanks]
---

# My Talk {#intro layout=title}

# The idea {#idea}

{.reveal}
- A first point
- A second point, with a [[proof|proof in backup]]

::: detour {label="Background" key=b}
# Some background
The last slide of a detour returns to its origin.
:::

::: notes
Say this out loud.
:::

# Thanks {#thanks .center}

# Proof {#proof offpath=true}
Right returns to where the link was followed.
````

Then `lattice check talk.md --strict && lattice build talk.md`, and look at it.
