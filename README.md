# Lattice

Lattice compiles Markdown into **non-linear** slide decks: one self-contained HTML file per deck,
made for computer science talks. Slides form a graph with a main path, detours, branches and links,
and content blocks can be animated algorithm traces, plots, Graphviz diagrams or highlighted code.

This is version 0.8.0. This README covers usage in brief. The rest:

- [`user_manual/manual.md`](user_manual/manual.md) is the user manual, itself a Lattice deck (open
  [`user_manual/manual.html`](user_manual/manual.html)): every feature, with a live example of each.
- [`docs/spec.md`](docs/spec.md) defines the syntax, navigation, components and output exactly.
- [`docs/design-report.md`](docs/design-report.md) explains the design and holds the roadmap.
- [`docs/SKILL.md`](docs/SKILL.md) is the starting point for contributors.

## Install

```bash
pip install -e .              # core
pip install -e ".[plot]"      # + matplotlib for the plot component
pip install -e ".[pdf]"       # + playwright for PDF export (then: playwright install chromium)
pip install -e ".[dev]"       # + pytest, matplotlib, playwright
```

Python 3.10 or newer. The Graphviz `dot` program is needed for `dot` diagrams, `.dot` graph files
and the overview map; without it, animated graphs fall back to a NetworkX layout and the overview
shows only an outline.

## Quick start

```bash
lattice new my-talk                  # scaffold my-talk/talk.md
lattice serve my-talk/talk.md        # live preview at http://127.0.0.1:8000
lattice build my-talk/talk.md        # writes my-talk/talk.html
lattice build my-talk/talk.md --dir out   # index.html + assets/ + data/, to serve over HTTP
lattice check my-talk/talk.md        # diagnostics only (exit code 1 on errors)
lattice graph my-talk/talk.md        # print the slide graph (--dot for Graphviz)
lattice pdf my-talk/talk.md          # PDF of the main path, detours and branches as an appendix
```

The output HTML works offline from any folder: images, fonts for math, styles, scripts and data are
embedded. Libraries are only included when a deck uses them (KaTeX for math, Vega for
`backend=vega`, Plotly for `backend=plotly`, which adds about 4.4 MB).

## Authoring in one screen

````markdown
---
title: Shortest Paths
theme: default            # or dark
tours:
  short: [intro, dijkstra, end]
---

# Shortest Paths {#intro layout=title}

# Dijkstra's algorithm {#dijkstra}

{.reveal}
- Every `#` heading starts a slide; a bare `#` makes an untitled one
- `{.reveal}` shows list items one step at a time
- Link anywhere with [[proof]] or [[proof|a custom label]]

::: detour {label="Refresher: heaps" key=h}
# Binary heaps
The last slide of a detour returns to where you came from.
:::

::: branch
- [[in-python|Python]] the short version
- [[in-rust|Rust]] {key=2} the fast version
:::

::include{file="parts/backup.md" offpath=true}
````

