# Implementation report: the help button (Lattice 0.39.0, 2026-10-23)

The report of 0.38.0 is in `archive/implementation-report-2026-10-12.md`.

Olivier's request: an optional flag at build time that adds a small, faint question mark button in the top right corner, off by default and only on non-mobile devices (phones already have one). A click shows an overlay like the mobile one, with the basic keybindings: those of the mobile version plus `p` for the presenter view and more controls, without the tour and start of the deck buttons. The overlay has a close button and also closes on a click outside it.

## 1. What was built

- **The flag** (`model.py`, `emit.py`): `help_button: true` in the front matter (default `false`), carried to the page as `helpButton` in the deck JSON. A front matter key rather than a CLI option, like `touch`, so that `build`, `serve` and `pdf` agree without a flag each.
- **The button and its card** (`lattice.js`, `buildHelpButton`): created at boot only when the deck asks for it and the window is neither the presenter window (its panel lists every key) nor a passive one; a deck without the flag has the same DOM as before. The card lists, as bound by the deck (`deck.keys`, so `keys:` overrides show): the actions of the deck's gestures in the order of the touch help sheet (next, previous, enter detour, return, next and previous checkpoint, go-to, overview, undo with the default gestures), then the click (links, badges, branch options and blocks, the counterpart of the sheet's "Tap"), then `p`, "Presenter view and more controls". It has no tour or start buttons. It closes with Close, Escape, a click on the backdrop (outside the card), which does nothing else, and when touch mode turns on.
- **Only off touch mode**: the button and its card are under `html.lt-touch ... {display:none}`, so the rule of spec 7.8 decides alone which **?** a window shows; `?touch` on a desktop shows the touch one, and a tablet that gains a trackpad gets the desktop one.
- **Looks** (`lattice.css`): a 26 px round button at 35 % opacity, opaque when hovered, focused or open; the card takes the sheet's look (theme custom properties only), anchored under the button, over a light scrim. Print mode hides both.

## 2. Tests and verification

- `tests/test_touch.py`: `test_help_button_on_a_desktop` (absent without the flag; position, size and opacity; the rows and the deck's own binding of `next`; Close, Escape, a click outside over a wiki link that leaves the slide unchanged; keys acting after it closes) and `test_help_button_never_in_touch_mode_or_other_windows` (a phone shows the touch **?** only; an emulated touchscreen laptop turning into a tablet hides the button and closes the card, and back; none in `?presenter`, `?preview`, `?print`). `tests/test_output.py`: `helpButton` in the deck JSON, false by default.
- Screenshots of the open card in the default and dark themes at 1280 by 720.
- `pytest -rs`: 481 passed, 1 skipped (Firefox, not installed here), 1 failed: the manual's `plot-sources` in `test_layout.py`, as since 0.34.0 (it fails the same way without this change; the baseline run before the change gave 479 passed, the same skip and the same failure). The new manual rows first pushed `front-matter` 14 px below the body: `help_button` has its own row and the meaning of `start` was shortened to keep the slide in one page. Examples and the manual rebuilt; `scripts/check_docs.py`: 0 problems.
- Docs: spec 2.2, 7.9 (new), 11.2 and 15; README (Navigation); the manual (front matter table, `presenting-keys`, and `help_button: true` in its own front matter so the button is shown live); design report (section 3.17, decision 49, roadmap); `docs/USER_SKILL.md` (front matter row, feature map); `docs/SKILL.md` (runtime structure, the touch and output suites); version 0.39.0.

## 3. Left open

- `?` is not bound to the card: a deck may already use the key, and the request asked for a button.
- The card lists the gesture actions and the presenter view only; the digit keys of branch options, `t` and End/Home stay in the presenter's Keybindings section.
