# Implementation report: panel placement (Lattice 0.25.0, 2026-10-06)

The variable panel of an animation sat beside the drawing, and moved under it when the component was narrower than 760 px; nothing else chose its place. Once a column widens (0.24.0), an author may want it elsewhere. The new option `panel_at` puts it beside (`right`) or under (`below`) the drawing at any width; `auto`, the default, keeps the earlier behaviour. The rule is in spec 8.8 (with 9.5 and 15); the rationale is decision 34.

## 1. What was built

- **Components** (`components/animations.py`, `components/bbv.py`):
  - `panel_at: auto | right | below` on `graph-anim`, `array-anim`, `tree-anim`, `grid-anim`, `bbv-anim` and `abstract-interp-anim`; another value is LT021 (pydantic).
  - `panel_root` writes the root element with the class `lt-panel-right` or `lt-panel-below`. `auto` adds nothing, so existing decks render byte for byte as before.
  - `panel_at` is a known option of the versioning components, so it is never passed to a program function.
- **Styles** (`lattice.css`):
  - `below` lays out the main row as a column (the drawing keeps its `height`), and the panel's entries in a row that wraps, as in a narrow component.
  - `right` undoes the narrow-component rules inside the same container query, including the fixed panel width of the versioning drawings.
  - No runtime changed.
- **Docs**:
  - spec 8.8 (the six rows and a paragraph "Panel placement"), 9.5, and a 0.25 row in 15;
  - README (the `graph-anim` row);
  - manual: the options tables of graph animations, versioning and abstract interpretation;
  - design report (roadmap v0.25, decision 34), SKILL.md (tests table), todo;
  - the 0.24.0 report copied to `docs/archive/` and listed in its README;
  - version 0.25.0.

## 2. Verification

- `pytest -rs`: 307 passed, no skips, in Chromium, twice in a row. New tests:
  - `test_output.py`: the classes on each kind of root, `auto` adding none, and LT021 for another value.
  - `test_runtime.py`, `test_panel_at_places_the_panel`: in a narrow column `auto` puts the panel under the drawing and `right` beside it; at full width `below` puts it under the drawing, which keeps its `height`.
- `test_columns_change_width_however_a_step_is_reached` (0.24.0) failed once under the load of the full suite, on a 400 ms move checked within its timing. Its deck now moves for 800 ms, and its waits are longer.
- Screenshots in Chromium of `right` in a narrow column, beside `auto`, and of `below` and `right` on `graph-anim`, `array-anim` and `abstract-interp-anim`, including the defense's `findv` slide.
- Examples and the manual rebuilt; `check_docs.py` and `lattice check --strict` on the manual pass.

## 3. Not verified, and left open

- Only Chromium was available.
- On the defense's `findv` slide, `below` with `height=470` lets the panel and the caption reach the footer: a smaller `height`, or `direction: LR`, is needed there (todo).
- `array-anim` keeps its panel beside the drawing under `auto` even in a narrow column, as before (it never followed the container query); `below` is the way to move it.
- `docs/implementation-report-2026-10-06-c.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
