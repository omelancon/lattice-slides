"""Touch input (spec 7.8) in an emulated phone, and its absence everywhere else. Skipped without Playwright.

Touches are sent through the Chrome DevTools Protocol (Input.dispatchTouchEvent), because Playwright's touchscreen
only taps.
"""
import time

import pytest

from lattice.cli import main

pw = pytest.importorskip("playwright.sync_api")

VERSIONS = "".join(f'  - code: "a = {k}\\n"\n' for k in range(4))
DECK = (
    "---\ntitle: Touch\ntours:\n  short: [intro, end]\n---\n"
    "# Intro {#intro}\nHello, see [[end]].\n\n::: notes\nSay hello, $x^2$.\n:::\n\n"
    "# Many {#many}\n{.reveal}\n- a\n- b\n- c\n\n"
    "```diff-steps {#d lang=python}\nversions:\n" + VERSIONS + "```\n\n"
    "```timeline\nreveal ..2\nd ..end\n```\n\n"   # checkpoints 2 and 5 (spec 6.5)
    "# Dijkstra {#dijkstra}\nA slide with a detour.\n\n::: detour {#heaps}\n# Heap what {#heap-what}\n:::\n\n"
    "# End {#end}\n"
)
PHONE = {"viewport": {"width": 844, "height": 390}, "has_touch": True, "is_mobile": True, "device_scale_factor": 2}
DESKTOP = {"viewport": {"width": 1280, "height": 720}}


def build(tmp_path, text=DECK, name="talk"):
    src = tmp_path / f"{name}.md"
    src.write_text(text)
    out = tmp_path / f"{name}.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    return out


