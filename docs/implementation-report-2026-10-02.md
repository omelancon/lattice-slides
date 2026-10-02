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
