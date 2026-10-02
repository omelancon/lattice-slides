# Implementation report: visuals of the versioning animations (Lattice 0.7.0, 2026-10-02)

Two display bugs and one formatting feature on the `bbv-anim`, `bbv-cfg` and `abstract-interp-anim` components. The rules live in the spec (sections cited); the rationale is in the design report (3.13, decision 16).

## 1. The cropped CFG (example 07, slide `find-cfg`)

Reported as "the CFG flows outside the bottom border". Reproduced in Chromium and Firefox at 1280x720; the example's `height=470` was right and no warning was needed. Two causes in `lattice.css`, both fixed:

- Under 760 px of container width the animation panel switches to a column (`@container` rule). The canvas, a flex item of that column with `flex: 1 1 0%`, then ignored its `height` and took the natural height of its SVG (777 px for `find`). The canvas is now `flex: none` in column mode, and so is the panel (its row-mode `flex-basis` had become a 174 px height).
- `.lt-ga-panel { display: flex }` overrode the user-agent `[hidden] { display: none }`, so a panel with nothing to show (every `bbv-cfg`, every animation without `panel:`) still took 150 px of width in a row and 174 px of height in a column. `.lt-ga-panel[hidden] { display: none }` added.

`tests/test_layout.py` now also flags anything painted below the slide body, at the first and last step of every example slide. It found two example excesses, `power4-lv` (`height=520`) and `square-ops` (`height=500`), whose captions sat under the footer; both lowered to 470. Spec 9.5 states the narrow-column behaviour.

## 2. Origin colours lost after stepping back (slide `find-sbbv`)

Reported as "only A1 is coloured in the animation"; confirmed by Olivier as happening on the second display of a version. Cause in `bbv.js`: a hidden node gets its class attribute overwritten (`lt-bbv-node lt-gone`), which dropped `has-origin`, and the class rebuilt when the node reappears copied `has-origin` only from the classes it currently had. The node record now remembers whether it has an origin colour and the class is rebuilt from that, hidden or not. `test_bbv_runtime_steps_both_ways` goes back to step 0 and forward again and checks every visible node keeps `has-origin`.

## 3. Rich text (spec 9.5, report 3.13, decision 16)

`lattice/bbv/rich.py` defines a backtick markup (`` `op:...` ``, `tag`, `v`, `var`, `ty`, `code`, `rm`), helpers to build it (`op`, `tag`, `ver`, `var`, `ty`, `code`, `struck`, `binding`, `context`, `join`) and `plain` to strip it. `trace.py` writes every caption as "operation badge, version chips, details" (`INSTRUCTION_OPS`, `ABSINT_OPS` name the badges of instruction frames); the instruction notes of `sbbv.py`, `lv.py` and `absint.py` use the same helpers. `bbv.js` renders the markup as spans in the caption, draws context lines as `tspan`s (`;;`, the name padded to the longest of the node, the type, the interval), colours the keywords and `[i]` indices of code lines, and renders its own panel (version labels as chips, `∪` and `∇` steps of a widening chain marked). `lattice.css` holds the `lt-rc-*` classes; both themes gain `--lt-type` and `--lt-range`. `layout.py` sizes nodes on the padded context lines (`context_width`), and `AbstractTrace` keeps the longest name and the longest type of each context slot separately for sizing.

Captions are still strings: frame stores, the presenter preview and the PDF export are unchanged; tooltips show the plain lines.

## 4. Verification

Suite: 103 passed in Chromium (`test_rich_markup_round_trips` added; caption assertions of `test_bbv.py` rewritten on the markup and on `plain`). Firefox checked by hand for the fixed CFG slide, the node `tspan`s and the chips. Examples rebuilt; screenshots of `find-cfg`, `find-sbbv`, `one-block-steps`, `sum-to-n-ai`, `fact-lv` and `power4-lv` checked in both engines, plus the presenter view and a PDF export of the short tour. `check_docs.py`: 0 problems.

## 5. Documentation touched

Spec 8.8 (`show` default), 9.5 (rich text, narrow columns), 9.6 (operations), 15; README (version, `bbv-anim` row); report (version, 3.13, roadmap v0.7, decision 16); SKILL (structure, invariants, test table, two pitfalls); todo.

## 6. Left open

See `todo.md`: a look at the result on Olivier's screen and in the dark theme; the `height` of `one-block-steps`; a `code` panel key if a slide ever needs the specialized code of the current version without drawing code in every node.

## 7. Addendum, 0.7.1: Scheme highlighting