class Finger:
    """Touches sent to a page through CDP."""

    def __init__(self, ctx, page):
        self.page = page
        self.cdp = ctx.new_cdp_session(page)

    def send(self, kind, pts):
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [
            {"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})

    def tap(self, x, y, fingers=1):
        self.send("touchStart", [(x, y + 60 * k) for k in range(fingers)])
        self.send("touchEnd", [])

    def double_tap(self, x, y):
        self.tap(x, y)
        time.sleep(0.08)
        self.tap(x, y)
        self.page.wait_for_timeout(400)

    def swipe(self, x0, y0, x1, y1, fingers=1):
        offsets = [(0, 0), (0, 40)][:fingers]
        self.send("touchStart", [(x0 + a, y0 + b) for a, b in offsets])
        for k in range(1, 6):
            x, y = x0 + (x1 - x0) * k / 5, y0 + (y1 - y0) * k / 5
            self.send("touchMove", [(x + a, y + b) for a, b in offsets])
            time.sleep(0.02)
        self.send("touchEnd", [])
        self.page.wait_for_timeout(450)

    def long_press(self, x, y):
        self.send("touchStart", [(x, y)])
        self.page.wait_for_timeout(800)
        self.send("touchEnd", [])
        self.page.wait_for_timeout(350)


def run(fn):
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                fn(browser)
            finally:
                browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise


def open_page(browser, url, opts):
    ctx = browser.new_context(**opts)
    page = ctx.new_page()
    errors, warnings = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
    page.goto(url)
    page.wait_for_timeout(500)
    return ctx, page, errors, warnings


def cur(page):
    return page.evaluate("Lattice.state().cur")


def touch_mode(page):
    return page.evaluate("document.documentElement.classList.contains('lt-touch')")


def controls(page):
    return page.evaluate("document.querySelectorAll('.lt-tc').length")


def go(page, slide, step=0):
    page.evaluate(f"location.hash = '#/{slide}/{step}'")
    page.wait_for_timeout(400)


def test_gestures_on_a_phone(tmp_path):
    """Spec 7.8: each default gesture runs its action; the help sheet shows once, with the tour and start buttons;
    the notes sheet follows the slide."""
    out = build(tmp_path)

    def check(browser):
        ctx, page, errors, _ = open_page(browser, out.as_uri(), PHONE)
        f = Finger(ctx, page)
        assert touch_mode(page)
        assert page.is_visible("#lt-touch-help")  # first load: the help sheet
        rows = page.eval_on_selector_all("#lt-touch-help td:first-child", "ts => ts.map(t => t.textContent)")
        assert rows == ["Swipe left", "Swipe right", "Swipe up", "Swipe down", "Two-finger swipe left",
                        "Two-finger swipe right", "Double tap", "Long press", "Two-finger tap", "Tap"]
        page.click('[data-lt-tc-close="help"]')
        assert page.is_hidden("#lt-touch-help")

        f.swipe(600, 200, 300, 200)
        assert cur(page) == {"slide": "many", "step": 0}
        f.swipe(300, 200, 600, 200)
        assert cur(page) == {"slide": "intro", "step": 0}
        assert page.evaluate("document.scrollingElement.scrollTop + window.scrollX") == 0

        f.double_tap(420, 200)
        assert page.evaluate("!document.getElementById('lt-overlay').hidden && document.activeElement.tagName === 'INPUT'")
        f.tap(5, 380)  # the backdrop closes the search
        page.wait_for_timeout(300)
        assert page.is_hidden("#lt-overlay")

        f.long_press(420, 200)
        assert page.evaluate("!!document.querySelector('.lt-overview')")
        f.swipe(420, 300, 420, 100)  # while the overview is open, a swipe only scrolls it
        assert page.evaluate("!!document.querySelector('.lt-overview')") and cur(page)["slide"] == "intro"
        f.long_press(420, 200)
        assert page.is_hidden("#lt-overlay")
        f.swipe(600, 200, 300, 200)  # the finger lifted over the closing overview leaves no stale gesture
        assert cur(page)["slide"] == "many"

        go(page, "dijkstra")
        f.swipe(420, 300, 420, 80)
        assert cur(page)["slide"] == "heap-what"
        f.swipe(420, 80, 420, 300)
        assert cur(page)["slide"] == "dijkstra"

        go(page, "many")
        f.swipe(600, 150, 300, 150, fingers=2)
        page.wait_for_timeout(300)
        assert cur(page) == {"slide": "many", "step": 2}
        f.swipe(600, 150, 300, 150, fingers=2)
        page.wait_for_timeout(300)
        assert cur(page) == {"slide": "many", "step": 5}
        f.swipe(300, 150, 600, 150, fingers=2)
        page.wait_for_timeout(300)
        assert cur(page) == {"slide": "many", "step": 2}
        for _ in range(4):  # steps 3, 4 and 5, then the next slide
            f.swipe(600, 200, 300, 200)
        assert cur(page)["slide"] == "dijkstra"
        f.tap(400, 150, fingers=2)
        page.wait_for_timeout(300)
        assert cur(page) == {"slide": "many", "step": 5}  # undo: back where the slide was left

        # the notes of the current slide, math rendered, following navigation
        go(page, "intro")
        page.click('[data-lt-tc="notes"]')
        assert page.is_visible("#lt-touch-notes")
        assert page.text_content(".lt-tc-notes-title") == "Intro"
        assert page.evaluate("!!document.querySelector('.lt-tc-notes-body .katex')")
        f.swipe(600, 200, 300, 200)
        assert page.text_content(".lt-tc-notes-title") == "Many"
        assert "No notes" in page.text_content(".lt-tc-notes-body")
        page.click('[data-lt-tc="help"]')  # one sheet at a time
        assert page.is_hidden("#lt-touch-notes") and page.is_visible("#lt-touch-help")

        # the buttons of the help sheet: cycle tours, start of the deck
        assert page.text_content('[data-lt-tc-act="tour"]') == "Tour: off"
        page.click('[data-lt-tc-act="tour"]')
        assert page.text_content('[data-lt-tc-act="tour"]') == "Tour: short"
        assert page.evaluate("Lattice.state().tour") == "short"
        page.click('[data-lt-tc-act="tour"]')
        assert page.evaluate("Lattice.state().tour") is None
        page.click('[data-lt-tc-act="home"]')
        page.wait_for_timeout(300)
        assert page.is_hidden("#lt-touch-help")
        assert page.evaluate("Lattice.state()")["H"] == [] and cur(page) == {"slide": "intro", "step": 0}

        # a tap on a link still follows it, and is not the first half of a double tap
        f.tap(*page.evaluate("""(() => { const r = document.querySelector('#s-intro a[data-lt-link]').getBoundingClientRect();
          return [r.x + r.width / 2, r.y + r.height / 2]; })()"""))
        page.wait_for_timeout(300)
        assert cur(page)["slide"] == "end"
        assert page.is_hidden("#lt-overlay")

        # the help sheet shows only once
        page.reload()
        page.wait_for_timeout(500)
        assert touch_mode(page) and page.is_hidden("#lt-touch-help")
        assert not errors, errors

    run(check)


# Chromium's touch emulation always reports a coarse pointer and no hover, so a laptop with a touchscreen (touches,
# but a fine primary pointer) is emulated by answering the query of spec 7.8 from the page; __phone(on) changes the
# answer and notifies, as when a tablet gains or loses a trackpad.
FAKE_QUERY = """(() => {
  const real = window.matchMedia.bind(window);
  let phone = false; const listeners = [];
  const mql = { get matches() { return phone; }, media: "(hover: none) and (pointer: coarse)",
    addEventListener: (t, f) => listeners.push(f), removeEventListener() {}, addListener: (f) => listeners.push(f) };
  window.matchMedia = (q) => (q.replace(/\\s+/g, " ").trim() === mql.media ? mql : real(q));
  window.__phone = (on) => { phone = on; listeners.forEach((f) => f({ matches: on })); };
})()"""


def test_no_touch_controls_off_phones(tmp_path):
    """Spec 7.8: on a desktop, and on a laptop with a touchscreen (its primary pointer is fine), touch mode is off:
    no class, no controls, and touches do nothing; it follows the query when the device changes."""
    out = build(tmp_path)

    def check(browser):
        ctx, page, errors, _ = open_page(browser, out.as_uri(), DESKTOP)
        assert not page.evaluate("matchMedia('(hover: none) and (pointer: coarse)').matches")
        assert not touch_mode(page) and controls(page) == 0
        page.keyboard.press("ArrowRight")
        assert cur(page) == {"slide": "many", "step": 0}
        assert not errors, errors
        ctx.close()
        ctx = browser.new_context(**DESKTOP, has_touch=True)
        ctx.add_init_script(FAKE_QUERY)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(out.as_uri())
        page.wait_for_timeout(500)
        f = Finger(ctx, page)
        assert not touch_mode(page) and controls(page) == 0
        f.swipe(900, 300, 300, 300)
        f.long_press(600, 300)
        f.double_tap(600, 300)
        assert cur(page) == {"slide": "intro", "step": 0} and page.is_hidden("#lt-overlay")
        page.evaluate("__phone(true)")  # becomes a tablet
        assert touch_mode(page) and page.is_visible("#lt-touch-help")
        page.click('[data-lt-tc-close="help"]')
        f.swipe(900, 300, 300, 300)
        assert cur(page) == {"slide": "many", "step": 0}
        page.evaluate("__phone(false)")  # a trackpad again: the controls hide, gestures stop
        assert not touch_mode(page) and not page.is_visible("#lt-touch-bar")
        f.swipe(900, 300, 300, 300)
        assert cur(page) == {"slide": "many", "step": 0}
        assert not errors, errors
        ctx.close()

    run(check)


def test_touch_overrides_and_passive_windows(tmp_path):
    """Spec 7.8: `?touch` and `?touch=0` force touch mode on or off; `touch: false` turns it off on a phone; the URL
    wins over the front matter with a warning; the presenter window has no Notes button; the preview and print
    windows never have touch mode."""
    out = build(tmp_path)
    off = build(tmp_path, DECK.replace("title: Touch", "title: Touch\ntouch: false"), name="off")

    def check(browser):
        ctx, page, errors, _ = open_page(browser, out.as_uri() + "?touch", DESKTOP)
        assert touch_mode(page) and controls(page) > 0
        ctx.close()
        ctx, page, errors, _ = open_page(browser, out.as_uri() + "?touch=0", PHONE)
        assert not touch_mode(page) and controls(page) == 0
        Finger(ctx, page).swipe(600, 200, 300, 200)
        assert cur(page) == {"slide": "intro", "step": 0}
        ctx.close()
        ctx, page, errors, warnings = open_page(browser, off.as_uri(), PHONE)
        assert not touch_mode(page) and controls(page) == 0 and not warnings
        ctx.close()
        ctx, page, errors, warnings = open_page(browser, off.as_uri() + "?touch", PHONE)
        assert touch_mode(page) and controls(page) > 0
        assert any("touch: false" in w for w in warnings)
        assert "?touch" in page.text_content("#lt-flash")
        ctx.close()
        ctx, page, errors, _ = open_page(browser, out.as_uri() + "?presenter", PHONE)  # the panel has the notes
        assert touch_mode(page) and page.locator('[data-lt-tc="notes"]').count() == 0
        assert page.locator('[data-lt-tc="help"]').count() == 1
        page.click('[data-lt-tc-close="help"]')
        Finger(ctx, page).swipe(500, 200, 200, 200)
        assert cur(page) == {"slide": "many", "step": 0}
        assert not errors, errors
        ctx.close()
        for query in ("?preview&touch", "?print&touch"):
            ctx, page, errors, _ = open_page(browser, out.as_uri() + query, PHONE)
            assert not touch_mode(page) and controls(page) == 0
            assert not errors, errors
            ctx.close()

    run(check)


def test_gestures_from_front_matter_and_rebound_keys(tmp_path):
    """Spec 7.8: `gestures` changes what a gesture does; a gesture runs an action whatever key the deck binds to it."""
    text = DECK.replace("title: Touch", "title: Touch\nkeys: {goto: '/', overview: O}\n"
                        "gestures: {double-tap: none, long-press: goto, two-finger-tap: overview}")
    out = build(tmp_path, text)

    def check(browser):
        ctx, page, errors, _ = open_page(browser, out.as_uri(), PHONE)
        f = Finger(ctx, page)
        rows = page.eval_on_selector_all("#lt-touch-help tr", "ts => ts.map(t => t.textContent)")
        assert not any(r.startswith("Double tap") for r in rows)
        assert "Long pressGo to a slide" in rows
        page.click('[data-lt-tc-close="help"]')
        f.double_tap(420, 200)
        assert page.is_hidden("#lt-overlay")
        f.long_press(420, 200)  # goto, although its key is now "/"
        assert page.evaluate("!!document.querySelector('.lt-goto')")
        f.long_press(420, 200)  # the gesture bound to goto closes it
        assert page.is_hidden("#lt-overlay")
        f.tap(400, 150, fingers=2)
        page.wait_for_timeout(300)
        assert page.evaluate("!!document.querySelector('.lt-overview')")
        assert not errors, errors

    run(check)


ZOOM_DECK = """
# On {#on}
```bbv-anim {#b}
show: [label]
clickable_show: [label, code]
source: |
  function f(x)
  A:  if fixnum?(x) goto B else goto C
  B:  return fx+(x, 1)
  C:  return x
```

# Next {#next}
"""


def test_a_gesture_over_an_enlarged_block_only_closes_it(tmp_path):
    """Spec 7.7 and 7.8: a tap enlarges a block as a click does; a gesture then closes it and does nothing else."""
    out = build(tmp_path, ZOOM_DECK)

    def check(browser):
        ctx, page, errors, _ = open_page(browser, out.as_uri() + "#/on/999", PHONE)
        f = Finger(ctx, page)
        page.evaluate("document.getElementById('lt-touch-help').hidden = true")
        start = cur(page)
        for gesture in ("swipe", "double", "long"):
            box = page.locator("#s-on .lt-bbv-node").first.bounding_box()
            f.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(400)
            assert page.evaluate("Lattice.zoomed()") is not None, gesture
            if gesture == "swipe":
                f.swipe(700, 200, 300, 200)
            elif gesture == "double":
                f.double_tap(60, 60)
            else:
                f.long_press(60, 60)
            page.wait_for_timeout(300)
            assert page.evaluate("Lattice.zoomed()") is None, gesture
            assert cur(page) == start and page.is_hidden("#lt-overlay"), gesture
        assert not errors, errors

    run(check)
