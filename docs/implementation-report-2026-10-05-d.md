# Implementation report: sub-bullets revealed one by one, LT059 and highlights (Lattice 0.19.0, 2026-10-05)

Two small changes found while preparing the background slide of Olivier's defense (a `code-morph` whose last positions only move a highlight, beside bullets with sub-bullets that appear one per step). Both were agreed with Olivier before implementation. The rules are in spec 3.12, 8.11 and 12 (with 15); the rationale is decision 28. Fourth release of the day, hence `-d`.

## 1. What was found first

- A `{.reveal}` line inside a list item was rendered as literal text: attribute lines were read only between the top-level blocks of a slide or a container (`render_groups`), and a revealed list numbers its top-level items only. Sub-bullets could appear only with their parent.
- A morph that repeats its text to move a highlight (positions 1 and 2, then 3 to 6 of the defense slide) produced one LT059 warning per repetition ("positions N and N+1 show the same code"), although the positions differ.

## 2. What was built

- **Attribute lines inside list items** (`body.py`): `item_attr_lines` scans the paragraphs inside the items of a list group. A paragraph whose last line is an attribute block and that is directly followed by another block of the same item gives that block the attributes (the line is removed, the paragraph's inline content parsed again); a paragraph that is only the attribute line is removed; a paragraph whose first line is an attribute block followed by text takes the attributes itself, as at the top level. `plain` then walks the list in document order: blocks with attributes get them (`wrapper_attrs`, so `reveal-with`, ids and classes behave as elsewhere), a nested list marked `reveal` gets one fragment per item, and so does the list itself when it is revealed. An item is numbered before the items nested in it. A line not followed by a block of the item stays text. The tight form (the line right after the item's text, which CommonMark reads as part of the item's paragraph) keeps the list tight.
- **LT059** (`components/morph.py`): the warning is emitted after the highlights are resolved, and only when two consecutive positions have the same text, language, undimmed rows and highlight layer.
- **Docs**: spec 3.12 (a nested example and the rule), 8.11 and 12 (LT059), 15 (0.19 row); README (reveal row, version); manual: "Fragments: reveal step by step" shows a nested list in its example and reveals two sub-bullets live (the slide is now `.dense` to fit); design report (roadmap v0.19, decision 28); SKILL.md (structure, tests table); todo; the 0.18.0 report copied to `docs/archive/`. Version 0.19.0.

## 3. Verification

- `pytest -rs`: 281 passed, no skips, in Chromium (2 new tests). `test_parsing.py::test_reveal_inside_list_items`: numbering in document order with a nested revealed list (with a class), an attribute line followed by text in an item, `reveal-with` on a nested list, a line that stays text, a nested reveal inside a list that is not revealed, and the line as a paragraph of its own. `test_morph.py::test_lt059_ignores_positions_with_other_highlights`.
- The manual's "Fragments" slide looked at in Chromium at its middle and last steps; the layout test passes on it. The defense slide built without warnings and looked at at each of its eight steps. `check_docs.py` and `lattice check --strict` on the manual pass.

## 4. Not verified, and left open

- Attribute lines inside block quotes, and before a fenced block inside an item, are unchanged (todo).
- `docs/implementation-report-2026-10-05-c.md` is copied to `docs/archive/`; the copy left in `docs/` needs a `git rm`.