| Syntax | Meaning |
|---|---|
| `# Title {#id .class next=id offpath=true layout=title}` | Slide boundary and attributes (`next` also accepts `back` and `none`) |
| `# Title {pdf="0,3,end"}` | Steps printed by `lattice pdf` for this slide (`first`, `last`, `all` or a list; numbered from 0) |
| `::include{file="x.md"}` | Splice the slides of another file here (also inside a detour) |
| `::: detour {#id label=... key=k at=2 blocking=true}` | Nested slides entered with Down or `k`, returning automatically; `at=2` makes it a step of the slide, entered after step 2, and `blocking` keeps skip keys from rolling over it (spec section 6.4) |
| `::: detour {at=2 badge=next}` | The badge of a detour step appears only when Right is about to enter it; `badge=step` keeps it from then on, `badge=false` hides it (spec section 3.9) |
| `::: branch` with a list of `[[target\|label]]` | A choice point, keys 1 to 9 by default |
| `::: notes` | Speaker notes, shown in presenter view |
| ` ```timeline ` with a line `detour id` (or `detour id blocking`) | A step that enters that detour, between the slide's other steps (spec section 6.4) |
| `::: columns` / `::: column {width=2fr}` | Layout (the outer fence needs more colons: `::::`) |
| `::: callout {kind=info\|tip\|warn}` | Highlighted box |
| `{.reveal}` on the line before a block | Fragment (list items reveal one by one) |
| `$...$`, `$$...$$` | Math, rendered with an embedded KaTeX |

The complete syntax, including slide attributes, layouts and ids, is in spec sections 2 and 3.

## Components

A fenced block whose info string names a component renders it; any other name is treated as a
code language.

| Block | What it does |
|---|---|
| ` ```python {highlight=2-3 title="x.py" linenos=true} ` | Highlighted code (any Pygments language) |
| ` ```code {lang=python file="algo.py" symbol=dijkstra} ` | Code from a file, a line range or a Python symbol; with `follow=trace` it highlights the lines named by an animation |
| ` ```code-steps {file=... lang=...} ` + `steps: [1-3, 5]` | Walk through code, one highlighted range per step |
| ` ```graph-anim {#trace source="algos.py:bfs" graph="city.dot"} ` | Animated graph from a `GraphTrace` built in Python |
| ` ```array-anim {source="sorts.py:bubble"} ` + `values: [...]` | Animated array from an `ArrayTrace` |
| ` ```tree-anim {source="avl.py:avl_trace"} ` + `values: [...]` | Animated tree from a `TreeTrace`: insertions, deletions and rotations, nodes glide to their new places |
| ` ```grid-anim {source="grids.py:lcs_trace"} ` | Animated grid from a `GridTrace`: mazes, dynamic programming tables with headers and arrows |
| ` ```bbv-anim {program="find.bbv" algorithm=sbbv limit=2} ` + `show: [label, context]` | Basic block versioning step by step: the specialized CFG of a small program grows, merges and settles (`algorithm=lv` for Lambda Versioning with entry and return points); `show` picks what the nodes draw (default: label, context and code), captions name the operation, the versions and the types of each step |
| ` ```bbv-cfg {program="find.bbv" follow=trace} ` | The source CFG of that program; following an animation, it highlights the block being specialized |
| ` ```abstract-interp-anim {program="sum-to-n.bbv"} ` + `history: [B.i]` | Abstract interpretation over the fixed CFG: contexts with types and intervals grow by union with widening and are narrowed at conditionals, until a fixed point; the panel can show the widening chain of a variable |
| ` ```plot {data="bench.csv" x=n y=ms group=algo logy=true} ` | Chart from a CSV with matplotlib (static SVG), or `backend=vega` / `backend=plotly` for interactive charts; also `source="file.py:fn"` or a raw `spec:` |
| ` ```diff-steps {lang=python context=3} ` + `versions: [...]` | Step through versions of a file; each step marks added and removed lines |
| ` ```dot ` | Graphviz diagram, themed |
| ` ```timeline ` | Orders the steps of several stepping elements on one slide |
| ` ```arrow {to=proof label="here" angle=315} ` | An arrow drawn over the slide, pointing at an element (an id or a CSS selector), from a direction or from another element (`from=`); with `steps:` it moves from one element to the next |

Animations are computed at build time. A trace function receives the graph (or values) and
keyword options from the block, and records frames as deltas:

```python
from lattice import GraphTrace

def bfs(g, start="A"):
    t = GraphTrace(g)
    t.frame(nodes={start: {"state": "frontier", "label": 0}}, caption="start", meta={"line": 3})
    ...
    return t
```

A `TreeTrace` reads your own node objects (`t.frame(root=root)` after each change), so an
implementation from a lab assignment can be traced as it is; see `examples/06-trees-and-grids`.

Basic block versioning runs at build time on a program written in a small CFG language:

```
function find(p, lst)
A:  if pair?(lst) goto B else goto L
L:  return #f
B:  if procedure?(p) goto D else goto E
...
```

One frame per step of the algorithm (versions queued, specialized, merged, made unreachable; for
Lambda Versioning also entry points, exit sites and return points), with automatic captions, a
panel and node contexts in the notation of the thesis figures; see `examples/07-basic-block-versioning`.
A `code` block can follow the animation through the program (`follow=trace`) or through the
bundled pseudo-code of the algorithm (`file="lattice:bbv/pseudocode/sbbv.txt" meta=algo`). The same
programs serve `abstract-interp-anim`, the classical analysis that SBBV extends: one context per
block, integer intervals widened at joins (`{0}`, `[0, 1]`, `[0, 2]`, `[0, 127]`, ...) and narrowed by
comparisons.
Every option of every component is listed in spec section 8.8; the trace classes and the states
the themes style are in spec section 9.1, and the program syntax in spec section 9.5.

## Navigation

| Key | Action |
|---|---|
| Right, Space | Next step, then next slide |
| Left | Undo the last move (history), or the previous slide when there is no history |
| Shift+Right, Shift+Left | Ten steps forward or back on the slide, played quickly |
| End | Last step of the slide |
| Shift+Down | Step over the next detour step without entering it |
| Down | Enter the slide's first detour |
| Up, Backspace | Return to where the current detour or jump started |
| 1 to 9, custom keys | Choose a branch option or detour |
| `o` / `g` | Overview (a map of the slide graph plus an outline) / go to a slide by name |
| `p` | Open the synchronized presenter view (notes, moves, all keybindings, timer, a preview of what comes next and a step scrubber) |
| `t` | Cycle through tours |
| Home | Back to the start, clearing history |

The URL keeps the position (`#/slide-id/step`), and a reload restores the history. Keys can be
changed with `keys:` in the front matter; the exact behavior of each move is spec section 7.

## PDF export

`lattice pdf talk.md` prints the main path, or a tour with `--tour NAME`, one page per slide at its
last step (`--steps first|all`, or a `pdf=` attribute per slide). Detours, branch options not taken
and linked backup slides follow as an appendix, and links between pages are clickable. It needs
`pip install -e ".[pdf]"` and `playwright install chromium`. Details: spec section 11.5.

## Writing your own components

Put a `lattice_plugins.py` next to the deck (it is imported automatically), or list installed
packages under `plugins:` in the front matter.

```python
from lattice import Component, RenderResult, register

@register("shout")
class Shout(Component):
    body = "text"
    def render(self, block, opts, ctx):
        return RenderResult(f"<p>{block.body.upper()}</p>")
```

An animated component returns `positions > 1` plus `data`, and names a JavaScript `runtime` that calls
`Lattice.component(name, {mount, show})`. See `examples/04-custom-components` and spec section 8.

## Examples

Each folder in [`examples/`](examples) holds a deck and its built `talk.html`:

1. `01-getting-started`: slides, fragments, code, math, an arrow that walks through the code, a detour
   that is also a step of its slide, links, an off-path slide, Graphviz.
2. `02-shortest-paths`: a multi-file lecture with BFS and Dijkstra animations, code following the
   animation, a timeline, a benchmark plot and a reusable detour included from `shared/`.
3. `03-sorting-workshop`: a dark-theme workshop where the audience picks an algorithm (branches that
   converge), array animations and a comparison plot computed at build time.
4. `04-custom-components`: two local plugins, a static truth table and an animated call stack with its
   own runtime.
5. `05-refactoring-a-cache`: `diff-steps` through three versions of an LRU cache, an embedded image,
   and the same benchmark as an interactive Vega-Lite chart and a Plotly bar chart.
6. `06-trees-and-grids`: AVL insertions with rotations traced from the lab's own code (followed by the
   code), a rotation in a detour, breadth-first search in a maze and a longest common subsequence
   table with backpointer arrows; `pdf=` picks the frames printed.
7. `07-basic-block-versioning`: abstract interpretation of `sum-to-n` (with the widening chain) and
   of `fact`, SBBV on `find` with the source CFG following along, one block at a time with the
   algorithm's pseudo-code following, a branch on the version limit, and Lambda Versioning on
   `power4`, on an operator written as a hyperfunction and on `fact`.

Rebuild them all, and the user manual, with `python scripts/build_examples.py`.

## Status

Version 0.8.0 implements everything in the spec; spec section 15 lists how it changed since the
first draft. Planned work is in the roadmap, design report section 6.

## Contributing

Start with [`docs/SKILL.md`](docs/SKILL.md): setup, project structure, tests, pitfalls, the release
steps and the rules for keeping these documents coherent.
