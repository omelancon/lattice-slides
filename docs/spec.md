# Lattice Specification

*Normative specification of Lattice, current as of v0.25.0 (changes since draft 1: section 15). The rationale is in `design-report.md`, user-facing usage in `../README.md` and the manual in `../user_manual/manual.md`, contributor workflow in `SKILL.md`. Where documents disagree, this one wins.*

---

## 0. Conventions

- **MUST**, **MUST NOT**, **SHOULD** and **MAY** are used as in RFC 2119.
- An **error** stops the build. A **warning** is reported and the build continues. Every diagnostic has a code (section 12) and a source location `file:line:col`.
- Grammars use EBNF: `{ x }` is zero or more, `[ x ]` is optional, `|` is alternation, `SP` is a space or tab, `NL` is a line ending.
- Identifiers in examples use `code font`.
- The document describes the **authoring format**, the **build pipeline** and the **runtime behavior**. Anything not described here is implementation-defined.

---

## 1. Terminology

| Term | Definition |
|---|---|
| **Root file** | The Markdown file passed to the CLI. It alone may contain front matter. |
| **Scope** | The container that owns a slide: either the root scope (`root`) or a detour, identified by the detour id. |
| **Origin** | The slide in whose body a detour is declared. |
| **Edge** | A directed relation between slides: `next`, `branch`, `detour` or `link`. |
| **Main path** | The chain of `next` edges followed from the start slide. |
| **Offpath slide** | A slide excluded from implicit `next` chains (backup material). |
| **Excursion** | A move that can later be undone as a whole with Return: entering a detour, following a link, go-to, overview click. |
| **Track** | Something on a slide that changes with steps: the reveal track or a component instance. |
| **Position** | The state index of a track. Position 0 is the state shown on arrival at step 0. |
| **Cue** | One slide step: an assignment of positions to tracks. |
| **Detour step** | A step that enters a detour when NEXT arrives on it (section 6.4). |
| **Follower** | A component instance whose position is always equal to another track's position. |
| **Frame store** | The serialized frames of an animation (section 9). |

---

## 2. Project and Files

### 2.1 Files

- Source files MUST be UTF-8. Line endings are normalized to `\n`.
- Relative paths in a file (includes, component options, images) are resolved against **the directory of the file containing them**, not the root file.
- A file `lattice_plugins.py` next to the root file, if present, is imported before rendering (section 8.1).
- The build cache lives in `.lattice-cache/` next to the root file.

### 2.2 Front matter

The root file MAY start with a YAML front matter block delimited by `---` lines. Included files MUST NOT have front matter (LT003).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `title` | string | root file stem | Deck title |
| `author`, `date` | string | none | Metadata, available to themes |
| `theme` | `default` or `dark` | `default` | Built-in theme; an unknown name falls back to `default` with warning LT052 |
| `aspect` | `16:9`, `16:10`, `4:3` | `16:9` | Slide aspect ratio |
| `start` | id | first root, non-offpath slide | Start slide |
| `plugins` | list of strings | `[]` | Plugin packages to activate (section 8.1) |
| `keys` | map action to key or list of keys | section 7.6 | Key binding overrides |
| `transitions` | map edge kind to transition name (`slide`, `zoom`, `fade`, `none`) | `next: slide`, `branch: slide`, `detour: zoom`, `link: fade` | Default transitions; moving backward plays the reverse (`slide` from the left, `zoom` out) |
| `tours` | map name to list of ids, or the string `main` | `{}` | Named tours (section 5.7) |
| `build.cache` | bool | `true` | Enable the render cache |
| `build.output` | `single`, `dir` | `single` | Output mode (section 11.4) |
| `build.frames.max_full_bytes` | int | `2097152` | Threshold for keyframed frame stores |
| `build.frames.keyframe_interval` | int | `16` | Keyframe spacing |

Unknown top-level keys produce warning LT040 and are otherwise ignored.

### 2.3 Includes

````markdown
::include{file="parts/dijkstra.md"}
::include{file="parts/backup.md" offpath=true}
````

- An include is a **leaf directive**: a line starting with `::include` followed by an attribute block (section 3.4). Attributes: `file` (required), `offpath` (bool, default `false`).
- An include MAY appear at the top level of any source file or at the top level of a detour container. It MUST NOT appear inside any other container, a list item or a block quote (LT034).
- An include acts as a slide boundary: it ends the current slide, and the included slides are spliced into the enclosing scope at that point, in order.
- The included file MUST start (after blank lines) with a slide heading or another include (LT002).
- `offpath=true` marks every slide of the included file (and of its nested includes) as offpath.
- Include cycles are an error (LT004). Including the same file twice anywhere in the deck is an error (LT005), since it would duplicate ids.

---

## 3. Authoring Syntax

### 3.1 Base Markdown

The base language is CommonMark plus GFM tables and strikethrough, and inline (`$...$`) and display (`$$...$$`) math. Lattice adds: heading attributes, attribute lines, wiki links, containers, leaf directives and component fenced blocks. Parsing is done with markdown-it-py; the grammar below is expressed over the resulting block structure, not raw characters.

### 3.2 Document grammar

```ebnf
document       = [ front_matter ] { top_item } ;
top_item       = slide | include ;
slide          = slide_heading { slide_block } ;
slide_heading  = "#" [ SP { SP } title ] [ SP { SP } attr_block ] { SP } NL ;
slide_block    = markdown_block | attr_line | container | detour
               | branch | fenced_block | detour_badge ;
detour         = ":::" { ":" } SP "detour" [ SP attr_block ] NL
                 { detour_item }
                 close_fence ;
detour_item    = slide | include ;
include        = "::include" attr_block NL ;
detour_badge   = "::detour-badge" attr_block NL ;   (* section 3.9 *)
container      = ":::" { ":" } SP NAME [ SP attr_block ] NL
                 { slide_block }
                 close_fence ;
close_fence    = ":::" { ":" } [ { SP } "/" { SP } NAME ] { SP } NL ;   (* bare, or naming the container *)
fenced_block   = FENCE NAME [ SP attr_block ] NL BODY FENCE ;
```

Notes:

- A `slide_heading` is recognized only at the top level of a file or at the top level of a detour container. Everywhere else, `#` headings are ordinary content and produce warning LT041 (a level-1 heading inside a container is almost always a mistake).
- Non-blank content before the first slide heading of a file (or of a detour) is an error (LT002).
- Setext level-1 headings (a line underlined with `=`) are an error (LT001).
- **Container fences.** A line of three or more colons followed by a name (and attributes) opens a container; a line of three or more colons alone closes the innermost open container. The number of colons carries no meaning: nested containers MAY all use `:::`, and an author MAY vary the counts for readability, in any order. To find where a container ends, the opening and closing fences that follow it are counted, skipping the lines of code blocks (fenced with backticks or tildes, also inside a list item or a block quote, or indented), so a fence quoted in code closes nothing.
- **Named closing fences.** A closing fence MAY name the container it closes, `::: /NAME`, with any number of colons. It closes the innermost open container like a bare fence, and that container's name MUST be `NAME`. Bare and named fences MAY be mixed in one file. A named fence that does not match its container, a malformed one (`::: /` with no name, or with attributes) and a closing fence with no open container are errors (LT061). A container still open at the end of the file or of its enclosing block (a list item, a block quote) is closed there, with warning LT062.
- `include` and `detour_badge` are **leaf directives**: alone on their line, with their attribute block required. A `detour_badge` is also recognized inside list items and block quotes; in the middle of a line the text is literal.

### 3.3 Slide headings and titles

| Heading | Result |
|---|---|
| `# Dijkstra's Algorithm` | Titled slide, auto id |
| `# Dijkstra's Algorithm {#dijkstra}` | Titled slide, explicit id |
| `#` | Untitled slide, auto id |
| `# {#overview .fullbleed}` | Untitled slide with attributes |

- The title is inline Markdown. Its HTML goes into the slide's `<h1>`; its plain text is used by the overview map and go-to search.
- An untitled slide renders no `<h1>`. Its plain-text title for the overview and go-to is its id.
- A trailing `{...}` is treated as an attribute block only if it is the last element of the heading line. If it looks like an attribute block but fails to parse, that is an error (LT009). Use `\{` for a literal brace.

### 3.4 Attribute blocks

```ebnf
attr_block = "{" { SP } [ attr { SP { SP } attr } ] { SP } "}" ;
attr       = "#" IDENT | "." CLASS | KEY "=" value ;
value      = BARE | '"' { any char except '"' | '\"' } '"'
                  | "'" { any char except "'" | "\'" } "'" ;
IDENT      = ALNUM { ALNUM | "-" | "_" } ;
CLASS      = ( ALPHA | "_" | "-" ) { ALNUM | "-" | "_" } ;
KEY        = ( ALPHA | "_" ) { ALNUM | "-" | "_" } ;
BARE       = 1*( any char except SP, "{", "}", '"', "'" ) ;
```

- At most one `#id` per block (LT009). Classes accumulate. A repeated key is an error (LT009).
- All values are strings at parse time. Typed consumers (slide attributes, component options) coerce them: `true`/`false` to bool, digits to int, and so on. A failed coercion is an error (LT021 for components, LT009 otherwise).
- **Attribute lines**: a line containing only an attribute block, placed directly before a block, applies to that block (markdown-it `attrs_block` behavior). When the line is directly followed by paragraph text (no blank line), it applies to the rest of that paragraph. This is how reveal fragments are declared (section 3.12).

### 3.5 Slide attributes

| Attribute | Type | Default | Meaning |
|---|---|---|---|
| `#id` | IDENT | generated (3.6) | Slide id |
| `.class` | CLASS | none | CSS classes on the slide element |
| `next` | IDENT, `back` or `none` | implicit (5.2) | Explicit next target |
| `offpath` | bool | `false` | Exclude from implicit next chains |
| `layout` | string | `default` | Adds the class `layout-NAME` to the slide; built-in layouts: `default`, `title` |
| `transition` | string | per edge kind | Transition used when entering this slide |
| `pdf` | `first`, `last`, `all` or a list like `0,3,end` | the export's default | Steps printed by the PDF export (section 11.5). Steps are numbered from 0, as in the URL; `end` is the last step. A malformed value, or a step beyond the slide's last, is error LT053 |

Any other key produces warning LT010 and is kept as a `data-*` attribute on the slide element for themes. The built-in themes also style the helper classes `.center` (centered body), `.fullbleed` (no padding) and `.small` (smaller body text).

### 3.6 Identifiers

- Slide ids and detour ids share **one global namespace** across all files. A wiki link can target either.
- Ids are case-sensitive and match `IDENT`.
- **Auto ids for titled slides**: take the plain-text title, apply Unicode NFKD, remove combining marks, remove apostrophes (`'` and `’`), lowercase, replace every run of characters outside `[a-z0-9]` with `-`, trim leading and trailing `-`. `Dijkstra's Algorithm` gives `dijkstras-algorithm`. If the result is empty, the untitled rule applies.
- **Auto ids for untitled slides**: `<file-stem>-<n>`, where `n` is the 1-based index of the slide within its source file.
- **Auto ids for detours**: `<origin-id>-detour-<n>`, where `n` is the 1-based index of the detour within the origin slide.
- Two explicit ids that collide are an error (LT007). An auto id that collides with any other id gets the smallest suffix `-2`, `-3`, ... that makes it unique, with warning LT008. Explicit ids are assigned first, then auto ids in document order.

### 3.7 Wiki links

```ebnf
wiki_link = "[[" IDENT [ "|" label ] "]]" ;
```

- `label` is inline Markdown. Default label: the target's plain-text title.
- Wiki links are recognized in slide bodies, titles and notes, but not in code spans or code blocks. `\[[` is literal.
- A link to a detour id targets the detour's entry slide.
- An unknown target is an error (LT011).
- Following a link is an excursion (section 7).

### 3.8 Containers

| Name | Purpose | Attributes |
|---|---|---|
| `detour` | Nested slides (3.9) | `#id`, `label`, `key`, `badge`, `at`, `blocking` |
| `branch` | Choice point (3.10) | `layout` (`menu` or `cards`) |
| `notes` | Speaker notes (3.14) | none |
| `columns` | Horizontal layout; direct children are `column` containers | `gap`, `duration` (milliseconds of a change of widths, default 600, below) |
| `column` | One column | `width`: a fraction of the free space (`2fr`, `1.5fr`), a CSS length (`px`, `em`, `rem`, `%`, `vw`, `vh`) or `0` (collapsed, below) |
| `callout` | Highlighted box | `kind` (`info`, `tip`, `warn`) |
| any other name | Rendered as `<div class="NAME">`, a styling hook for themes | any |

An unknown container name within edit distance 2 of a built-in name produces warning LT019 (likely typo).

Containers nest with fences of three colons; a bare `:::` closes the innermost one and `::: /NAME` closes it and checks its name (section 3.2):

````markdown
::: columns
::: column {width=2fr}
left
:::
::: column
::: callout {kind=tip}
right
:::
::: /column
::: /columns
````

Content never paints outside its column: a table wider than its column scrolls horizontally inside it.

**Widths that change.** A `width` cue of the timeline (section 3.15) gives named columns a new width from that step on, to make room for an animation in another column, say:

````markdown
::: columns
::: column {#src}
...
:::
::: column {#viz}
...
:::
:::

```timeline
width src=0      # src collapses: viz takes the whole row
ai ..end
width src=1fr    # src comes back
code 1
```
````

- Widths are positions (section 6.1): a step shows the widths of its row however it was reached. Step 0 shows the `width` attributes.
- A column of width `0` (or any zero length) is **collapsed**: it takes no width and takes away one gap of its `columns`, so the other columns fill the row as if it were not there. It is hidden and inert (no clicks, focus or links); its content keeps its layout and its components keep their positions, so it comes back as it would have been. An arrow at an element inside it is hidden (section 8.9). `width=0` on the column collapses it from step 0.
- **Motion.** A change of widths reached with a single step (NEXT, PREV) moves the columns for `duration` milliseconds (`0` changes them at once). The content of every column of that `columns` takes its final width at once, and the boxes of the columns move and clip it, so content reflows at most once per step: a growing column uncovers content already laid out at its final size, a shrinking one rewraps at the start. A collapsing column keeps its width and fades out; an opening one is laid out at its final width and fades in. A change that interrupts another, as during skip playback (section 7.2), takes 140 ms. Other moves (jumps, the scrubber, the preview, print, reduced motion) place the columns directly (section 10.1).
- Errors (LT064): a `width` attribute that is none of the values above, and a `duration` that is not a non-negative integer.

### 3.9 Detours

````markdown
::: detour {#heap-refresher label="Refresher: binary heaps" key=h}
# What is a binary heap?
...

# Heap operations
...
:::
````

- A detour container MUST appear at the top level of a slide body (LT034 inside another container). That slide is its **origin**.
- Its body MUST contain at least one slide (directly or through includes) (LT016).
- `label` defaults to the plain-text title of the entry slide. `badge` controls the badge rendered at the container's position in the origin slide: `true` (the default) shows it at every step, `false` renders none. Without a badge the detour is still reachable by key, Down, links and the overview.
- `badge=step` and `badge=next` tie the badge to the detour's detour step (section 6.4), for a detour that should not be announced before its turn. Let `k` be the step of its first detour step: with `step` the badge is hidden at the steps before `k - 1` and shown from step `k - 1` on; with `next` it is shown only at the step right before each of its detour steps, when NEXT would enter it. A hidden badge keeps its place (as a reveal fragment, section 10.4) and cannot be clicked; the key, Down, links and the overview still enter the detour. The footer hint for Down, which names the slide's first detour, is left out while every badge of that detour is hidden and waiting for its step. This is display only: the step table, `at` numbering and navigation are unchanged. Both values are an error (LT055) on a detour that is not a detour step of its origin.
- `at` (a step number, from 0) makes the detour a **detour step** of its origin, entered after that step (section 6.4). It MUST NOT be used on a slide that has a timeline, which declares detour steps itself (LT054). `blocking` (bool, default `false`) makes that detour step blocking: a multi-step move stops in front of it (section 7.2, SKIP).
- Detours MAY nest. A nested detour's origin is the detour slide that contains it.
- The container is removed from the origin's content; only the badge remains, at the container's position unless it is placed elsewhere (below).
- **Placed badges.** `::detour-badge{ref=ID}` renders a badge of the detour `ID` at its own position: in a column, a callout, a list item, a block quote or the top level of the body (not in a branch or in speaker notes). `ID` MUST be the explicit `#id` of a detour of the same slide (a nested detour's badges go in its origin, the detour slide that declares it). A detour MAY have several placed badges; once it has one, no badge is rendered at the container's position. Each placed badge inherits the detour's `label` and `badge` mode and MAY override them with its own `label=` and `badge=` (`true`, `step` or `next`); it MAY carry its own `#id` and classes, and an attribute line before it (at the top level or in a container) MAY add an `#id` and classes. The detour's `key`, `at` and `blocking` cannot be set on a badge: the key is shown on every badge, and the detour step belongs to the detour. Errors (LT056): a missing or unknown `ref`, a detour of another slide or without an explicit id, a detour with `badge=false`, another attribute, `badge=false` on the placed badge, an attribute line with a `reveal` class (the badge's visibility is its `badge` mode) or with key-value attributes, and a placed badge in speaker notes or in a branch. LT055 applies to the detour's own `badge` value and to each placed badge: a placed badge whose mode is `step` or `next` is an error at its own line when the detour has no detour step.

### 3.10 Branches

````markdown
::: branch
- [[impl-python|Python]] {key=1}
- [[impl-rust|Rust]] {key=2} fast and safe
- [[impl-c]]
:::
````

- The body MUST be exactly one bullet list. Each item MUST start with one wiki link, optionally followed by an attribute block (only `key` is allowed) and optional inline text shown as a description (LT017).
- Items without `key` get the lowest unused digit `1`..`9`, in order.
- A slide MUST NOT contain more than one branch (LT017).
- Branch targets MUST be in the same scope as the slide (LT013).

### 3.11 Keys on a slide

The keys of a slide's branch options and detours MUST be unique within that slide (LT018) and MUST NOT collide with a global binding (LT018).

### 3.12 Reveal fragments

````markdown
{.reveal}
- Greedy choice
- Priority queue
- No negative weights

{.reveal}
Final remark, revealed as one block.

{.reveal}
- Data structures
  {.reveal}
  - binary heap
  - Fibonacci heap
````

- An attribute line containing the class `reveal` marks the next block as revealable. If the block is a list, each top-level item is one fragment; otherwise the whole block is one fragment.
- Fragments are numbered 1, 2, 3, ... in document order across the slide (excluding detour content).
- An attribute line containing the class `reveal-with` puts the next block on the last fragment numbered so far, in document order, instead of opening a new one: it appears on the same step as that fragment. A list marked `reveal-with` joins as a whole. `reveal-with` before the first fragment of the slide, or together with `reveal` on one line, is an error (LT057); a placed detour badge is never a fragment (LT056, section 3.9).
- **Inside a list item**, a line holding only an attribute block, directly before a nested block of the same item, applies to that block: the line written after the item's text (which CommonMark reads as the last line of the item's paragraph, as in the example) or as a paragraph of its own; a line directly followed by text applies to the rest of that paragraph, as at the top level (section 3.4). A nested list marked `reveal` reveals one item per fragment, and the numbering stays in document order: an item is numbered before the items nested in it, and they before the next item. `reveal-with`, ids and classes apply as to any block. An attribute line in an item that is not directly followed by another block of that item stays text.
- All fragments of a slide form the single **reveal track** (section 6.1).

### 3.13 Fenced component blocks

````markdown
```graph-anim {#trace source="algos.py:dijkstra_trace" graph="data/city.dot"}
start: A
panel: [dist, queue]
```
````

The info string is `NAME [attr_block]`. `NAME` is resolved in this order:

1. `timeline`: the slide's timeline (section 3.15).
2. A registered component name (section 8).
3. A Pygments lexer alias: rendered by the built-in `code` component with `lang=NAME`.
4. Otherwise: plain preformatted text, with warning LT020. An empty info string gives plain text without a warning.

Because registered names win over lexers, components MUST NOT be registered under common language names; this is why the diff component is `diff-steps` and ` ```diff ` still highlights unified diffs.

Highlighting is Pygments' for every language, with one correction for `scheme`: the symbols that a binding form introduces are variables, not calls. The head of each binding of `let`, `let*`, `letrec`, `letrec*`, `do` and `fluid-let`, the formals of `let-values` and `let*-values`, and the parameters of `lambda`, `define-values` and `case-lambda` clauses are `Name.Variable`; the name of a named `let` is `Name.Function`, like the head of `(define (f ...))` and like its calls (`lattice.components.scheme`).

Code read by `code`, `code-steps`, `diff-steps` and `code-morph` (a file or the block's body) MAY contain **segment markers**, comments that name a stretch of code for arrows and highlights; they are removed from the displayed text (section 8.10).

Reserved attributes, handled by the core and not passed to component options: `#id`, classes, `follow`.

### 3.14 Speaker notes

A `notes` container's content goes to presenter view only. A slide MAY have several `notes` containers; they are concatenated in order. Wiki links in notes are clickable in presenter view and create link edges.

### 3.15 Timelines

At most one `timeline` block per slide (LT029). Its body is not YAML; it has its own line grammar:

```ebnf
timeline  = { line } ;
line      = { SP } ( cue | detour_cue | ) [ comment ] NL ;
cue       = part { { SP } "," { SP } part } ;
part      = assign | width_cue ;
width_cue = "width" SP { SP } column_width { SP { SP } column_width } ;   (* section 3.8; "width" is not a track name *)
column_width = IDENT "=" WIDTH ;    (* IDENT: the #id of a column; WIDTH: a value of the `width` attribute (3.8) *)
detour_cue = "detour" SP { SP } IDENT [ SP { SP } "blocking" ] ;   (* a detour step, section 6.4; "detour" is not a track name *)
assign    = TRACK SP { SP } ( position | range ) ;
position  = INT
          | ( "+" | "-" ) INT
          | end ;
end       = "end" [ { SP } "-" { SP } INT ] ;             (* end-N: N positions before the last *)
range     = ( INT | end ) { SP } ".." { SP } ( INT | end ) [ stride ]
          | ".." { SP } ( INT | end | ( "+" | "-" ) INT ) [ stride ] ;   (* open range: from the current position *)
stride    = SP { SP } "by" SP { SP } INT ;
TRACK     = IDENT ;          (* "reveal" or a component id on this slide *)
comment   = "#" { any char } ;
```

Example:

````markdown
```timeline
reveal 1            # first bullet
trace 1..4          # four cues, one frame each
code 2, trace 5     # both change on the same step
detour heap-refresher   # a detour step: entered on the way, section 6.4
trace ..end-1       # one cue per frame, from the current one to the one before the last
trace end
```
````

A `width` cue sets the width of each column it names (section 3.8) and leaves the other columns as they are. It is part of a cue like an assignment: alone on its line it is one step, and with other assignments the widths change on the same step (`width src=1fr, code 1`). Errors (LT064): a name that is not the `#id` of a column of this slide placed directly in a `columns` container (outside speaker notes), an invalid width, a column named twice in one cue, `width` without a column.

Positions are absolute (`3`), relative to the track's current position (`+1`, `-1`) or counted from the last one (`end`, `end-2`). A **range** gives one cue per position: `a..b` from `a` to `b`; an **open range** `..b` starts from where the track is, so `reveal ..end` reveals the remaining fragments one per step and `trace ..+2` plays the next two frames in two steps (where `trace +2` jumps them in one). `by K` keeps every `K`-th position of a range (`trace 1..end by 2`). Several ranges on one line advance in lockstep (`reveal ..+3, trace ..+3`). Semantics are defined in sections 6.3 and 6.4.

---

## 4. Deck Model

The build produces this model after parsing, include expansion, id assignment and graph resolution. Rendering then fills the track fields. Types are given as Python annotations; the implementation (`src/lattice/model.py`) uses dataclasses, and pydantic for the front matter. A slide body is kept as rendered HTML in which component blocks and the branch menu are placeholders, replaced once components are rendered and all titles are known.

```python
class SourceLoc:
    file: Path          # relative to the root file's directory
    line: int           # 1-based
    col: int            # 1-based

class Attrs:
    id: str | None
    classes: list[str]
    kv: dict[str, str]

# Next specification as written by the author, before resolution
NextSpec = Explicit(target: str) | Back | End | Implicit

class Slide:
    id: str
    title_html: str               # "" when untitled
    title_text: str               # plain text; the id when untitled
    untitled: bool
    classes: list[str]
    data: dict[str, str]          # unknown attributes, exposed as data-*
    scope: str                    # "root" or a detour id
    file_index: int               # 1-based index within its source file
    loc: SourceLoc
    next_spec: NextSpec
    offpath: bool
    layout: str
    transition: str | None
    pdf_steps: Literal["first", "last", "all"] | list[int | Literal["end"]] | None
    body_html: str                # rendered body with component placeholders
    components: list[ComponentBlock]
    reveal_count: int
    detours: list[str]            # detour ids, document order
    branch: Branch | None
    links: list[str]              # link targets (body, title, notes), deduplicated
    notes_html: str | None
    timeline: TimelineSpec | None
    # resolved (section 5)
    next: str | Literal["back"] | None
    # filled after rendering (section 6)
    tracks: list[Track]
    positions: list[list[int]]    # positions[step][track_index]
    step_detours: dict[int, dict] # detour steps: step -> {"id": detour id, "blocking": bool} (6.4)
    column_states: list[dict[str, str]]  # positions of the columns track: column id -> CSS flex value (3.8, 6.1)

class Detour:
    id: str
    origin: str
    label: str
    key: str | None
    badge: bool                   # false: no badge
    badge_mode: str | None        # "step" or "next": shown according to the detour step (3.9)
    badges: list[(str | None, SourceLoc)]  # rendered badges, default or placed, with their mode (3.9)
    at: int | None                # detour step after this step of the origin (6.4)
    blocking: bool                # a blocking detour step (6.4)
    slides: list[str]             # in document order; slides[0] is the entry
    loc: SourceLoc

class Branch:
    options: list[BranchOption]
    layout: Literal["menu", "cards"]

class BranchOption:
    target: str
    label_html: str
    description_html: str | None
    key: str

ComponentBlock(name: str, id: str | None, attrs: Attrs, body: str, loc: SourceLoc,
               follow: str | None)

class TimelineSpec:
    lines: list[TimelineLine]     # parsed cues with source locations; a line is a cue or a detour step (6.4)

class Track:
    id: str                       # "reveal" or component id
    kind: Literal["reveal", "component", "columns"]
    instance: str | None          # "<slide-id>/<component-id>"
    positions: int                # count, at least 1
    follow: str | None            # leader track id

class Edge:
    source: str
    target: str
    kind: Literal["next", "branch", "detour", "link"]
    key: str | None
    implicit: bool

class Deck:
    meta: FrontMatter
    slides: dict[str, Slide]      # insertion order = document order after includes
    detours: dict[str, Detour]
    edges: list[Edge]
    start: str
    main_path: list[str]
    tours: dict[str, list[str]]
    diagnostics: list[Diagnostic]
```

---

## 5. Graph Resolution

### 5.1 Scope sequences

For each scope `X`, `seq(X)` is the list of slides whose scope is `X`, in document order after include expansion.

### 5.2 Resolving `next`

For each slide `s`, `s.next` is computed as follows, in order:

1. `next_spec` is `Explicit(t)`: `t` MUST exist (LT012). If `s.scope` is a detour, `t` MUST have the same scope (LT013). If `t` is a detour id, it resolves to that detour's entry slide. Result: `t`.
2. `next_spec` is `Back`: result `back`.
3. `next_spec` is `End`: result `None`.
4. `next_spec` is `Implicit`:
   1. if `s.branch` is set: `None` (the presenter must choose);
   2. else if `s.offpath`: `back`;
   3. else the first slide after `s` in `seq(s.scope)` that is not offpath, if any;
   4. else `None` in the root scope, `back` in a detour scope.

`next=back` is legal in the root scope: it returns from whatever excursion brought the presenter there.

### 5.3 Edges

- One `next` edge per slide whose `next` is a slide id (`implicit` is true when rule 4 produced it).
- One `branch` edge per branch option, with its key.
- One `detour` edge from each origin to each of its detours' entry slides, with the detour key.
- One `link` edge per distinct `(source, target)` wiki link pair.

### 5.4 Start and main path

- `start` is the front matter `start` (resolved like a link target, LT012 if unknown), else the first root-scope slide that is not offpath. A deck with no such slide is an error (LT042).
- `main_path` starts at `start` and follows `next` while it is a slide id. Visiting a slide twice is an error (LT014).

### 5.5 Detour termination

For every detour, following `next` from its entry slide MUST reach `back` without revisiting a slide (LT035). With implicit edges this always holds; explicit `next` can break it.

### 5.6 Reachability

A breadth-first search from `start` over all edge kinds determines reachable slides. Each unreachable slide produces warning LT015. Offpath slides reachable only through links are fine.

### 5.7 Tours

- A tour is a list of ids. A detour id in the list expands to that detour's slides in `next` order. The value `main` means the computed main path.
- Unknown ids are an error (LT012). A slide MAY appear only once per tour (LT043).

---

## 6. Steps and Tracks

### 6.1 Tracks

A slide has these tracks, in this order:

1. The **reveal track** (`reveal`), if the slide has at least one fragment. With `m` fragments it has `m + 1` positions: position `k` shows fragments `1..k`.
2. One **component track** per component instance whose render result has `positions > 1` or that is a follower. Its id is the block's `#id`.
3. The **columns track** (`@columns`), if the timeline has a `width` cue (section 3.15). Its positions are the width states of the columns named in the slide's `width` cues: position 0 holds the widths of their attributes, and each `width` cue moves the track to the state it makes (a state equal to an earlier one takes that state's position). Timelines do not name it; `width` cues move it.

A track is **independent** if it is not a follower and has more than one position. The columns track is never the cause of LT023 or LT026.

### 6.2 Component ids and followers

- A component without `#id` receives the id `cN`, where `N` is its 1-based index among the slide's components. A component with more than one position MUST have an explicit `#id` when the slide needs a timeline (LT033), and a leader needs one so that `follow=` can name it.
- `follow=LEADER` makes a block a follower of track `LEADER` on the same slide (LT028 if unknown). Followers MAY be chained; cycles are an error (LT028). A follower MUST report the same number of positions as its leader (LT027).

### 6.3 Compiling steps

Let `I` be the independent tracks and `last(t) = positions(t) - 1`.

**Without a timeline:**

- `|I| = 0`: the slide has 1 step.
- `|I| = 1`, track `t`: equivalent to the timeline `t 1..end`.
- `|I| >= 2`: error LT023.

**With a timeline**, cues are compiled by this algorithm:

```python
pos = {t: 0 for t in I}
table = [dict(pos)]                              # step 0

for line in timeline.lines:
    for a in line.assigns:
        if a.track not in I: error("LT024")      # includes followers
    for cue in expand(line, pos):                # see below: LT025, LT030, LT031
        for a in cue:
            pos[a.track] = resolve(a, pos[a.track], last(a.track))
            if not 0 <= pos[a.track] <= last(a.track): error("LT025")
        if pos == table[-1]: warn("LT030")       # cue changes nothing
        table.append(dict(pos))

for t in I:
    if all(row[t] == 0 for row in table): warn("LT026")  # never advanced
```

- `width` cues (section 3.15) are assignments of the columns track: the state after the line is the state before it with the named columns changed. A cue whose widths are those already shown changes nothing (LT030), like any other.
- `resolve`: `INT` is absolute; `+N` and `-N` are relative to the current position; `end` is `last(t)` and `end-N` is `last(t) - N`.
- `expand`: a line without a range is one cue. A range on track `t` gives a sequence of values, and the line produces one cue per value (each cue assigns that value to `t`); the line's other assignments are applied in the first of these cues only. The values, with `K` the stride (`by K`, default 1, `K >= 1`):
  - **Range** `a..b` (`a` and `b` are integers, `end` or `end-N`): `a`, `a ± K`, ... in the direction from `a` to `b` (ascending or descending), ending with `b` even when `b` is not a multiple of `K` away from `a`. `a..a` is the single value `a`.
  - **Open range** `..b`: the same sequence started from the track's current position `c` (the position after the previous lines, which is known when the line is compiled), without `c` itself: `c ± K`, ..., `b`. The stop MAY be relative, `..+N` or `..-N`, meaning `c + N` or `c - N`; so `t ..+N` gives `N` cues where `t +N` gives one. If `b = c` the sequence is empty.
  - A relative stop after an explicit start (`2..+3`, ambiguous) and a stride of 0 are syntax errors (LT049).
  - **Lockstep.** A line MAY hold several ranges, on different tracks; they MUST produce the same number of values (LT031). Cue `i` assigns the `i`-th value of every range.
  - If every range of the line is empty (an open range whose track is already at its stop), the line produces warning LT030; it produces one cue holding its other assignments if it has any, and no cue (no step) otherwise.
  - A value outside `0..last(t)` is error LT025, reported once per line.

The number of steps is `len(table)`. Follower columns are then added by copying their leader's column. The final table is stored in `Slide.positions` with columns in track order.

### 6.4 Detour steps

A **detour step** is a step of a slide that, when reached with NEXT, enters one of the slide's detours. It lets an animation pause for a refresher and resume where it left off: RETURN (or the end of the detour) lands on the detour step, and the next NEXT performs the step that follows.

- A detour step is declared either by a timeline line `detour ID` (section 3.15), which appends one row to the table at that point, or by the attribute `at=N` on the detour container (section 3.9), which inserts one row after step `N` of the table compiled from the tracks (several `at` detours are inserted in increasing order of `N`, then document order; `N` counts the steps before any insertion). `ID` MUST be a detour of this slide and `N` MUST be an existing step, and `at` MUST NOT be combined with a timeline (all LT054).
- A detour step is **blocking** when its timeline line ends with `blocking` or its detour has `blocking=true`: a multi-step move (SKIP, section 7.2) stops in front of it instead of rolling over it. Only SKIP-DETOUR, an explicit key, steps over a blocking detour step without entering it.
- The row of a detour step is a copy of the row before it: nothing changes on the slide. It does not produce LT030.
- `Slide.step_detours` maps each such step to its detour id and whether it is blocking; the deck JSON carries it as `stepDetours` (section 11.2).
- The badge of a detour with `badge=step` or `badge=next` (section 3.9) is shown according to these steps; the runtime reads them from `stepDetours`. Like everything else on the slide, the badge depends only on the current step, however it was reached.
- Runtime consequences are in section 7.2 (NEXT, PREV), 7.5 (preview and moves) and 11.5 (the PDF export skips detour steps when printing `all`). Reaching a detour step by any means other than NEXT (PREV, the scrubber, the URL hash, a sync) does not enter the detour: steps are positions, not events.

---

## 7. Navigation Semantics

### 7.1 State

```text
cur   = (slide, step)                          current position
H     = [ Entry ]                              history stack, top = last element
Entry = (slide, step, kind)                    kind in { forward, excursion }
tour  = tour name or none
S(x)  = number of steps of slide x
```

Initial state: `cur = (start, 0)`, `H = []`, `tour = none` (subject to 7.4).

`push(k)` means: append `(cur.slide, cur.step, k)` to `H`. `go(x, i)` means: set `cur = (x, i)` and render.

`pred(x)`, the **structural predecessor** of a slide, is the first of: the slide before `x` in the active tour; the slide before `x` on the main path; a slide whose `next` is `x` (one in the same scope first, then document order); a slide with a branch option targeting `x`; the origin of the detour whose entry is `x`; else none. `detourstep(x, i)` is the detour of the detour step `i` of `x` (section 6.4), or none; it may be blocking.

### 7.2 Events

| Event | Guard | Effect |
|---|---|---|
| **NEXT** | `cur.step < S(cur.slide) - 1` | `cur.step += 1`; then, if `detourstep(cur.slide, cur.step)` is a detour `d`, **ENTER(d)** |
| | else, `tour` set, `cur.slide` in tour with a successor `u` | `push(forward)`, `go(u, 0)` |
| | else, `next(cur.slide)` is a slide `t` | `push(forward)`, `go(t, 0)` |
| | else, `next(cur.slide)` is `back` | **RETURN** |
| | else | no-op (end-of-path indicator) |
| **PREV** | `cur.step > 0` | `cur.step -= 1`, repeated while `cur.step > 0` and it is a detour step |
| | else, `H` not empty | `e = pop(H)`, `go(e.slide, e.step)` |
| | else, `pred(cur.slide)` is a slide `p` | `go(p, S(p) - 1)` without any push, so PREV keeps walking backward |
| | else | no-op |
| **SKIP(n)** (`skip-forward`: `n = 10`, `skip-back`: `n = -10`, `last-step` or three quick presses of `skip-forward` (section 7.6): to `S(cur.slide) - 1`, three quick presses of `skip-back`: to 0) | | `cur.step` moves by `n`, clamped to `0..S(cur.slide) - 1`, never leaving the slide and never touching `H`. The intermediate steps are played in rapid succession (single-step moves, so runtimes animate), and a new event cancels the playback. Detour steps passed on the way are not entered; a forward playback stops in front of a blocking detour step ("Cannot step detour") |
| **SKIP-DETOUR** | `detourstep(cur.slide, cur.step + 1)` is a detour step | `cur.step` moves past it and any detour steps directly following it (clamped to `S(cur.slide) - 1`), without entering them and without touching `H` |
| | else | no-op |
| **CHOOSE(k)** | `k` is a branch option key of `cur.slide`, target `t` | `push(forward)`, `go(t, 0)` |
| | `k` is a detour key of `cur.slide` | **ENTER(d)** |
| | else | no-op |
| **DOWN** | `cur.slide` has at least one detour | **ENTER(first detour)** |
| **ENTER(d)** | | `push(excursion)`, `go(entry(d), 0)` |
| **JUMP(t)** (link click, go-to, overview click, `api.goto`, manual edit of the URL hash) | `t != cur.slide` | `push(excursion)`, `go(t, 0)` |
| **RETURN** (Up, or `next = back`) | `H` contains an excursion entry | let `i` be the index of the topmost one, `e = H[i]`; `H = H[0:i]`; `go(e.slide, e.step)` |
| | else, `cur.slide` is in a detour `D` | structural fallback: `go(origin(D), S(origin(D)) - 1)` |
| | else | no-op |
| **HOME** | | `H = []`, `go(start, 0)` |
| **SET_TOUR(n)** | | `tour = n` (no move) |

Consequences, stated for clarity:

- Branch choices are forward moves: PREV after a choice returns to the branch slide.
- RETURN discards the excursion from history: PREV afterwards continues from what preceded the origin.
- Every forward move leaves a slide at its last step, so PREV into it restores that last step. Excursions store the step they were started from and restore it.
- The structural fallback only applies when history does not know the origin (after a reload with a deep link, or inside a tour). Likewise PREV falls back to `pred` only when `H` is empty (a deck opened on a deep link, or after HOME); since nothing is pushed, Right afterwards pushes a forward entry as usual and Left then pops it.
- A detour step entered through NEXT records the excursion at that step, so RETURN lands on it and the next NEXT performs the following step. PREV never lands on a detour step.

### 7.3 Worked trace

Deck: `intro` (1 step), `dijkstra` (3 steps, detour with `heap-what` then `heap-ops`), `complexity`.

| Event | `cur` | `H` |
|---|---|---|
| start | (intro, 0) | [] |
| NEXT | (dijkstra, 0) | [(intro,0,fwd)] |
| NEXT, NEXT | (dijkstra, 2) | [(intro,0,fwd)] |
| DOWN | (heap-what, 0) | [(intro,0,fwd), (dijkstra,2,exc)] |
| NEXT | (heap-ops, 0) | [..., (dijkstra,2,exc), (heap-what,0,fwd)] |
| NEXT (`next = back`) | (dijkstra, 2) | [(intro,0,fwd)] |
| PREV | (dijkstra, 1) | [(intro,0,fwd)] |
| NEXT, NEXT | (complexity, 0) | [(intro,0,fwd), (dijkstra,2,fwd)] |

### 7.4 URL and persistence

- The URL hash is `#/<slide-id>/<step>`, updated on every move with `history.replaceState` (browser history is not used for navigation).
- `H` and `tour` are saved in `sessionStorage` under `lattice:<deck-hash>:nav` after every event.
- On load: if the hash names a valid position and the saved state's `cur` equals it, the saved `H` and `tour` are restored. Otherwise `cur` comes from the hash (or `start`), and `H = []`.
- A step beyond `S - 1` in the hash is clamped.

### 7.5 Presenter view

- Opening the deck with `?presenter` (key `p` opens it in a new window) shows the current slide beside a panel with a timer (click to reset), the slide and step, a scrubber, a preview of what comes next, the available moves (what NEXT does, branch options, detours and the return target, each with its key), a **Keybindings** section listing every global action of section 7.6 with its keys (as bound by the deck, in smaller type than the moves, plus the three quick presses of the skip keys, the digit keys of branch options and detours, and the click that enlarges an element when the deck has components that offer it, section 7.7) and the notes.
- The **scrubber** is a slider over the steps of the current slide, shown when the slide has more than one step. Moving it sets `cur.step` directly: it is not an event of section 7.2 and leaves `H` unchanged, and runtimes receive `animate: false` (section 10.1).
- The **preview** shows what NEXT would show: the next step of the current slide (the entry slide of the detour when that step is a detour step, which the moves list names as "detour: label", marked "(blocking)" when it is, followed by the `skip-detour` key); at the last step, the slide NEXT moves to (tour successor, `next` slide at step 0, or the return target at the step it restores). At a branch point or at the end of the path it shows a label instead. The preview is a second copy of the document opened with `?preview`: a passive window that ignores keys and clicks, keeps no history or storage, does not join the `BroadcastChannel`, never animates, and renders the position the presenter window sends it with `postMessage`.
- Audience and presenter windows share state over a `BroadcastChannel` named `lattice:<deck-hash>`. After every event, the window that handled it broadcasts `{cur, H, tour}`; the other window adopts it without re-running the event. Either window may drive. An enlarged element (section 7.7) is shared the same way: opening one broadcasts `{zoom: {instance, key}}` and closing one `{zoom: null}`, and the other window opens or closes its own copy.

### 7.6 Default bindings

| Action | Keys |
|---|---|
| `next` | `ArrowRight`, `Space`, `PageDown` |
| `prev` | `ArrowLeft`, `PageUp` |
| `skip-forward` | `Shift+ArrowRight` |
| `skip-back` | `Shift+ArrowLeft` |
| `last-step` | `End` |
| `skip-detour` | `Shift+ArrowDown` |
| `enter-detour` | `ArrowDown` |
| `return` | `ArrowUp`, `Backspace` |
| `choose` | digits `1`..`9` and custom keys from the slide |
| `overview` | `o` |
| `goto` | `g` |
| `presenter` | `p` |
| `tour` | `t` |
| `home` | `Home` |

**Three quick presses.** The third press of a `skip-forward` key within one second of the first (presses of that action only) performs SKIP to the last step instead of ten steps, like `last-step`; three presses of `skip-back` likewise perform SKIP to step 0. A later press still inside the window does the same, so a fourth quick press keeps the playback going rather than cutting it short. The auto-repeat of a held key (`KeyboardEvent.repeat`) does not count as a press, and any other action, or a slide key, starts the count again. The count follows the action, so it applies to whatever keys the deck binds to it.

Bindings are overridable in front matter under `keys`. A key is a `KeyboardEvent.key` value, optionally prefixed with `Shift+`; with Shift held, the `Shift+` binding is tried first, then the plain key (letters already arrive shifted, so `A` binds Shift+a). Slide-level keys (branch options and detours) never override global bindings: a collision is an error (LT018).


### 7.7 Enlarged elements

A component MAY let the viewer enlarge one of its elements (a basic block of the versioning drawings, section 9.5): a click asks the core to show a copy of the element in a **card** over the slide (`api.zoom`, section 10.3).

- **Layout.** The card keeps the aspect ratio of the element's natural size and fits in 80% of the slide's width and height, whichever limits first, magnifying the element's own units at most 4.5 times; it is centred on the slide as shown, which in presenter view is the slide pane (the panel stays uncovered). The slide and the HUD are blurred and dimmed behind it. The card grows out of the element's place on the slide and shrinks back into it when it closes, unless the viewer prefers reduced motion.
- **Input.** While a card is open, any key closes it and performs no action, except a bare modifier (`Shift`, `Control`, `Alt`, `Meta`) and a combination with `Ctrl`, `Meta` or `Alt`, which are left to the browser. A press of the pointer outside the card closes it and does nothing else (no link, badge, branch option, timer reset or scrubber move); a click inside the card does nothing.
- **Not a position.** Opening or closing a card is not an event of section 7.2: `cur`, `H` and `tour` do not change, the URL hash and `sessionStorage` are not written, and a reload never reopens a card. Any render of a position (a sync from the other window, a change of the URL hash, the scrubber) closes it at once. After it closes, keys and clicks act as before it opened.
- **Windows.** The presenter and audience windows show the same card (section 7.5). Passive windows (the preview and print mode) never open one.

---

## 8. Component Contract (Python)

### 8.1 Registration and plugin loading

- Components are classes registered with `@lattice.register(name)`.
- Installed packages expose plugins through the entry point group `lattice.plugins`. A plugin is **activated** only if listed in the front matter `plugins`, which keeps builds deterministic.
- Built-in components are always active. `lattice_plugins.py` next to the root file is always imported. Python code referenced by a deck is trusted and executed without confirmation.
- Registering a name twice is an error (LT044), including a plugin shadowing a built-in. Re-importing the same class (for example after a live reload) is not a conflict.

### 8.2 Component class

```python
class Component:
    name: ClassVar[str]
    version: ClassVar[str] = "1"                 # part of the cache key
    Options: ClassVar[type[BaseModel]] = NoOptions
    body: ClassVar[Literal["yaml", "text", "none"]] = "yaml"
    runtime: ClassVar[str | None] = None         # file in lattice/runtime/components, or an absolute path
    css: ClassVar[list[str]] = []                # same resolution as runtime
    requires: ClassVar[list[str]] = []          # shared libraries for every instance: "plotly", "vega", "katex"

    def render(self, block: ComponentBlock, opts: BaseModel,
               ctx: RenderContext) -> RenderResult: ...
```

Option construction:

- `body = "yaml"`: the body MUST be empty or a YAML mapping (LT021). Its keys are merged with the non-reserved attributes; a key present in both is an error (LT036). The merge is validated with `Options`.
- `body = "text"`: attributes alone are validated with `Options`; the raw body is in `block.body`.
- `body = "none"`: a non-empty body is an error (LT021).
- An `Options` model declaring `extra="allow"` accepts unknown options; `graph-anim` and `array-anim` pass them to the trace function as keyword arguments, reading attribute values as YAML scalars (`push=1` gives the integer 1).

### 8.3 RenderContext

| Member | Description |
|---|---|
| `meta` | Front matter |
| `slide_id`, `instance_id` | `instance_id` is `<slide-id>/<component-id or cN>` |
| `root_dir`, `file_dir` | Root directory and directory of the file containing the block |
| `path(p) -> Path` | Resolve `p` against `file_dir` and register it as a dependency (LT045 if missing, raised as `MissingFileError`) |
| `depends(p)` | Register an extra dependency for caching |
| `call(ref, **kwargs)` | `ref` is `"file.py:function"`: import the file (relative to `file_dir`), call the function, register the file as a dependency |
| `load_graph(p)` | Load `.dot`, `.gml` or `.json` (node-link) into a NetworkX graph |
| `layout(graph, engine="auto")` | Stable positions for nodes and edge routes, in points. `auto` is Graphviz `dot` with `rankdir=LR` (wide layouts suit slides); without Graphviz, a seeded NetworkX spring layout |
| `palette` | Theme colors for build-time rendering: `ink`, `muted`, `accent`, `grid` and a `series` list |
| `seed` | Integer derived from `instance_id`, for deterministic randomness |
| `leader` | The leader's `RenderResult` for a follower, else `None` |
| `frames_config` | `max_full_bytes`, `keyframe_interval` |
| `warn(msg, code="LT046")` | Emit a warning at the block's location: LT046, or the code a built-in component passes (LT059, LT060). Warnings emitted this way are reported again when the result comes from the cache (section 8.6) |

### 8.4 RenderResult

```python
@dataclass
class RenderResult:
    html: str                          # placed at the block's position
    data: Any = None                   # JSON-serializable, delivered to the runtime
    positions: int = 1                 # 1 means static
    meta: list[dict] | None = None     # per-position metadata, build time only
    assets: list[Asset] = field(default_factory=list)   # extra files to embed
    requires: list[str] = field(default_factory=list)   # shared libraries for this instance only
    anchors: list[str] = field(default_factory=list)    # element ids defined for authors (8.10)
```

- `positions` MUST be at least 1. `meta`, if present, MUST have length `positions` (LT047).
- A component with `positions > 1` MUST declare a `runtime` (LT047), since only the runtime can change what is shown.
- `requires` adds shared libraries for this instance only (a `plot` needs Vega only with `backend=vega`). Libraries are embedded only in decks that use them.
- `anchors` lists the element ids of `html` that the author names (the segments of a `code` block, or of every position of a `code-morph`, sections 8.10 and 8.11). They take part in the check of ids on a slide (LT058, section 8.10); other ids inside a component's HTML (those of a matplotlib SVG, say) do not.

### 8.5 Render order

- Within a slide, leaders render before their followers (topological order).
- Slides render independently; the implementation MAY render them in parallel processes. `render` MUST be a pure function of its inputs (options, body, dependencies, leader result).

### 8.6 Caching

The cache key is the SHA-256 of: the Lattice version and a hash of its Python sources, the component's name, version and module, canonical JSON of the options, the body, the block's directory, the leader's cache key and the theme palette; a cached entry is used only if the content hash of every registered dependency is unchanged. A cached entry keeps the render result (`html`, `data`, `positions`, `meta`, `requires`, `anchors`) and the warnings the render emitted through `ctx.warn`, which are reported again when the entry is used. Only files registered through `path`, `depends` and `call` are tracked; modules imported indirectly by a called file are not. `lattice build --no-cache` bypasses the cache.

### 8.7 Errors

A `ComponentError` raised by `render` becomes error LT022 at the block's location (LT045 for `MissingFileError`). Any other exception also becomes LT022, with the last frames of the traceback in the message.

### 8.8 Built-in components

| Name | Body | Positions | Main options |
|---|---|---|---|
| `code` | text | 1, or leader's count when following | `lang`, `file` (a file of the deck, or `lattice:PATH` for a file bundled with Lattice, such as `lattice:bbv/pseudocode/sbbv.txt`), `lines`, `symbol`, `highlight` (line ranges and segment names, section 8.10), `title`, `linenos`, `line_base` (`snippet` or `file`: how highlighted line numbers are counted), `markers` (default `true`: read segment markers; `false` shows the text as written); as a follower, highlights `meta[i]["lines"]` or `meta[i]["line"]`, or `meta[i][KEY]` with `meta=KEY` (line numbers, ranges or segment names) |
| `code-steps` | yaml | `len(steps) + 1` | same as `code` (`file` required); body `steps:` one entry per step, a line range, a segment name, or a list or comma-separated string of them |
| `diff-steps` | yaml | number of versions | `lang`, `context` (lines around changes), `title`, `markers` (default `true`: segment markers are removed; a diff defines no segments); body `versions:` file paths, or mappings with `file` or `code` and an optional `label` (`highlight` in a version is LT022: a diff does not highlight) |
| `plot` | yaml | 1 | `backend` (`matplotlib`: static SVG; `vega`: Vega-Lite compiled in the browser; `plotly`), `source`, `spec` (raw Vega-Lite spec or Plotly figure), `data` (CSV), shorthand `kind`, `x`, `y`, `group`, `xlabel`, `ylabel`, `title`, `logx`, `logy`, `width`, `height` (inches, 96 px per inch for vega and plotly), `legend`. Theme colors and fonts are merged into the spec's `config` or `layout`; values given by the author win |
| `dot` | text | 1 | `engine` |
| `graph-anim` | yaml | number of frames | `source`, `graph` or `edges` (inline `"u v weight"` lines), `directed`, `engine`, `rankdir`, `panel`, `edge_labels`, `height`; `panel_at` (see below the table); other keys are passed to the trace function |
| `array-anim` | yaml | number of frames | `source`, `values`, `panel`; `panel_at` (see below the table); other keys are passed to the trace function |
| `tree-anim` | yaml | number of frames | `source` (returns a `TreeTrace`), `values` (passed as the first argument), `layout` (`auto`, `binary`, `tidy`; `auto` is `binary` when every node has zero or two child slots), `panel`, `height`; `panel_at` (see below the table); other keys are passed to the trace function |
| `grid-anim` | yaml | number of frames | `source` (returns a `GridTrace`), `values` (passed as the first argument), `cell` (cell size in drawing units, default 48, relative to the text), `panel`, `height`; `panel_at` (see below the table); other keys are passed to the trace function |
| `bbv-anim` | yaml | number of frames | `program` (a `.bbv` file, or `file.py:function` returning a `Program` or its text) or `source` (the program text), `algorithm` (`sbbv` or `lv`), `limit` (default 2), `limits` (per function, `none` for no limit), `heuristic` (`similarity`, `arithmetic`, `random`), `entry` (the function traversed first; default the first one), `functions` (drawn, in that order; hidden functions are analysed but not drawn), `events` (kinds kept as frames), `granularity` (`block`, or `instruction` for one frame per specialized instruction), `until` (stop after that many frames), `show` (node contents among `label`, `context`, `code`; default all three), `colors` (`origin` or `none`), `direction` (`TB` or `LR`), `wrap` (versions per line of a rank before it wraps, default 4), `call_edges`, `panel` (keys among `queue`, `versions`, `checks`, `merges`, `limit`), `caption` (`auto` or `none`), `prims` (extra primitives), `height`, `clickable`, `clickable_show` (section 9.5), `max_steps`, `intervals` (track integer intervals and vector lengths, default `false`), `thresholds` (widening thresholds of the merges, as `abstract-interp-anim`), `fixnum_bits` (default 61), `vector_bounds` (default `true`; `false` drops the symbolic vector bounds, section 9.5); `panel_at` (see below the table); other keys are passed to the program function (section 9.5) |
| `bbv-cfg` | yaml | 1, or leader's count when following | `program` or `source`, `functions`, `show` (default `label` and `code`), `colors`, `direction`, `prims`, `height`, `clickable`, `clickable_show`; as a follower of a `bbv-anim`, highlights the block named by `meta[i]["block"]` |
| `abstract-interp-anim` | yaml | number of frames | `program` or `source`, `entry` (the function analysed; default the first), `thresholds` (`machine`, `sign`, `none`, or a list of integers and names, section 9.6), `narrowing` (default `true`), `fixnum_bits` (default 61), `vector_bounds` (default `true`, section 9.5), `events` (among `start`, `dequeue`, `instruction`, `propagate`, `done`), `granularity` (`block` or `instruction`), `until`, `history` (`BLOCK.VAR` entries whose chain of entry values the panel shows), `panel` (keys among `worklist`, `iterations`, `history`), `panel_at` (see below the table), `show`, `colors`, `direction`, `wrap`, `caption`, `prims`, `height`, `clickable`, `clickable_show`, `max_steps` (section 9.6) |
| `math` | text | 1 | display math block |
| `arrow` | yaml | 1, or `len(steps)` | `to` (an element id, an item of a list as `LIST[N]`, or a CSS selector, resolved inside the slide), `from` (another element), `angle` (degrees), `length` (default 120), `label`, `color` (a CSS color or a theme token: `accent`, `detour`, `muted`, `ink`), `width` (default 4), `curve` (bend as a fraction of the length, default 0), `from_anchor` and `to_anchor` (`left`, `right`, `top`, `bottom`, `center`, `bullet` (the marker of a list item) or an angle in degrees); body `steps:` a list of targets (a string, or a mapping with the same `to`, `from`, `angle`, `length`, `label`, `from_anchor`, `to_anchor` keys, defaulting to the block's options; `from: ""` drops the block's `from`; or `null`, no arrow), one position each (section 8.9) |
| `code-morph` | yaml | number of versions, or `len(steps) + 1` | `lang`, `title`, `markers`, `linenos`, `duration` (ms, default 600), `room` (`max` or `fit`), `mark` (default `false`), `highlight` (line numbers, segment names or `changed`, the default of every position); body either `versions:` (as `diff-steps`, and a version MAY set its own `lang` and `highlight`) or `file` with `steps:` (replacement texts of named segments, cumulative, and a `highlight` per step), with `lines`, `symbol` and `label`; the text of the block changes between positions and unchanged tokens glide (section 8.11) |

**Panel placement.** The variable panel of `graph-anim`, `array-anim`, `tree-anim`, `grid-anim`, `bbv-anim` and `abstract-interp-anim` sits where `panel_at` says: `auto` (the default) beside the drawing, and under it when the component is narrower than 760 px (`array-anim` keeps it beside); `right` beside the drawing at any width; `below` under it at any width. Under the drawing, the panel's entries are laid out in a row that wraps, and the drawing keeps its `height` (section 9.5). Another value is LT021.

The exact option schemas are the pydantic `Options` models in `src/lattice/components/`.

A `code` or `code-steps` block taller than its space scrolls. At each position that highlights something, the first highlighted line (or line holding a highlighted segment) is scrolled a third of the way down the block, smoothly on a single-step move and at once otherwise (`code-morph` does the same with its first changed row, section 8.11).

### 8.9 The `arrow` component

An `arrow` draws an arrow over the current slide, pointing at one of its elements. It is the one component whose geometry is computed in the browser, because element boxes exist only there; the build still decides everything else (targets, directions, steps).

- **Targets.** `to` and `from` name an element of the slide: a bare identifier is an element id (an `{#id}` attribute line, a component `#id`, a code segment of section 8.10, or any id in the rendered body), an identifier followed by indices in brackets is an item of a list (below), anything else is a CSS selector such as `.lt-line[data-line="4"]` or `.lt-title`, resolved inside the slide section. A bare id that no element of the slide carries, and that is not an anchor of one of its components (a segment of a later position of a `code-morph`, say), is warning LT046 at build time; a target not found at runtime hides the arrow (console warning), and so does a target inside a collapsed column (section 3.8), without a warning. The box of a target is the extent of its contents when it has some (so a heading or a code line is pointed at its text, not at its full row), else the element's box; the box of a code segment is the union of its pieces, one per line it spans. The box of a list item (`<li>`) is that of its own content, without the lists nested in it, so an arrow at an item with sub-items points at the item's own lines.
- **List items.** `LIST[N]` names the `N`-th item of the list whose id is `LIST` (an `{#id}` attribute line before a bullet or ordered list puts the id on the list), counted from 1 in document order, whatever numbers an ordered list displays; a negative `N` counts from the end (`[-1]` is the last item). Further indices descend into the first list nested in that item: `facts[2][1]` is the first item of the list nested in item 2 of `facts`. The grammar is `IDENT "[" ["-"] DIGITS "]" { "[" ["-"] DIGITS "]" }`, which is not a CSS selector, so no working selector changes meaning (in a YAML flow sequence, `[a, b]`, the value needs quotes). An index of 0 is LT022. At build time, an item that does not exist is error LT063: no element with that id on the slide, an element that is not a `<ul>` or `<ol>`, an index beyond the number of items, or an item with no nested list to descend into.
- **Anchors.** `from_anchor` and `to_anchor` choose where the arrow leaves `from` and enters `to`. A side is an angle: `right` is 0, `top` 90, `left` 180, `bottom` 270, and a number is an angle in degrees with the convention of `angle` (counterclockwise, 0 pointing right). The end sits where the ray from the center of the box at that angle leaves the box (for a side, the middle of that side), a small gap outside it, and the curve leaves or enters along that ray. `center` puts the end at the center of the box, with no gap. `bullet` puts the end at the marker of a list item (its bullet, or its number in an ordered list): a small gap to the left of the marker, at its vertical middle, and the curve leaves or enters to the left, as with `left` (without `from`, `to_anchor=bullet` gives `angle` 180). The end MUST be a list item, written `LIST[N]` or the bare id of an `<li>`; a bare id of a whole list, any other element and a CSS selector (which the build cannot check) are error LT063. A step whose `from_anchor` is set has a `from` (LT022); the block's `from_anchor` applies to the steps that have one.
- **Direction.** With `from`, an end without an anchor (or with `center`) aims at the other end: at its anchor point, or at the center of its box. With no anchor at all, the arrow runs from the edge of the `from` box to the edge of the `to` box along the line between their centers, shortened by a small gap at both ends. Without `from`, the arrow comes from `angle`: degrees measured from the target toward the tail, counterclockwise with 0 pointing right (90 means the arrow comes from above, 315 from the lower right); its head sits at the target's edge along that direction, or at `to_anchor` when it is set, and its tail `length` slide pixels from the head's edge point along `angle`, shortened when it would leave the slide. `angle` defaults to the direction of `to_anchor` when it is an angle, a side or `bullet` (180), else to 315, a fixed direction chosen over any direction computed at runtime (report, decision 14).
- **Markers.** The marker of a list item has no box of its own in the page, so the runtime measures it: with the item's `list-style-position` set to `inside` for the time of one measurement, the first character of the item moves right by the width of the marker, and the marker ends where the item's content starts. This is exact for a marker made of text, in Chromium and Firefox. The built-in stylesheet therefore gives bullet lists text markers, `•` at the first level, `◦` at the second and `▪` below (`list-style-type` strings followed by an en space, in the accent colour), and ordered lists keep their numbers; a theme or plugin MAY set other markers, and a list whose marker is one the browser draws as a shape (`disc`, `circle`, `square`) is measured approximately. A list with no marker (`list-style: none`) puts a `bullet` end at the left of the item's first line.
- **Appearance.** A cubic curve from tail to head. An end with an angle anchor has a handle along its ray, a free end a handle along the chord, so with no anchor the curve is the quadratic of earlier versions; `curve` bends it sideways by `curve` times its length (0 is straight; negative bends the other way). An arrowhead at `to` follows the curve's direction there; the `label` is at the tail (or beside the middle of the curve with `from`), kept inside the slide. `color` defaults to the theme accent.
- **Steps.** With `steps:` the block has one position per entry and is a track (section 6.1): position `i` points at entry `i`. On a single-step move the arrow glides from its previous geometry (`info.animate`, section 10.1); any other move places it directly. An entry `null` is a position without an arrow, so an arrow can appear after the first position and disappear before the last; the next arrow shown is placed directly rather than gliding. At least one entry MUST be a target (LT022).
- **Placement.** The runtime moves the block's wrapper out of the body to the slide section as an overlay covering the whole slide, above the content and ignoring pointer events, so the block's position in the Markdown does not matter and it takes no space. A `{.reveal}` attribute line before the block hides it until its fragment is shown, as for any block. The arrow is re-measured when the slide is entered, on every step, when the window is resized, when the slide body changes size and when a component of the slide announces that its content moved (the `lt-relayout` event, section 10.4); it glides to the new geometry when that move is animated. The presenter preview and the PDF export draw it like any component.

### 8.10 Named segments in code

A **segment** names a stretch of code shown by `code`, `code-steps` or `code-morph` (section 8.11), so that an arrow can say `to: i-init` and a highlight `i-init` instead of a line number and a token position. Segments are written in the source itself, in comments, so the file stays the single source of truth and keeps running.

````text
(let loop (#|@i-init|# (i 0) #|@end|#        ; inline form, block comments
           (acc 0))
  ...)

# @loop                                      # whole-line form, line comments
while lo < hi:
    ...
# @end
````

- **Markers.** A marker is a comment holding only `@NAME` (opens a segment named `NAME`, an `IDENT` of section 3.4) or `@end` (closes the innermost open segment; `@end NAME` also checks its name), with optional spaces inside the comment. The **inline form** uses a block comment, `#| |#`, `/* */`, `(* *)`, `{- -}` or `<!-- -->`, whatever the language, and may sit anywhere in a line. The **whole-line form** is a line holding only a line comment, `#`, `;`, `//`, `--` or `%`, followed by the marker; it is for languages without block comments (Python, shell, `.bbv` programs). Markers are recognized anywhere in the text, string literals included. Segments MAY span lines and MAY nest.
- **Removal.** Markers are removed from the displayed code. An opening marker takes the spaces and tabs after it, a closing marker those before it unless they are the indentation of its line, so `(#|@i-init|# (i 0) #|@end|#)` displays as `((i 0))`. Spaces left at the end of a line by a removed marker are removed, and a line left blank (a whole-line marker, or a line of inline markers only) is dropped.
- **Line numbers.** `lines`, `symbol`, `line_base=file` and the gutter of `linenos` count the lines of the file as written; a dropped marker line keeps its number, so displayed numbers may skip it. Numbers with `line_base=snippet` count the displayed lines. A segment partly outside `lines` or `symbol` is cut to the lines shown; one wholly outside is dropped.
- **Rendering.** Each segment is wrapped in `<span class="lt-seg" data-lt-seg="NAME">`, one piece per displayed line it spans, without the spaces at the edges of a piece; the first piece carries `id="NAME"`. A Pygments token cut by a segment boundary is split into two spans of the same class; code without segments renders exactly as before.
- **Highlights.** `highlight` (of `code` and of `code-morph`, section 8.11), the entries of `code-steps` `steps:` and the lines a follower reads from its leader's `meta` accept segment names beside line numbers and ranges (`"3, i-init"`, `[i-init, 4-5]`). A highlighted segment is marked itself (the highlight background with an underline in `--lt-hl`), and the lines holding it are not dimmed. A name that is not a segment of the block is LT022.
- **Errors.** An unclosed segment, an `@end` with no open segment or naming another one, a name defined twice in one text, or an empty segment is error LT022, its message giving the file and line of the marker.
- **Ids on a slide.** Segment names are element ids: on a slide, the ids written by the author (attribute lines, placed badges, raw HTML in the body), explicit component ids and segment names MUST be distinct (LT058; two components with one id are LT007). Two blocks showing the same annotated file on one slide therefore collide; give one of them `markers=false`, which shows the text as written, markers included. Ids MAY repeat on different slides: arrows resolve them inside their slide.
- `diff-steps` removes markers from its versions (unless `markers=false`) and defines no segments. `code-morph` reads them in every version and in its file, and its segments follow the text from one position to the next (section 8.11).

### 8.11 Code that changes: `code-morph`

A `code-morph` block shows one piece of code whose text changes from one position to the next, for example a bug and its fix. The audience watches the old text turn into the new one: tokens that survive keep their identity and glide to their new place, removed tokens fade out and new tokens fade in. `diff-steps` remains the static, marked-up view of the same versions.

**Two forms.** The body holds either `versions:` or, with the option `file`, `steps:`; one of the two is required and they exclude each other, `file` needs `steps:`, and `lines`, `symbol` and `label` belong to the steps form (all LT021).

````markdown
```code-morph {#fix lang=python title="the off-by-one"}
versions:
  - code: |
      for i in range(len(xs) - 1):
          total += xs[i]
    label: buggy
  - {file: fixed.py, label: fixed}
```

```code-morph {#loop lang=scheme file="sum-to-n.scm" label="as written"}
steps:
  - bound: "(>= i n)"
    label: "stop before n"
  - init: "(i 1)"
```
````

- **Versions.** `versions:` is read as by `diff-steps` (section 8.8): file paths, or mappings with `file` or `code` and an optional `label`. A mapping MAY also set `lang`, which replaces the block's `lang` for that version, so a version can be written in another language, and `highlight` (below). At least two versions are needed (LT022). Position `i` shows version `i`. The default label is the file path as written or `version N`; in a block whose versions do not all have the same language, it is the name of the version's lexer (`Python`, `Scheme`).
- **Steps.** With `file`, the file holds the code once, with segment markers (section 8.10), and `lines` and `symbol` select part of it as for `code`. Position 0 shows the selection as written; each entry of `steps:` is one more position and maps segment names to the text that replaces their contents. Steps are cumulative: a step applies on top of the position before it, and a name set to `null` returns its segment to the text of the file. Setting a segment drops the replacements of the segments nested in it; when it returns to the file's text, they show the file's text too. The keys `label` (the label of that position), `highlight` (below) and `lang` (the language cannot change in this form) are reserved, so a segment with one of these names cannot be set in a step; `lang`, a name that is not a segment of the selection, and a step that sets both a segment and one nested in it are LT022. A replaced segment keeps its name and covers its replacement text, so arrows and the title follow it; segments nested in a replaced one do not exist while it is replaced, and naming one in a step is LT022. The replacement is the text as written (markers in it are not read, and show as written), with its trailing line breaks removed; when the segment starts within the indentation of its first line, that indentation stays in front of the replacement and every further line of the replacement is indented by it as well. An empty replacement of a segment that fills whole lines removes those lines. The option `label` is the label of position 0. The default labels are `as written` for position 0 and `step K` for step `K`.
- **Options.** `lang`, `title`, `markers` (default `true`; `false` reads no segment markers), `linenos`, `duration` (milliseconds of one animated step, default 600; 0 never animates), `room` (`max`, the default, or `fit`, below), `mark` (default `false`: tokens that arrive are briefly tinted with the background of added lines, `--lt-add-bg`), `highlight` (below).
- **Highlights.** A position MAY highlight lines and segments, as a `code` block does (section 8.10): its targets are line numbers, ranges and segment names, as a comma-separated string or a list, plus the keyword `changed`. They are written in the version (`highlight:` in a mapping of `versions:`) or in the step (`highlight:` in an entry of `steps:`), and apply to that position only, not to the steps after it. The option `highlight` is the default of every position that sets none, which is how position 0 of the steps form is highlighted; a position that sets `highlight: ""` (or an empty list, or null) highlights nothing. Line numbers count the rows of the version shown at that position, from 1, as `linenos` numbers them. `changed` names the rows that hold a unit new at that position (a unit that did not survive from the position before, alignment step 3), so the audience sees where the change it just watched landed; it names nothing at position 0, and a segment called `changed` cannot be highlighted by name. In a position's own targets, a line beyond its rows and a name that is not a segment at that position are LT022. In the option, a line must exist at every position that uses the default, and a name must be a segment at one position at least; where it is not a segment, it highlights nothing.
- **Highlights, appearance.** At rest a highlighted position looks like a `code` block of the same text with the same `highlight`: a highlighted row has the highlight background and the `--lt-hl` left border, every other row (its units and its line number) is dimmed, and a highlighted segment is marked itself, its rows staying undimmed. A position that highlights nothing dims nothing. The bands and segment marks are painted under the units, from a highlight layer per position built with the rest; the transparent text copy on top, and the arrows that measure it, are unchanged. A block without any highlight renders as it did before highlights existed.
- **Positions and meta.** The block has one position per version and is a track like `code-steps` (section 6.1). `meta[i]` is `{"label": LABEL, "version": i}`; it holds no line numbers, since lines change between positions, so a `code` follower that reads `lines` or `line` highlights nothing.

**Alignment, at build time.** All matching is done in Python; the runtime places what it is given.

1. Each version is highlighted with the lexer of its language (`lexer_for`, section 3.13, with the Scheme correction). Tabs are expanded to columns of 8, the width the browser gives them in a `code` block. Tokens spanning lines are cut at line ends, then every token is split into units: a run of word characters, a run of spaces, or one other character, each keeping the token's class. Units of spaces are not drawn: a token sits at an absolute row and column, so indentation is a gap, and code that is re-indented moves instead of being recreated.
2. Consecutive versions are aligned by lines with `difflib.SequenceMatcher` (`autojunk=False`), comparing each line's units without its spaces. A line that is deleted on one side and inserted on the other, with the same units, at least six characters long (not counting spaces) and unique among the unmatched lines of both sides, is a move. Equal lines and moves pair their units in order. In each other changed region, the units of all its old and new lines are aligned by a second `SequenceMatcher`, on class and text when both versions have the same language and on text alone otherwise; units of equal runs survive, possibly on another line (a line rewritten into several, or several into one).
3. A unit that survives from one version to the next keeps its identity (and its element in the page); every other unit is new. A unit's class is recorded per version, so a surviving unit whose class changes (another language, or a lexer that reads it differently) changes colour.

**Rendering.** At rest the block looks like a `code` block of its current version: the same background, title bar, font, size, line height and padding. Every drawn unit is an absolutely positioned element at `col` character widths (`ch`) and `row` line heights from the origin of the text, so no layout is measured. A transparent plain-text copy of the current version lies over the units at the same origin: it carries the native text selection and the segments of the current version (`<span class="lt-seg" data-lt-seg="NAME">`, one piece per line, the first with `id="NAME"`, as in section 8.10), which arrows measure. Changing position replaces that copy at once. The title bar shows `title` and the label of the current version; it is shown when `title` is set, when any label was written, or when the language changes. With `linenos`, the rows of the current version are numbered from 1, beside the text, and the numbers do not move. A character that does not take one column of a monospace font (a wide character of East Asian scripts or an emoji, a combining mark, a control character) misplaces the units after it on its line: warning LT060. Two consecutive positions with the same text, language and highlights: warning LT059 (positions that differ only by their highlights are not).

**Room.** With `room=max` the text area keeps the height of the tallest version and the width of the widest at every position, so the rest of the slide never moves. With `room=fit` its height is that of the current version and changes with it (animated on a single step), moving what follows; its width stays that of the widest version. Long lines scroll horizontally, and a block taller than its space scrolls, as a `code` block does; when the text area overflows, the first highlighted row (or row holding a highlighted segment) of the shown position is scrolled into view, or, at a position that highlights nothing, the first row of the shown version that differs from the version before it (in the order of the versions).

**Motion.** On a single-step move (`info.animate`, section 10.1) the change takes `duration` milliseconds in three overlapping phases: units that leave fade out during the first 40 %, units that survive glide to their new place (and change colour) from 20 % to 80 %, units that arrive fade in during the last 40 %. Highlights follow the same phases: the bands and segment marks of the old position fade out with the leaving units, surviving units change between dimmed and undimmed while they glide, and arriving units fade in to their dimmed or undimmed state together with the new bands and marks. Every other move, the presenter preview, print mode, `duration=0` and a browser that asks for reduced motion (`prefers-reduced-motion`) place the units directly. With `mark`, arriving units are tinted only in such a phased change. A step that arrives while a change is still playing (skip playback, a quick second NEXT) continues from where the units are, in one short glide without phases. The final geometry does not depend on how a position was reached. After each `show` the block dispatches `lt-relayout` (section 10.4), and again when an animated change of height ends.

**Segments.** In the versions form each version MAY define segments with markers; a name MAY be defined in several versions, and is then one target across them. In the steps form the segments are those of the file, replaced or not. The segment names of all positions are the block's anchors (LT058, section 8.10); at a position where a segment does not exist, an arrow at it is hidden.

**Print.** In the PDF a morph is printed at the step of each page, like any component (section 11.5).

---

## 9. Animation Frames

### 9.1 Authoring

```python
from lattice.anim import GraphTrace

def dijkstra_trace(graph, start):
    t = GraphTrace(graph)
    dist = {v: None for v in graph}
    dist[start] = 0
    t.frame(nodes={start: {"state": "active", "label": "0"}},
            panel={"dist": dist}, caption="Start at A", meta={"line": 4})
    ...
    return t
```

- `Trace.frame(delta=None, *, meta=None, transient=None, **parts)` appends one frame. `parts` are merged into `delta` (for example `nodes=`, `edges=`, `panel=`, `caption=`). `transient` values apply to that frame only.
- Frame 0 is the base state with the first delta applied. The number of positions equals the number of `frame` calls (at least 1).
- `meta` is kept per frame for followers and is not emitted unless the component includes it in `data`.
- `GraphTrace` defines the conventional state shape below; node and edge values may be a state string or a mapping, and edges may be given as `(u, v)` tuples.
- `ArrayTrace(values)` uses `values`, `cells` (persistent per-index states), `marks` (transient per-frame highlights), `pointers` (name to index, `None` removes), `caption` and `panel`.
- `TreeTrace(root=None, *, key="key", children=("left", "right"))` traces a tree whose shape changes. `frame(root=...)` takes a snapshot of the author's own node objects and stores it as `tree: {"root": name, "kids": {name: [child name or null, ...]}}` (nodes without children are omitted from `kids`). A frame without `root` keeps the previous shape; a new shape replaces the old one as a whole instead of being merged. `key` is an attribute or mapping key, or a callable, giving the node's name; `children` is a tuple of attributes read as fixed slots (`None` allowed), one attribute holding a list, or a callable. Tuples `(name, child, ...)` and bare scalars (leaves) are nodes too. A name appearing twice in one snapshot (duplicate or cycle) is an error. `nodes`, `edges` (keys `parent->child`, or `(parent, child)` tuples), `panel` and `caption` work as in `GraphTrace`.
- `GridTrace(values, *, rows=None, cols=None)` traces a 2D grid. State: `values` (list of rows; a string row is one cell per character), `rows` and `cols` (header labels), `cells` (persistent per-cell states), `marks` (transient), `pointers` (name to `[row, col]`, `None` removes), `arrows` (`"r,c->r,c"` to a state, `None` removes), `caption`, `panel`. Cell keys are `(row, col)` tuples or `"r,c"` strings. `frame(put={cell: value})` changes single values; `frame(values=...)` replaces the grid.
- `VersioningTrace(program, algorithm=..., limit=..., ...)` runs basic block versioning on a program and records one frame per event; it is built by `bbv-anim` rather than by an author's function, and section 9.5 defines its frames.
- States styled by the built-in themes: graph and tree nodes and edges `active`, `frontier`, `visited`, `done`, `tree`, `path`, `dim`, `error`; array cells `compare`, `swap`, `pivot`, `sorted`, `done`, `dim`; grid cells `active`, `compare`, `frontier`, `visited`, `done`, `path`, `wall`, `start`, `goal`, `dim`, `error`; grid arrows `active`, `path`, `dim`; versioning nodes `queued`, `done` with marks `active`, `new`, `back`, `merge`, `merged`, `gone`, and edges `new`, `gone`; abstract interpretation adds the node state `dead`, the marks `changed`, `widened` and the edge state `active`.

```json
{
  "nodes":   { "A": { "state": "active", "label": "0" } },
  "edges":   { "A->B": { "state": "relaxed" } },
  "panel":   { "dist": { "A": 0, "B": 4 } },
  "caption": "Relax A -> B"
}
```

Edge keys are `u->v` for directed and `u--v` for undirected graphs; for undirected graphs the runtime also accepts `v--u`.

### 9.2 Delta semantics

`apply(state, delta)`: for each key of `delta`, if its value is `null` the key is removed; if both values are objects, apply recursively; otherwise the value replaces the old one. Arrays are replaced as a whole.

### 9.3 Frame stores

`trace.frame_store(max_full_bytes, keyframe_interval)` (values from `ctx.frames_config`) materializes the frames and returns one of:

```json
{ "format": "full", "count": 42, "frames": [ {...}, {...} ] }
```

```json
{ "format": "keyframed", "count": 600, "interval": 16,
  "keyframes": [ {...}, {...} ],
  "deltas": [ null, {...}, {...} ] }
```

- `full` is used unless its canonical JSON exceeds `build.frames.max_full_bytes`.
- In `keyframed`, `keyframes[j]` is the full state of frame `j * interval`, and `deltas[i]` is the delta from frame `i - 1` to frame `i` (`null` at keyframe indexes).
- Identical consecutive states are allowed; they cost little in either format.

### 9.4 Layout stability

`ctx.layout` MUST be computed once per instance, on the union of the base graph and every element that appears in any frame. Elements absent from a frame are hidden, never re-laid out.

Trees are the exception, since insertions and rotations move nodes. `tree-anim` computes positions per frame at build time and stores them in the frame as `pos` (node name to `[x, y]`), all in one box sized for the largest frame, each frame centered horizontally in it. The `binary` layout places a node by its in-order rank and its depth, so a rotation keeps every node's x and only changes depths; `tidy` gives leaves consecutive slots and centers a parent over its children. On a single step the runtime moves nodes from their old to their new positions; any other move places them directly.

### 9.5 Basic block versioning

`bbv-anim` and `bbv-cfg` work on a **program**: functions made of basic blocks, in the shape that Static Basic Block Versioning (SBBV) and Lambda Versioning (ΛV) expect (a CPS-like form where every block lists the variables it receives). The Python package `lattice.bbv` holds the model (`ir`), the type lattice and contexts (`types`), the primitives (`prims`), the two algorithms (`sbbv`, `lv`), the merge heuristics (`heuristics`), the frames (`trace`) and the layout (`layout`).

**Text syntax.** A `.bbv` file (or the `source` option) is a sequence of functions; `;` starts a comment.

```ebnf
program     = { function } ;
function    = "function" SP NAME "(" [ params ] ")" { SP option } NL { block } ;
params      = param { "," param } ;
param       = NAME [ ":" type ] ;                 (* an annotation gives the entry context *)
type        = TYPE [ interval ] ;                 (* "fx | bg", "fx [0, 100]", "num (-∞, 5]", "fx [0, ⟦v⟧-1]" *)
option      = "hidden" | "limit=" ( INT | "none" ) ;
block       = LABEL [ "(" [ params ] ")" ] ":" [ SP instr ] NL { SP instr NL } ;
instr       = VAR "=" PRIM "(" [ args ] ")" | VAR "=" arg
            | "if" SP test SP "goto" SP LABEL SP "else" SP "goto" SP LABEL
            | "goto" SP LABEL [ "(" [ binds | args ] ")" ]
            | "call" SP callee "(" [ args ] ")" SP "->" SP LABEL [ "(" [ params ] ")" ]
            | "return" SP ( arg | PRIM "(" [ args ] ")" ) | "fail" ;
test        = PRIM "(" [ args ] ")" | VAR ;      (* a predicate (type test, comparison), or the truthiness of a variable *)
binds       = VAR "=" arg { "," VAR "=" arg } ;  (* rebinding of the target's parameters by name *)
arg         = VAR | INT | FLOAT | STRING | "#t" | "#f" | "nil" ;
```

- The first block of a function is its entry. Every block ends with `if`, `goto`, `call`, `return` or `fail`. Labels are local to their function. A parameter annotation (`n: fx | bg`, `m: fx [0, 100]`, `i: fx [0, ⟦v⟧-1]` for a valid index of the vector parameter `v`) is the parameter's type in the generic entry context (default `any`); the versioning algorithms keep its types and drop its interval unless `intervals` is on.
- A test is a primitive returning a boolean: a type test narrows its argument on each branch; a comparison (`<`, `<=`, `=`, `>`, `>=`, their `fx` and `##` variants, `zero?` and `fxzero?`) narrows the intervals of its integer arguments; other predicates (`eq?`, `not`) narrow nothing. A bare variable is tested for truthiness (`#f` or not).
- A block's **parameters** are the variables live at its entry plus the function's parameters (always tracked, as ΛV contexts do), or the explicit list when one is written (which MUST cover the variables used; the function's parameters and `#res` are added). A block reached by a `call` is a **return block**: it also receives `#res`, the returned value. `goto A(x=y)` rebinds the parameter `x` of `A` to `y`; positional arguments are allowed only when `A` declares its parameters; a function parameter cannot be rebound.
- `call f(args) -> K` continues at the return block `K`; `-> K(vars)` names the variables passed to it (by default the ones live at `K`). `f` is a function of the program, or a variable holding a procedure. Under SBBV every call is opaque (`#res` is `any`); under ΛV a call to a known function requests a specialized entry point and receives one return point per exit contract of that entry (thesis chapter 3).
- Primitives come from a table (`lattice.bbv.prims`): type tests (`fixnum?`, `flonum?`, `bignum?`, `number?`, `pair?`, `null?`, `procedure?`, `boolean?`, `string?`, `integer?`, `vector?`), fixnum operations (`fx+`, `fx-`, `fx*`, the overflow-checking `fx+?`, `fx-?`, `fx*?` returning `fx | #f`, or `fx` with its interval when the interval of the result fits the fixnum range, comparisons), flonum operations (`fl+`, `fl-`, `fl*`, `fl/`, comparisons), generic arithmetic (`+`, `-`, `*`, `/`, `quotient`, `abs`, `min`, `max`, comparisons, `zero?`, and the `##` variants that skip the type checks: arguments are narrowed to numbers, two fixnums may overflow to a bignum), `fxquotient`, `fxmodulo`, `fxremainder`, `fxzero?`, `flzero?`, `car`, `cdr`, `##car`, `##cdr`, `cons`, `vector-length` and `##vector-length` (the length of a vector: the singleton `fx {⟦v⟧}` naming the argument's class, or `fx [0, maxfix]` for a value with no name; both narrow their argument to `vec`), `vector-ref` (`vec`, `fx`), `##vector-ref`, `vector-set!`, `##vector-set!`, `make-vector`, `eq?`, `eqv?`, `equal?`, `not`, `display`, `read`, `random`. A `prims` option adds or overrides entries: `{name: {args: [fx, fx], result: "fx | #f"}}` or `{name: {test: pair}}`. They are added before the program is checked, so a predicate it declares (a type test, or a primitive whose result is `bool`, which narrows nothing) may be tested in an `if`. A primitive whose argument requirements cannot be met in a context makes the block fail at that point.
- Types are sets of `fx`, `bg`, `fl`, `#t`, `#f`, `nil`, `pair`, `str`, `vec`, `proc`, `other`, written `fx | fl`, `!fx`, `bool`, `num`, `any`, `⊥`; a procedure value may carry the function it is known to be (`proc(square)`); an integer may carry an interval (`fx [0, 100]`, `fx | bg [1, ∞)`, `{0}` for a singleton), which the abstract interpreter always tracks (section 9.6) and the versioning algorithms track with `intervals` on. Contexts map variables to types and keep equivalence classes of variables holding the same value, printed `a/b: fx`. Type tests narrow both branches; assignments break equivalences; `x = y` creates one.
- **Vector lengths** (paper section 3.3, thesis appendix D). A bound of an interval may be the symbol `⟦v⟧-i`: the length of the vector held by the class of variable `v`, minus an offset `i >= 0`. A length is a fixnum in `0..maxfix`, so `⟦v⟧-i` lies in `-i..maxfix-i`; `maxfix` is `2^(fixnum_bits-1) - 1`. The symbol names the representative of the class (the earliest variable of the class in the context), so that two contexts of the same shape carry the same symbols and compare equal; every operation that changes classes renames the symbols, and a symbol whose vector leaves the context (a reassignment with no alias, a `goto` or a call that does not pass it, an exit contract, a merge with a path where the class is not exactly `vec`) is widened to its numeric value. The rules on bounds: lower bounds drop the symbol under addition (`(⟦v⟧-i) + j = j - i`), upper bounds keep it while the offset stays nonnegative (`(⟦v⟧-i) + j = ⟦v⟧-(i-j)` if `i >= j`, an overflow otherwise); other operations use the numeric values. A comparison between a number and a symbol is decided only when the numeric range of the symbol settles it (`⟦v⟧-1 < ⟦v⟧` always holds, `0 <= ⟦v⟧` too). When a narrowing has two candidate bounds whose order is unknown, an upper bound keeps the symbolic candidate and a lower bound the numeric one (what the bound checks `i < len` and `i >= 0` need); a union keeps a symbol only when it bounds both sides. In a merge (below), a symbolic upper bound that grew widens to `⟦v⟧`, a bound that became symbolic keeps the symbol, a bound that became numeric stops at the symbol's numeric value, and a symbolic lower bound that grew becomes its numeric value. With `vector_bounds: false` (on `bbv-anim` with `intervals`, and on `abstract-interp-anim`) no symbol ever enters a context: `vector-length` and `##vector-length` give `fx [0, maxfix]`, and an annotation that names a length is widened to its numeric value at the entry (`fx [0, ⟦v⟧-1]` becomes `fx [0, maxfix-1]`). A bound check against a length read again (figure 7's `fx<(i, len2)`) then stays.
- A program may also be built in Python (`lattice.bbv.ir.Program`, `Function`, `Block` and the instruction classes) and returned by the function named in `program`, which then receives the block's extra options as keyword arguments; it may also return the program text.

**Algorithms.** `algorithm: sbbv` implements thesis algorithms 1.1 to 1.7: breadth-first traversal of versions, `mergeSome` when a block has more reachable versions than its limit (pairs are merged until the limit holds, the pair chosen by the heuristic), reachability recomputed after every change, versions skipped while unreachable and requeued when reconnected. With `intervals` on (paper section 3.2), contexts keep the intervals of annotations, constants and arithmetic, comparisons narrow them, the overflow-checking operators are decided when the interval fits, and a merge is the union with widening of the paper's algorithm 4: the older version's intervals are widened against the newer one's with the `thresholds` (section 9.6), which is what makes loops converge. The merge heuristics compare types by their Hamming distance, to which the intervals add a fraction below one (equal 0, nested or same bounds up to numeric offsets 0.25, otherwise 0.5, plus 0.25 when the symbolic bounds name different vectors), so intervals only break ties. `algorithm: lv` implements algorithms 2.1 to 2.10 on top: specialized entry points at call sites, exit sites, return points computed as `callContext ∩ exitSite.contextAfter`, cascading additions before removals, generic entries of the other functions queued when the queue first empties, return point indices allocated at the end (one index per distinct exit contract of a function, reachable exits first). Jump cascades are not removed. Version labels are the block name followed by the creation rank of the version among the block's versions (`A1`, `A2`; `J2.1` when the block name ends with a digit).

**Frames.** One frame per event, in this order of kinds: `start`, `dequeue`, `must-merge`, `merge`, `specialize` (or one `instruction` frame per instruction with `granularity: instruction`), `entry`, `exit`, `return-points`, `generic-entries`, `done`. Events touching only hidden functions produce no frame. A frame is:

```json
{
  "nodes": { "7": { "state": "queued", "mark": "new", "entry": true } },
  "edges": { "3->7:true": { "kind": "true", "state": "new" }, "5->9:return": { "kind": "return", "label": "[1]" } },
  "pos": { "7": [312.0, 96.0] },
  "caption": "Specialize A1: queue B1 and L1.",
  "panel": { "queue": ["B1", "L1"], "versions": { "A": 1 }, "checks": 3, "merges": 0, "limit": 2 }
}
```

`checks` counts the tests left in the reachable specialized code (every `if` not removed: type tests, comparisons, overflow and truthiness tests). `state` is `queued` or `done` (`shown`, in instruction frames, is the number of code lines specialized so far); `mark` is `active` (the version being processed), `new`, `back` (reachable again), `merge` (a merge candidate), `merged` (the result) or `gone` (unreachable since this frame, drawn once more at its old place). Edge kinds are `goto`, `true`, `false`, `return` (dashed, labelled with the return point indices) and `call` (drawn only with `call_edges`). Static text lives in `data.tables`: per version its label, block, context lines, specialized code (with removed tests marked) and exit context; per function its blocks. `meta[i]` holds `event`, `block` (the origin block, for `bbv-cfg`), `function`, `lines` and `line` (the program lines of that block, or of the instruction), and `algo` (the lines of the bundled pseudo-code listing `lattice:bbv/pseudocode/sbbv.txt` or `lv.txt` executed by the event, for a `code` block with `meta=algo`).

**Rich text.** Captions, instruction notes and the panel share one vocabulary, produced at build time and styled by the runtime. A caption is a string in which a span ```kind:text``` names what `text` is: `op` (the operation of the frame, drawn first as a badge whose colour follows its category: specialization amber, test removal, merges, widening and dead edges red, done and exits green, new reaches and unions teal, the rest neutral), `tag` (a secondary operation, outlined), `v` (a version label, drawn as a chip filled with the origin colour of its block; written `v:A2|find/A` so that the chip finds its block), `var` (a variable), `ty` (an abstract type, its interval in a second tone), `code` (an instruction or test) and `rm` (a test that was removed, struck through). Captions read "badge, versions, details": `` `op:specialize` `v:F1|find/F` · `tag:queue` `v:G1|find/G` ``. `lattice.bbv.rich` builds and strips the markup (`plain`); tooltips and the presenter notes use the plain text. Backticks never occur in programs, contexts or labels. Inside a node, context lines keep the `;; name: type` notation of the figures with the names padded to the longest one of the node, the variable in ink, the type in the type colour and the interval (symbolic bounds included) in the range colour (`--lt-type`, `--lt-range`); code lines colour the keywords (`if`, `goto`, `else`, `return`, `call`, `fail`, `->`) and the `[i]` indices, and a removed test is struck through in the warning colour. In the panel, a version label becomes a chip and a widening chain entry marks its `∪` (teal) or `∇` (red) step. Node sizes are computed on the padded lines.

**Layout** (block bands). The source CFG of each function is laid out once with Graphviz when available (ranks and left-to-right order; without Graphviz, longest paths and declaration order). Per frame, the live versions of a rank are packed along it, sorted by their block's order and creation id, in lines of at most `wrap` versions, and centred in the function's column (`TB`) or band (`LR`); functions sit side by side in the order of `functions`. Node sizes come from the text shown, so a version never resizes; the drawing box is the union over all frames. Back edges travel along a lane beside the function. On a single step the runtime glides nodes between their two known positions; any other move places them directly. The drawing keeps its size across frames: the panel has a fixed width, and the caption fits in the space left below the drawing, shrinking its text when a long caption would not fit. In a column narrower than 760 px the panel moves under the drawing (unless `panel_at=right`; `panel_at=below` puts it there at any width, section 8.8), and the drawing keeps the `height` given; a panel with nothing to show takes no space.

**Enlarging a block.** In `bbv-anim`, `bbv-cfg` and `abstract-interp-anim`, `clickable` (default `true`; `on` and `off` are accepted) lets the viewer click a block of the drawing to enlarge it (section 7.7). The enlarged block shows the items of `clickable_show`, among `label`, `context`, `code` and `after` (default all four; `after` is the exit context, under a line `;; after:`, and is not an item of `show`), in the state of the current step: its marks and colour, the entry context of the frame in abstract interpretation, `…` for a queued version, only the lines specialized so far with `granularity: instruction`, and the exit context once the version is specialized to its end (a `bbv-cfg` block has none; its context is its parameters). Its size is computed at build time from the text of `clickable_show` (the largest over the frames when the context changes with the frame) and emitted in the instance data as `zoom: {show, sizes}`; with `clickable` off the data has no `zoom` and blocks do not react to clicks. Faded versions (mark `gone`) are not clickable. `clickable_show` with an unknown item is a component error, like `show`.

### 9.6 Abstract interpretation

`abstract-interp-anim` runs the classical analysis of thesis chapter 1.1 on one function of a program written as in section 9.5: the CFG is fixed, every block has one entry context, and a FIFO worklist re-interprets a block whenever its entry context grows, until a fixed point. The package `lattice.bbv` holds the interval lattice (`intervals`), the interpreter (`absint`) and its frames (`AbstractTrace` in `trace`).

**Abstract values.** A type as in section 9.5 plus, for integers, an interval `[lo, hi]` with integer or infinite bounds (`{0}`, `[0, 127]`, `[1, ∞)`, `(-∞, ∞)`; large bounds print as `2^31-1`). Integer constants carry singleton intervals; flonums carry none. The interval and the type inform each other: an integer whose interval fits the fixnum range (`fixnum_bits`, default 61, the width of a 3-bit tag implementation) is `fx`, beyond it `fx | bg`; a `fixnum?` test clips a known interval to that range. A bound may be a vector length (section 9.5); the same rules apply at joins and comparisons.

**Transfer functions.** Assignments apply the primitive's result rule, which includes interval arithmetic for `+`, `-`, `*`, `quotient`, `abs`, `min`, `max` and the `fx` variants (`fx+?` and friends return `fx | #f` with the interval of the sum); `goto` rebinds parameters; a call is opaque (`#res: any`); `return` ends the block. At an `if`, each outcome narrows the context: type tests through the type lattice, comparisons through the intervals (`>(i, 0)` holding gives `i ∈ [1, ∞)`, failing gives `i ∈ (-∞, 0]`). With `narrowing: false` outcomes are still found impossible or possible but nothing is learned from them.

**Join.** The context sent along an edge is joined into the successor's entry context by union with widening: types are joined; an interval bound that grew moves to the next threshold at or beyond it. The `machine` thresholds (the sign and the 8, 32 and 64-bit limits: `0, 1, 2, 127, 128, 2^31-1, 2^31, 2^63-1, 2^63, ∞` and their negatives; `thesis` is accepted as an alias) reproduce figure 2 step for step; `sign` keeps `-1, 0, 1`; a list of integers sets the thresholds, and MAY also name `machine` and `sign` (their thresholds are added) and `maxfix` and `minfix` (the bounds of the fixnum range of `fixnum_bits`), with an optional offset (`maxfix-1`, `minfix+1`), so that `[sign, maxfix]` stops a growing index at the largest fixnum and `[sign, maxfix-1, maxfix]` also keeps the bound that `i < len` gives when lengths are numbers; `none` is plain union (the run then stops at `max_steps` if it does not converge, with warning LT046). A successor whose context changed is queued once. An edge whose outgoing context is `⊥` is dead; a block never reached stays `⊥`.

**Frames.** One frame per event: `start`, `dequeue`, `instruction` (with `granularity: instruction`), `propagate` (one per outgoing edge, with result `first`, `union`, `widened`, `unchanged` or `dead`) and `done`. Nodes are the blocks (`state` `done` or `dead`; `mark` `active`, `new`, `changed`, `widened`), each carrying `lines` (its entry context for that frame; an integer with no known interval shows `(-∞, ∞)` as in the figures) and `after` (its exit context, shown in the tooltip and in the enlarged block, section 9.5); the propagated edge is `new` (changed), `active` (unchanged) or `gone` (dead). Node sizes are computed over all frames. The panel offers `worklist`, `iterations` and, for each `history` entry `BLOCK.VAR`, the chain of entry values of that variable prefixed with `∪` (union) or `∇` (widening), the red path of figure 2. Captions use the rich text of section 9.5 with the operations `start`, `interpret`, `assign`, `test`, `goto`, `call`, `exit`, `fail`, `reached`, `union`, `widen`, `unchanged`, `dead edge` and `fixed point`. `meta[i]` holds `event`, `block`, `function`, `lines`, `line` and `algo` (lines of `lattice:bbv/pseudocode/absint.txt`). The drawing is the block bands layout of `bbv-cfg`.

---

## 10. Runtime Contract (JavaScript)

### 10.1 Registration

A component runtime is a script that registers a controller when it runs. Runtimes are concatenated after the core, so they MUST NOT use `import` or `export`; they run as a module in single-file output and as a deferred classic script in directory output.

```js
Lattice.component("graph-anim", {
  mount(el, data, api) { /* build DOM once; return an instance object */ },
  show(inst, position, info) { /* render the state at this absolute position */ },
  enter(inst) {},
  leave(inst) {},
  destroy(inst) {},
  zoom(inst, key) { /* optional: an element to enlarge (section 7.7), or null */ },
});
```

`info = { from: number | null, direction: -1 | 0 | 1, animate: boolean }`. `animate` is true only for single-step moves (NEXT or PREV within the slide); jumps, restores and scrubbing use `false`.

`zoom(inst, key)` is called by the core when `api.zoom(key)` asks for an element, or when the other window opened it (section 7.5). It returns `{ el, width, height, source }`: a new element to show in the card, its natural size in its own units, and the element of the slide it grows from; or `null` when `key` names nothing to show at the current position. `el` MUST depend only on `key` and the position last shown.

### 10.2 Lifecycle

1. `mount` is called once, the first time the slide becomes current. Only instances with `data` are mounted; static components (plain code, matplotlib plots, diagrams) need no runtime.
2. Each time the slide becomes current: `enter`, then `show` with the position for the current step.
3. On each step change where the instance's position changes: `show`.
4. When the slide stops being current: `leave`. Timers and animations MUST stop.
5. `destroy` is called on page unload.

Requirements:

- `show` MUST be idempotent and MUST depend only on `position` (plus `info` for transition effects). It MUST work for any position, in any order.
- Controllers MUST NOT register global keyboard listeners. Pointer and wheel events inside `el` are allowed.

### 10.3 The `api` object

| Member | Description |
|---|---|
| `api.instanceId` | Instance id |
| `api.frames(store)` | Returns `{ count, at(i) }` for a frame store, regardless of format, with a small cache |
| `api.goto(id)` | Performs JUMP |
| `api.palette` | Computed style of the root element; read tokens with `api.palette.getPropertyValue("--lt-accent")` |
| `api.presenter` | `true` in presenter view |
| `api.onResize(cb)` | Called when the slide scale changes |
| `api.zoom(key)` | Asks the core to enlarge element `key` of this instance through the controller's `zoom` (section 7.7); a no-op in passive windows |

### 10.4 Core-managed features

- Reveal: elements carry `data-lt-reveal="k"`; the core shows fragment `k` when the reveal position is at least `k`, using `visibility: hidden` so layout does not shift.
- Badges that wait for their step (section 3.9): the badge carries `data-lt-badge="step"` or `data-lt-badge="next"`; at every step the core looks up the detour steps of its `data-lt-detour` in the slide's `stepDetours` and hides the badge the same way as a fragment. Each badge is handled on its own, so the placed badges of one detour may differ. The presenter preview and print mode render positions through the same path, so they follow.
- Branch menus, detour badges, wiki links, transitions, overview, go-to, presenter view (with its preview and scrubber), enlarged elements (section 7.7) and print mode (section 11.5) are implemented by the core.
- A runtime that moves content of the slide without changing its own box (the text of a `code-morph`, section 8.11) dispatches a bubbling `CustomEvent` named `lt-relayout` on its element after it has placed its new state, with `detail.animate` true when the move is animated and, optionally, `detail.timing = {delay, duration}` in milliseconds, when the content glides. Runtimes that measure the slide (`arrow`, section 8.9) listen for it on their slide section and glide with that timing.
- Column widths (section 3.8). A `columns` container with a column named in a `width` cue or collapsed by its attribute carries `data-lt-cols` and `data-lt-duration`; each of its columns carries `data-lt-col` (its id, or empty) and `data-lt-flex` (the `flex` value of its attribute, empty for the default), and its content is wrapped in `<div class="lt-column-in">`. At every step the core gives each such column the `flex` value of the current position of the columns track (`SlideJSON.columns`), or its own `data-lt-flex`; a collapsed column has the class `lt-col-shut` and is `inert`. An animated change measures the columns before and after the change (for display only, as `arrow` does), moves their boxes in slide pixels while the width of their contents stays fixed, then sets the final values. It dispatches `lt-relayout` on the container with `detail.follow`, the duration of the move in milliseconds; a still change dispatches it with `animate` false. A runtime that measures the slide re-measures at every frame while `follow` lasts (`arrow` does). A runtime whose drawing depends on its own size observes it (`ResizeObserver`): a change of widths changes its box once per step.
- The core exports helpers for runtimes: `Lattice.frames(store)`, `Lattice.applyDelta`, `Lattice.renderPanel(el, panel, keys)` (the variable panel of the animation components) and `Lattice.esc` (HTML escaping).

---

## 11. Output Format

### 11.1 Single-file document

```html
<!doctype html>
<html lang="en" data-lattice="1" data-theme="default">
<head>
  <meta charset="utf-8">
  <meta name="generator" content="lattice 0.16.0">
  <title>Shortest Paths</title>
  <style>:root{--lt-w:1280px;--lt-h:720px}</style>   <!-- design size from `aspect` -->
  <style id="lt-theme">/* base, theme, Pygments, KaTeX if used, component CSS */</style>
  <script>/* shared libraries (KaTeX, Vega, Plotly), only those the deck requires */</script>
</head>
<body>
  <div id="lt-root">
    <main id="lt-stage"><div id="lt-viewport">          <!-- scaled to fit the window -->
      <section class="lt-slide layout-default" id="s-dijkstra" data-slide="dijkstra" hidden>
        <header class="lt-head"><h1 class="lt-title">Dijkstra's algorithm</h1></header>
        <div class="lt-body">
          <div class="lt-c lt-c-graph-anim" data-component="graph-anim" data-instance="dijkstra/trace">
            <div class="lt-graph-anim"></div>
          </div>
          <button class="lt-detour-badge" data-lt-detour="heap-refresher"><kbd>h</kbd><span>Refresher: binary heaps</span></button>
        </div>
      </section>
      <!-- one section per slide, detour slides included, document order -->
      <div id="lt-hud"><div id="lt-crumbs"></div><div id="lt-progress"></div></div>
    </div><!-- #lt-zoom, the layer of enlarged elements (section 7.7), is added here at run time --></main>
    <aside id="lt-presenter-panel" hidden></aside>
  </div>
  <div id="lt-overlay" hidden></div>
  <script type="application/json" id="lt-deck">{ ... }</script>
  <script type="application/json" id="lt-data-dijkstra/trace">{ ... }</script>
  <script type="module">/* core runtime, then component runtimes, then Lattice.boot() */</script>
</body>
</html>
```

- Relative image sources are embedded as `data:` URIs; a missing image produces LT051.
- Component data lives in separate `<script type="application/json">` tags, parsed on first mount.
- Speaker notes are stored in the deck JSON, not in slide sections.
- The command line warns (LT032) when the file exceeds 50 MB.

### 11.2 Deck JSON

```ts
interface DeckJSON {
  lattice: 1;                              // format version
  hash: string;                            // content hash, used for storage keys
  version: string;                         // Lattice version that built the deck
  meta: { title: string; author?: string; date?: string;
          aspect: string; theme: string };
  start: string;
  keys: Record<string, string[]>;          // action -> keys
  transitions: Record<"next" | "branch" | "detour" | "link", string>;
  order: string[];                         // slide ids, document order
  slides: Record<string, SlideJSON>;
  detours: Record<string, DetourJSON>;
  instances: Record<string, InstanceJSON>;
  tours: Record<string, string[]>;
  mainPath: string[];
  overview: {                              // empty nodes and edges without Graphviz
    width: number; height: number;
    nodes: Record<string, { x: number; y: number; w: number; h: number; label: string }>;
    edges: (EdgeJSON & { path: string })[];  // path: SVG path of the drawn edge
  };
}

interface SlideJSON {
  title: string;                           // plain text; "" when untitled
  label: string;                           // title, or the id when untitled (overview, go-to)
  scope: string;                           // "root" or detour id
  next: { slide: string } | "back" | null;
  branches: { target: string; key: string; label: string }[];
  detours: string[];
  steps: number;
  tracks: { id: string; kind: "reveal" | "component" | "columns";
            instance?: string; follow?: string }[];
  positions: number[][];                   // [step][trackIndex]
  columns?: Record<string, string>[];      // positions of the columns track: column id -> CSS flex value (section 3.8)
  stepDetours?: Record<string, { id: string; blocking: boolean }>;  // detour steps (section 6.4)
  offpath: boolean;
  transition?: string;
  notes?: string;                          // HTML
  source: { file: string; line: number };
}

interface DetourJSON {
  origin: string; entry: string; label: string;
  key?: string; slides: string[];
}

interface InstanceJSON {
  component: string;
  slide: string;
  data: string | null;                     // id of the JSON script tag (single file), or null
  url?: string;                            // data/<instance>.json (directory output)
}

interface EdgeJSON {
  from: string; to: string;
  kind: "next" | "branch" | "detour" | "link";
  key?: string;
}
```

### 11.3 Deck hash

`hash` is the SHA-256 (first 16 hex digits) of the canonical deck JSON without the `hash` field. It changes whenever the deck changes, which invalidates stale session state.

### 11.4 Directory output

With `lattice build --dir OUT` or `build.output: dir`, the build writes `index.html`, `assets/` (stylesheet, runtime, shared libraries, `media/` for images) and `data/<instance>.json`. The runtime is a deferred classic script and fetches every data file before the first slide renders, so the folder MUST be served over HTTP (for example `python -m http.server -d OUT`); `file://` works only for single-file output. Math fonts stay embedded in the stylesheet.

### 11.5 PDF export

`lattice pdf DECK [-o OUT] [--tour NAME] [--steps first|last|all] [--no-appendix]` writes a PDF, by default next to the deck. It requires Playwright with Chromium (extra `pdf`).

- **Pages.** The tour (default: the main path; `main` also names it) is printed first, in order. Each slide gives one page per selected step: its `pdf` attribute (section 3.5) if present, else `--steps` (default `last`). `all` leaves out detour steps (section 6.4), which repeat the page before them.
- **Appendix** (unless `--no-appendix`). Starting from the printed slides, breadth first, and then from each appendix slide in turn: every detour with slides not yet printed becomes a section; every branch option whose target is not yet printed becomes a section holding the target and the slides that follow it along `next`, up to a slide already printed; off-path root slides linked from a printed slide are collected in a final section, "Linked slides". Sections are lettered A, B, ... in that order.
- **Links.** Wiki links, detour badges and branch options link to the first page of their target when it is printed (badges and options also show its page number) and become plain text otherwise. A badge with `badge=step` or `badge=next` is printed as it is at the printed step (section 3.9). A `next` badge is therefore never on a slide's last step (the default), and with `all`, which leaves out detour steps, a badge shown only at detour steps appears on no page; its detour is still printed in the appendix. Each appendix page names its section and links back to the page that leads to it.
- **Rendering.** The command builds the single-file HTML and opens it in Chromium with `?print` at the design size. In print mode the runtime is passive (as the preview of section 7.5). `Lattice.print(plan)` renders each page of the plan with `animate: false`, then copies the slide into a static page: canvases become images, and ids inside the copy get a per-page suffix, with `url(#...)` and `href="#..."` references updated. A copy keeps the scroll positions of the slide it was made from (a code block scrolled to its highlight). Chromium prints the copies in one pass, one page per slide page, so the links above are links inside the PDF.

---

## 12. Diagnostics

| Code | Severity | Condition |
|---|---|---|
| LT001 | error | Setext level-1 heading |
| LT002 | error | Content before the first slide of a file or detour |
| LT003 | error | Front matter in an included file |
| LT004 | error | Include cycle |
| LT005 | error | File included more than once |
| LT006 | error | Included file not found |
| LT007 | error | Duplicate explicit id |
| LT008 | warning | Auto id renamed to avoid a collision |
| LT009 | error | Malformed attribute block or invalid attribute value |
| LT010 | warning | Unknown slide attribute |
| LT011 | error | Wiki link to an unknown id |
| LT012 | error | Unknown id in `next`, `start` or a tour |
| LT013 | error | `next` or branch target outside the detour's scope |
| LT014 | error | Cycle on the main path |
| LT015 | warning | Unreachable slide |
| LT016 | error | Detour without slides |
| LT017 | error | Malformed branch, or more than one branch on a slide |
| LT018 | error | Duplicate key on a slide, or collision with a global binding |
| LT019 | warning | Unknown container name close to a built-in (likely typo) |
| LT020 | warning | Unknown fenced block name, rendered as plain text |
| LT021 | error | Invalid component options or body |
| LT022 | error | Component render failed |
| LT023 | error | Several independent tracks and no timeline |
| LT024 | error | Timeline references an unknown track or a follower |
| LT025 | error | Timeline position out of range |
| LT026 | warning | Independent track never advanced |
| LT027 | error | Follower position count differs from its leader |
| LT028 | error | Unknown leader or follow cycle |
| LT029 | error | More than one timeline on a slide |
| LT030 | warning | Timeline cue changes nothing, or a timeline line whose ranges are all empty |
| LT031 | error | Ranges of different lengths on one timeline line |
| LT032 | warning | Single-file output larger than 50 MB |
| LT033 | error | Component track needs an `#id` |
| LT034 | error | An include inside a container other than a detour, a list item or a block quote; a detour that is not at the top level of a slide body |
| LT035 | error | Detour does not terminate with `back` |
| LT036 | error | Option given both as attribute and in the YAML body |
| LT040 | warning | Unknown front matter key |
| LT041 | warning | Level-1 heading inside a container |
| LT042 | error | No start slide |
| LT043 | error | Slide repeated in a tour |
| LT044 | error | Component name registered twice |
| LT045 | error | Referenced file not found |
| LT046 | warning | Warning emitted by a component |
| LT047 | error | Invalid render result |
| LT048 | error | Invalid front matter (YAML or value) |
| LT049 | error | Timeline syntax error (including a relative stop after an explicit range start, or `by 0`), or a track twice in one cue |
| LT050 | error | Plugin or `lattice_plugins.py` failed to load |
| LT051 | warning | Image referenced by a slide not found |
| LT052 | warning | Unknown theme (the default theme is used) |
| LT053 | error | Invalid `pdf` slide attribute, or a `pdf` step beyond the slide's last step |
| LT054 | error | Invalid detour step: unknown detour in a timeline, `at` out of range or combined with a timeline, or a malformed `detour` line |
| LT055 | error | `badge=step` or `badge=next` on a detour, or on one of its placed badges, when the detour is not a detour step of its origin |
| LT056 | error | Invalid placed badge (`::detour-badge`): missing or unknown `ref`, a detour of another slide, without an explicit id or with `badge=false`, an unknown attribute or value, an attribute line with `reveal` or key-value attributes, or a badge in speaker notes or in a branch |
| LT057 | error | `.reveal-with` with no fragment before it on the slide, or together with `.reveal` |
| LT058 | error | An id used twice on a slide: element ids written by the author, explicit component ids and code segment names (section 8.10) |
| LT059 | warning | Two consecutive positions of a `code-morph` are identical: same text, language and highlights (section 8.11) |
| LT060 | warning | A character of a `code-morph` that does not take one column of a monospace font: wide, combining or control (section 8.11) |
| LT061 | error | A closing container fence with no open container, a named closing fence (`::: /NAME`) whose name is not that of the container it closes, or a malformed one (section 3.2) |
| LT062 | warning | A container never closed: it ends with its file or its enclosing block (section 3.2) |
| LT063 | error | An `arrow` end naming a list item that does not exist (`LIST[N]`: no such list on the slide, not a list, an index out of range, no nested list), or a `bullet` anchor on an end that is not a list item (section 8.9) |
| LT064 | error | A column width that is not a fraction (`Nfr`), a CSS length or `0`, in a `width` attribute or a `width` cue; a `duration` of `columns` that is not a non-negative integer; a `width` cue naming something that is not a column of this slide directly in a `columns` container, naming a column twice, or naming none (sections 3.8, 3.15) |

Diagnostics are printed as `file:line:col: severity LTnnn: message`. `lattice check` exits with status 1 if any error is reported, 0 otherwise (`--strict` also fails on warnings).

---

## 13. Complete Example

### Files

`talk.md` (root):

````markdown
---
title: Shortest Paths
tours:
  short: [intro, dijkstra, end]
---

# Shortest Paths {#intro}

{.reveal}
- Single source
- Non-negative weights

::include{file="parts/dijkstra.md"}

# Questions? {#end}

::include{file="parts/backup.md" offpath=true}
````

`parts/dijkstra.md`:

````markdown
# Dijkstra's Algorithm {#dijkstra}

```code {#code lang=python file="../algos.py" symbol=dijkstra follow=trace}
```

```graph-anim {#trace source="../algos.py:dijkstra_trace" graph="../data/city.dot"}
start: A
panel: [dist]
```

::: detour {#heap-refresher label="Refresher: binary heaps" key=h}
::include{file="../shared/heaps.md"}
:::

::: notes
If someone asks about negative weights, go to [[bellman-ford]].
:::

# Complexity {#complexity}

$$O((V + E) \log V)$$
````

`shared/heaps.md`:

````markdown
# What is a binary heap? {#heap-what}
...

# Heap operations {#heap-ops}
...
````

`parts/backup.md`:

````markdown
# Bellman-Ford {#bellman-ford}
...
````

### Resolution

| Slide | Scope | `next` | Notes |
|---|---|---|---|
| `intro` | root | `dijkstra` | 2 fragments, so 3 steps |
| `dijkstra` | root | `complexity` | One independent track (`trace`, say 12 frames), `code` follows it: 12 steps, no timeline needed |
| `heap-what` | `heap-refresher` | `heap-ops` | |
| `heap-ops` | `heap-refresher` | `back` | Last slide of the detour |
| `complexity` | root | `end` | |
| `end` | root | `None` | End of main path |
| `bellman-ford` | root | `back` | Offpath, reachable through the notes link |

Main path: `intro`, `dijkstra`, `complexity`, `end`. Edges: 4 `next` (implicit, including `heap-what` to `heap-ops`), 1 `detour` (`dijkstra` to `heap-what`, key `h`), 1 `link` (`dijkstra` to `bellman-ford`). No unreachable slides.

### Excerpt of the deck JSON

```json
{
  "lattice": 1,
  "start": "intro",
  "order": ["intro", "dijkstra", "heap-what", "heap-ops",
            "complexity", "end", "bellman-ford"],
  "slides": {
    "dijkstra": {
      "title": "Dijkstra's Algorithm",
      "label": "Dijkstra's Algorithm",
      "scope": "root",
      "next": { "slide": "complexity" },
      "branches": [],
      "detours": ["heap-refresher"],
      "steps": 12,
      "tracks": [
        { "id": "trace", "kind": "component", "instance": "dijkstra/trace" },
        { "id": "code", "kind": "component", "instance": "dijkstra/code", "follow": "trace" }
      ],
      "positions": [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5],
                    [6, 6], [7, 7], [8, 8], [9, 9], [10, 10], [11, 11]],
      "notes": "<p>If someone asks about negative weights, go to <a data-lt-link=\"bellman-ford\">Bellman-Ford</a>.</p>",
      "source": { "file": "parts/dijkstra.md", "line": 1 }
    },
    "heap-ops": {
      "title": "Heap operations",
      "scope": "heap-refresher",
      "next": "back",
      "branches": [], "detours": [],
      "steps": 1, "tracks": [], "positions": [[]],
      "source": { "file": "shared/heaps.md", "line": 4 }
    }
  },
  "detours": {
    "heap-refresher": {
      "origin": "dijkstra", "entry": "heap-what",
      "label": "Refresher: binary heaps", "key": "h",
      "slides": ["heap-what", "heap-ops"]
    }
  },
  "tours": { "short": ["intro", "dijkstra", "end"] }
}
```

---

## 14. Not Yet Specified

Planned features (spatial mode, plugin hooks, custom themes and others) are tracked in the roadmap of `design-report.md`, section 6. They are specified here when they are implemented.

---

## 15. Changes Since Draft 1

A record of departures from the first draft. Each rule lives in the section cited; this list holds no rules of its own.

| Version | Change | Sections |
|---|---|---|
| 0.1 | Attribute lines may be followed directly by paragraph text | 3.4 |
| 0.1 | Extra options passed to trace functions as keyword arguments | 8.2 |
| 0.1 | Runtime and CSS paths may be absolute (local plugins) | 8.2 |
| 0.1 | Only instances with data are mounted | 10.2 |
| 0.1 | Cache key includes a hash of the Lattice sources | 8.6 |
| 0.1 | Graph layouts default to Graphviz `dot` left to right | 8.3 |
| 0.1 | Id-less components are named `cN` | 6.2 |
| 0.1 | Diagnostics LT048 to LT050 | 12 |
| 0.2 | The diff component is `diff-steps` | 3.13, 8.8 |
| 0.2 | Per-instance libraries (`RenderResult.requires`) | 8.4 |
| 0.2 | Vega-Lite and Plotly backends for `plot` | 8.8 |
| 0.2 | Image embedding, LT051 | 11.1 |
| 0.2 | Directory output | 11.4 |
| 0.2 | Overview map layout in the deck JSON | 11.2 |
| 0.2.1 | Columns contain their content | 3.8 |
| 0.2.2 | Presenter view described as implemented (no scrubber) | 7.5 |
| 0.2.2 | Built-in themes only, LT052; LT045 and LT032 implemented; `destroy` called on page unload | 2.2, 8.7, 11.1, 10.2 |
| 0.3 | Tree and grid traces, `tree-anim` and `grid-anim`; tree layouts per frame | 8.8, 9.1, 9.4 |
| 0.3 | Presenter view: preview of the next position and step scrubber | 7.5, 10.4 |
| 0.3 | PDF export, `pdf` slide attribute, LT053 | 3.5, 11.5, 12 |
| 0.4 | Basic block versioning: `bbv-anim`, `bbv-cfg`, the `.bbv` program syntax, SBBV and ΛV frames, block bands layout | 8.8, 9.1, 9.5 |
| 0.4 | `code`: `meta=` picks the leader's meta key; `file="lattice:..."` reads a bundled file | 8.8 |
| 0.5 | Abstract interpretation: `abstract-interp-anim`, intervals in types, parameter annotations and comparison tests in `.bbv` programs | 8.8, 9.5, 9.6 |
| 0.6 | PREV with an empty history goes to the structural predecessor | 7.1, 7.2 |
| 0.6 | SKIP and SKIP-DETOUR events and the `skip-forward`, `skip-back`, `last-step` and `skip-detour` bindings; `Shift+KEY` notation | 7.2, 7.6 |
| 0.6 | Keybindings section of the presenter view | 7.5 |
| 0.6 | Detour steps (`detour ID [blocking]` timeline lines, `at=` and `blocking=` on detours), LT054, `stepDetours` | 3.9, 3.15, 6.4, 7.2, 11.2, 11.5, 12 |
| 0.6 | The `arrow` component | 8.8, 8.9 |
| 0.7 | Rich text in the versioning and abstract interpretation captions, nodes and panel; `--lt-type` and `--lt-range` theme tokens | 9.5, 9.6 |
| 0.7 | The drawing keeps its `height` and a hidden panel takes no space when an animation sits in a narrow column | 9.5 |
| 0.7.1 | Scheme highlighting: binding sites are variables, named-let names are procedures | 3.13 |
| 0.7.2 | User manual (`user_manual/manual.md`, a deck built and tested with the examples); no rule changes | 2.1 |
| 0.8 | `badge=step` and `badge=next` on detours: a badge shown according to its detour step; LT055 | 3.9, 4, 6.4, 10.4, 11.5, 12 |
| 0.9 | Placed badges: the `::detour-badge` leaf directive, several badges per detour with their own label and mode; LT056; an include in a list item or a quote is LT034 | 2.3, 3.2, 3.9, 4, 10.4, 12 |
| 0.10 | `.reveal-with`: a block revealed on the same step as the previous fragment; LT057 | 3.12, 12 |
| 0.11 | Named segments in code (markers in comments, `markers` option, segment highlights), `RenderResult.anchors`, LT058 for ids used twice on a slide | 3.13, 8.4, 8.8, 8.10, 12 |
| 0.11 | Arrow anchors (`from_anchor`, `to_anchor`) and cubic arrow curves; arrows at code segments | 8.8, 8.9 |
| 0.12 | `code-morph`: code whose text changes between positions, with versions (a language per version) or segment replacements; LT059, LT060 | 3.13, 8.8, 8.10, 8.11, 12 |
| 0.12 | The `lt-relayout` event; arrows re-measure when a component moves content | 8.9, 10.4 |
| 0.12 | Cached render results keep their anchors and warnings (LT058 and component warnings on cached builds) | 8.6 |
| 0.12.1 | A scrolled code block brings its highlight into view (stated, and fixed: it scrolled too far); the PDF keeps scroll positions | 8.8, 11.5 |
| 0.13 | Intervals in SBBV and ΛV (`intervals`, `thresholds`, `fixnum_bits`; merges widen), the `vec` type, vector lengths as symbolic bounds, the vector primitives, overflow-checking operators decided by intervals, intervals as tie-breakers of the heuristics, `checks` counts every test left; the `thesis` thresholds are now `machine` | 8.8, 9.5, 9.6 |
| 0.15 | Enlarged elements: `clickable` and `clickable_show` on the versioning drawings, the controller hook `zoom` and `api.zoom`, a card shared by the presenter and audience windows | 7.5, 7.7, 8.8, 9.5, 10.1, 10.3, 10.4 |
| 0.14 | Container fences: a bare closing fence closes the innermost container, whatever the colons (nested containers may all use `:::`); fences in code blocks are skipped; named closing fences `::: /NAME`; LT061, LT062 | 3.2, 12 |
| 0.16 | Arrows at list items (`LIST[N]`, nested and from the end) and at their markers (the `bullet` anchor); the box of a list item leaves out its nested lists; text markers for bullet lists; LT063 | 8.8, 8.9, 12 |
| 0.17 | Timeline sugar: open ranges `..STOP` from the current position (`reveal ..end`, `trace ..+2`), positions counted from the last (`end-N`), strides (`by K`), several ranges on one line in lockstep (LT031 now means ranges of different lengths) | 3.15, 6.3, 12 |
| 0.18 | Highlights in `code-morph`: `highlight` per version, per step and as the default of every position, the keyword `changed`; `highlight` in a `diff-steps` version is LT022 | 8.8, 8.10, 8.11 |
| 0.19 | Attribute lines inside list items: a nested list revealed item by item; LT059 ignores positions whose highlights differ | 3.12, 8.11, 12 |
| 0.20 | Widening thresholds may name `machine`, `sign`, `maxfix` and `minfix` in a list; the predicates of a `prims` option may be tested in an `if` | 8.8, 9.5, 9.6 |
| 0.21 | `vector_bounds` (symbolic vector bounds can be turned off); threshold names with an offset (`maxfix-1`) | 8.8, 9.5, 9.6 |
| 0.22 | `null` steps of `arrow`: a position without an arrow | 8.8, 8.9 |
| 0.23 | Three quick presses of `skip-forward` or `skip-back` play to the last or first step of the slide | 7.2, 7.5, 7.6 |
| 0.24 | Columns that change width: the `width` timeline cue, collapsed columns (`width=0`), `duration` on `columns`, the columns track, `lt-relayout` with `follow`; an invalid column width is LT064 | 3.8, 3.15, 4, 6.1, 6.3, 8.9, 10.4, 11.2, 12 |
| 0.25 | `panel_at` on the animation components: the panel beside or under the drawing at any width | 8.8, 9.5 |