Pygments' Scheme lexer types every symbol that follows `(` as `Name.Function`, so in `(let loop ((i 0) (sum 0)) ...)` the bound variables took the call colour and `loop` took the variable colour at its binding and the call colour at its calls. `components/scheme.py` adds a Pygments filter (a stack of open lists with a role each) that retypes binding sites as `Name.Variable` (bindings of `let`, `let*`, `letrec`, `letrec*`, `do`, `fluid-let`, formals of `let-values` and `let*-values`, parameters of `lambda`, `define-values` and `case-lambda` clauses) and the name of a named `let` as `Name.Function`; `(define (f ...))` already had the call colour and keeps it, per Olivier's choice. `lexer_for(lang)` in that module is now the one place that builds a lexer for `code`, `code-steps` and `diff-steps`. Scheme only; Racket and Common Lisp are untouched. Spec 3.13 and 15; `test_scheme_binding_sites_are_variables`.

## 8. Addendum, 0.7.2: the user manual

`user_manual/manual.md` is the user documentation, written as a Lattice deck (64 slides) and compiled to `user_manual/manual.html`: chapters on the main path (commands, front matter, slides, content, the graph, steps and timelines, components, traces, compiler animations, presenting, output, themes, extending, diagnostics), a branch into the component families, detours for a live detour demo and for the complete diagnostic table, a `quick` tour, and the overview as a table of contents. Every component is used live with self-contained sources in the folder (`traces.py`, `search.py`, `recursion.py`, `versions/`, `data/`, `programs/`) and a plugin tutorial (`lattice_plugins.py` with the static `checklist` and the animated `stack-anim`, `call_stack.js`, `plugins.css`, which also defines the manual's `.dense` slide class). The manual is built by `scripts/build_examples.py`, must pass `lattice check --strict` and use every component (`test_user_manual_builds_without_warnings`), is visited by the layout test, and `check_docs.py` checks its paths and version. README, SKILL.md, the report's roadmap and spec 15 point to it.

## 9. Addendum, 0.8.0: badges that wait for their detour step

The motivating slide reveals a code block at step 1 and has two detour steps after it (`at=1` on both detours). Its badges were visible from step 0, so the slide announced both questions in advance; `badge=false` hid them for good, and a `{.reveal}` line before a `::: detour` is ignored (the container path of `BodyBuilder` drops the pending attributes of a detour).

- **Syntax (spec 3.9).** `badge` accepts `step` and `next` beside the booleans (case-insensitive, like them). With `step` the badge appears at the step before the detour's first detour step and stays; with `next` it shows only at the step before each of its detour steps. Anything else is LT009, as before. `Detour.badge_mode` holds the mode; `badge` stays `true`.
- **LT055 (spec 12).** Either value on a detour that is not a detour step of its origin (no `at=`, not named by a `detour` timeline line). Checked at the end of `compile_steps`; a detour with `at=` is left out, since a bad `at` is already LT054 and one mistake should give one error.
- **Build.** `detour_badge` adds `data-lt-badge="step|next"` to the button. No step index is stamped: badges are rendered before steps are compiled, and the deck JSON already has `stepDetours`, so the JSON is unchanged (spec 11.2 untouched).
- **Runtime (spec 10.4).** `applyStep` in `lattice.js`, next to the reveal toggle, finds the detour steps of each `[data-lt-badge]` in the slide's `stepDetours` and toggles `lt-hidden` (visibility, so the badge keeps its place and cannot be clicked). The key, Down, links and the overview still enter the detour. The presenter preview and print mode go through the same `render` path and follow; the PDF prints a badge as it is at the printed step (spec 11.5). The footer's Down hint, which names the slide's first detour, is left out while that detour's badge is hidden; without that, the footer would still announce the first question.
- **Tests.** `test_badge_step_modes` and `test_badge_step_errors` (`test_steps.py`: modes, unchanged step table, HTML attribute, timeline detour steps, LT055, no LT055 after LT054, LT009, case); `test_badges_wait_for_their_detour_step` (`test_runtime.py`: a reveal and two detour steps, `next` and `step` modes and a plain badge, every step forward through both detours and backward with Left, the hash, the Down hint, the key of a hidden badge, the presenter preview). The browser test fails on the old runtime.
- **Manual.** New slide "Badges that wait for their turn" after "Timelines" (the manual now has 67 slides with its two new detour slides), live (the motivating case, one detour per mode); a phrase on "Detours", the LT055 row, the cheat sheet row. Building it ran into a parser limitation, recorded as a SKILL.md pitfall and in `todo.md`: a `:::` line quoted inside a fenced block closes an enclosing `:::` container.
- **Version.** 0.8.0 (a new attribute value is a feature). Spec 3.9, 4, 6.4, 10.4, 11.1 (generator), 11.5, 12, 15; README syntax table; report 3.12, roadmap, decision 17; SKILL (structure, invariants, test table, pitfall); todo.
- **Verification.** Suite green (108 tests), examples and manual rebuilt, `lattice check --strict` clean on the manual, screenshots of the new slide at each step and of the touched manual slides at 1280x720 in Chromium, `check_docs.py` clean.
