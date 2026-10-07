"""Navigation state machine in a real browser (spec 7.3). Skipped without Playwright."""
import pytest

from lattice.cli import main

pw = pytest.importorskip("playwright.sync_api")

DECK = """
# Intro

# Dijkstra
{.reveal}
- a
- b

::: detour {#heaps}
# Heap what
# Heap ops
:::

# Complexity
"""


def test_spec_trace(tmp_path):
    src = tmp_path / "talk.md"
    src.write_text(DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())

            def press(*keys):
                for k in keys:
                    page.keyboard.press(k)
                return page.evaluate("Lattice.state()")

            s = press("ArrowRight", "ArrowRight", "ArrowRight")
            assert s["cur"] == {"slide": "dijkstra", "step": 2}
            s = press("ArrowDown")
            assert s["cur"]["slide"] == "heap-what" and s["H"][-1]["kind"] == "excursion"
            s = press("ArrowRight", "ArrowRight")  # heap-ops, then back
            assert s["cur"] == {"slide": "dijkstra", "step": 2}
            assert s["H"] == [{"slide": "intro", "step": 0, "kind": "forward"}]
            s = press("ArrowLeft")
            assert s["cur"] == {"slide": "dijkstra", "step": 1}
            s = press("ArrowRight", "ArrowRight")
            assert s["cur"] == {"slide": "complexity", "step": 0}
            s = press("ArrowLeft")
            assert s["cur"] == {"slide": "dijkstra", "step": 2}  # backward lands on the last step
            browser.close()
    except Exception as e:  # browser not installed
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_prev_without_history_walks_the_structure(tmp_path):
    """Spec 7.2, PREV: with an empty history, Left goes to the structural predecessor without recording it."""
    src = tmp_path / "talk.md"
    src.write_text(DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []

            def open_at(hash_):
                page = browser.new_context().new_page()  # a fresh context: no saved history
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(out.as_uri() + hash_)
                return page

            page = open_at("#/complexity/0")
            page.keyboard.press("ArrowLeft")
            s = page.evaluate("Lattice.state()")
            assert s["cur"] == {"slide": "dijkstra", "step": 2} and s["H"] == []  # last step, nothing pushed
            for _ in range(3):
                page.keyboard.press("ArrowLeft")
            s = page.evaluate("Lattice.state()")
            assert s["cur"] == {"slide": "intro", "step": 0} and s["H"] == []
            page.keyboard.press("ArrowLeft")  # the start has no predecessor
            assert page.evaluate("Lattice.state().cur") == {"slide": "intro", "step": 0}
            page.keyboard.press("ArrowRight")  # a forward move records history again
            page.keyboard.press("ArrowLeft")
            s = page.evaluate("Lattice.state()")
            assert s["cur"] == {"slide": "intro", "step": 0} and s["H"] == []
            page = open_at("#/heap-what/0")  # the entry of a detour: back to its origin
            page.keyboard.press("ArrowLeft")
            assert page.evaluate("Lattice.state().cur") == {"slide": "dijkstra", "step": 2}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


SKIP_DECK = "# Intro\n\n# Many\n{.reveal}\n" + "".join(f"- item {i}\n" for i in range(14)) + "\n# Last\n"


def test_skip_keys_play_steps_within_the_slide(tmp_path):
    """Spec 7.2, SKIP: Shift+arrows move ten steps, End goes to the last step, all clamped to the slide."""
    src = tmp_path / "talk.md"
    src.write_text(SKIP_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri() + "#/many/0")

            def settle(expected):
                for _ in range(60):
                    if page.evaluate("Lattice.state().cur") == expected:
                        break
                    page.wait_for_timeout(50)
                return page.evaluate("Lattice.state()")

            page.keyboard.press("Shift+ArrowRight")
            assert page.evaluate("Lattice.state().cur")["step"] < 10  # the steps are played, not jumped
            s = settle({"slide": "many", "step": 10})
            assert s["cur"] == {"slide": "many", "step": 10} and s["H"] == []
            page.keyboard.press("Shift+ArrowRight")
            assert settle({"slide": "many", "step": 14})["cur"] == {"slide": "many", "step": 14}  # clamped
            page.keyboard.press("Shift+ArrowLeft")
            assert settle({"slide": "many", "step": 4})["cur"] == {"slide": "many", "step": 4}
            page.keyboard.press("End")
            assert settle({"slide": "many", "step": 14})["cur"] == {"slide": "many", "step": 14}
            page.keyboard.press("Shift+ArrowRight")  # at the last step: stays on the slide
            page.wait_for_timeout(200)
            assert page.evaluate("Lattice.state().cur") == {"slide": "many", "step": 14}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


BURST_DECK = "# Intro\n\n# Many\n{.reveal}\n" + "".join(f"- item {i}\n" for i in range(40)) + "\n# Last\n"


def test_three_quick_skips_go_to_the_end_of_the_slide(tmp_path):
    """Spec 7.6: three presses of a skip key within a second play to the last (or first) step;
    slower presses, another key in between and auto-repeat keep moving ten steps at a time."""
    src = tmp_path / "talk.md"
    src.write_text(BURST_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri() + "#/many/0")

            def settle():
                """The position once playback has stopped (unchanged for 300 ms)."""
                last = None
                for _ in range(100):
                    cur = page.evaluate("Lattice.state().cur")
                    if cur == last:
                        return cur
                    last = cur
                    page.wait_for_timeout(300)
                return last

            def press(*keys):
                for k in keys:
                    page.keyboard.press(k)

            press("Shift+ArrowRight", "Shift+ArrowRight", "Shift+ArrowRight")
            assert page.evaluate("Lattice.state().cur")["step"] < 40  # the steps are played, not jumped
            assert settle() == {"slide": "many", "step": 40}
            assert page.evaluate("Lattice.state().H") == []  # never leaves the slide nor touches history
            press("Shift+ArrowLeft", "Shift+ArrowLeft", "Shift+ArrowLeft")
            assert settle() == {"slide": "many", "step": 0}

            # slow presses: each one moves ten steps (the first and third are more than a second apart)
            for _ in range(3):
                press("Shift+ArrowRight")
                settle()
            assert settle() == {"slide": "many", "step": 30}

            # a direction change or another key in between starts the count again
            page.goto(out.as_uri() + "#/many/20")
            page.reload()
            press("Shift+ArrowRight", "Shift+ArrowLeft", "Shift+ArrowRight")
            assert 0 < settle()["step"] < 40
            page.goto(out.as_uri() + "#/many/0")
            page.reload()
            press("Shift+ArrowRight", "ArrowRight", "Shift+ArrowRight", "Shift+ArrowRight")
            assert settle()["step"] < 40

            # holding the keys: the auto-repeat is not a quick succession of presses
            page.goto(out.as_uri() + "#/many/0")
            page.reload()
            page.keyboard.down("Shift")
            for _ in range(3):
                page.keyboard.down("ArrowRight")  # repeat=true after the first
            page.keyboard.up("ArrowRight")
            page.keyboard.up("Shift")
            assert settle()["step"] < 40
            press("Shift+ArrowRight", "Shift+ArrowRight", "Shift+ArrowRight")  # three real presses still work
            assert settle() == {"slide": "many", "step": 40}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


DETOUR_STEP_DECK = """
# Intro

# Dijkstra
{.reveal}
- a
- b
- c

::: detour {#heaps at=1}
# Heap what
# Heap ops
:::

# Blocked
{.reveal}
- a
- b
- c
- d

::: detour {#wall at=1 blocking=true}
# Inside the wall
:::

# Complexity
"""


def test_detour_step_enters_and_returns(tmp_path):
    """Spec 6.4: arriving on a detour step with Right enters the detour; back, the next Right steps on."""
    src = tmp_path / "talk.md"
    src.write_text(DETOUR_STEP_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())

            def press(*keys):
                for k in keys:
                    page.keyboard.press(k)
                return page.evaluate("Lattice.state()")

            assert press("ArrowRight", "ArrowRight")["cur"] == {"slide": "dijkstra", "step": 1}
            s = press("ArrowRight")  # step 2 is the detour step
            assert s["cur"] == {"slide": "heap-what", "step": 0}
            assert s["H"][-1] == {"slide": "dijkstra", "step": 2, "kind": "excursion"}
            s = press("ArrowRight", "ArrowRight")  # heap-ops, then back to the detour step
            assert s["cur"] == {"slide": "dijkstra", "step": 2}
            assert press("ArrowRight")["cur"] == {"slide": "dijkstra", "step": 3}  # the next step, no re-entry
            assert press("ArrowLeft")["cur"] == {"slide": "dijkstra", "step": 1}  # Left skips the detour step
            assert press("ArrowRight")["cur"] == {"slide": "heap-what", "step": 0}  # Right enters it again
            assert press("ArrowUp")["cur"] == {"slide": "dijkstra", "step": 2}
            page.goto(out.as_uri() + "#/dijkstra/2")  # reaching the step by the hash is not an event
            page.wait_for_timeout(100)
            assert page.evaluate("Lattice.state().cur") == {"slide": "dijkstra", "step": 2}
            assert "dt" in page.inner_html("#lt-progress")  # the HUD marks the detour step
            # skip-detour steps over a detour step without entering it; a multi-step rolls over it
            assert press("ArrowLeft", "Shift+ArrowDown")["cur"] == {"slide": "dijkstra", "step": 3}
            assert press("Shift+ArrowDown")["cur"] == {"slide": "dijkstra", "step": 3}  # nothing to skip: no-op
            page.goto(out.as_uri() + "#/dijkstra/0")
            page.keyboard.press("End")
            page.wait_for_timeout(600)
            assert page.evaluate("Lattice.state()")["cur"] == {"slide": "dijkstra", "step": 4}
            # a blocking detour step stops a multi-step in front of it, and still enters with Right
            page.goto(out.as_uri() + "#/blocked/0")
            page.keyboard.press("Shift+ArrowRight")
            page.wait_for_timeout(600)
            assert page.evaluate("Lattice.state().cur") == {"slide": "blocked", "step": 1}
            assert page.inner_text("#lt-flash") == "Cannot step detour"
            page.keyboard.press("End")
            page.wait_for_timeout(300)
            assert page.evaluate("Lattice.state().cur") == {"slide": "blocked", "step": 1}
            assert press("Shift+ArrowDown")["cur"] == {"slide": "blocked", "step": 3}  # the explicit skip works
            assert press("ArrowLeft", "ArrowRight")["cur"] == {"slide": "inside-the-wall", "step": 0}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


BADGE_DECK = """
# Questions
{.reveal}
```python
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)
```

{.reveal}
Last remark.

::: detour {#q1 at=1 badge=next key=a}
# Why is it slow?
:::

::: detour {#q2 at=1 badge=step key=b}
# Memoize it
:::

::: detour {#q3 key=c}
# Always offered
:::
"""


def test_badges_wait_for_their_detour_step(tmp_path):
    """Spec 3.9: `badge=next` shows only at the step before its detour step, `badge=step` from that step on."""
    src = tmp_path / "talk.md"
    src.write_text(BADGE_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())

            def press(*keys):
                for k in keys:
                    page.keyboard.press(k)
                return page.evaluate("Lattice.state().cur")

            def shown():
                """The badges visible on the slide, and the current step."""
                return page.evaluate("""() => [Lattice.state().cur.step,
                    [...document.querySelectorAll('#s-questions .lt-detour-badge')]
                      .filter((b) => !b.classList.contains('lt-hidden')).map((b) => b.dataset.ltDetour)]""")

            # steps: 0, 1 (the code), 2 (detour step q1), 3 (detour step q2), 4 (the remark)
            assert shown() == [0, ["q3"]]
            assert "Why is it slow?" not in page.inner_text("#lt-progress")  # nor does the Down hint name it
            press("ArrowRight")
            assert shown() == [1, ["q1", "q3"]]  # q1 is what Right does next
            assert "Why is it slow?" in page.inner_text("#lt-progress")
            assert press("ArrowRight") == {"slide": "why-is-it-slow", "step": 0}
            assert press("ArrowRight") == {"slide": "questions", "step": 2}
            assert shown() == [2, ["q2", "q3"]]  # q1 is done, q2 is next and stays from now on
            assert press("ArrowRight") == {"slide": "memoize-it", "step": 0}
            assert press("ArrowRight") == {"slide": "questions", "step": 3}
            assert shown() == [3, ["q2", "q3"]]
            press("ArrowRight")
            assert shown() == [4, ["q2", "q3"]]
            # backward: Left skips both detour steps, and the badges follow the step
            press("ArrowLeft")
            assert shown() == [1, ["q1", "q3"]]
            press("ArrowLeft")
            assert shown() == [0, ["q3"]]
            # any way of reaching a step shows the same badges (steps are positions)
            page.goto(out.as_uri() + "#/questions/2")
            page.wait_for_timeout(100)
            assert shown() == [2, ["q2", "q3"]]
            # a hidden badge cannot be clicked, but its key still enters the detour
            assert page.is_hidden("#s-questions [data-lt-detour=q1]")
            assert press("a") == {"slide": "why-is-it-slow", "step": 0}
            # the presenter preview renders the next position through the same path: q1 shows there
            page.goto(out.as_uri() + "?presenter#/questions/0")
            frame = None
            for _ in range(40):
                frame = next((f for f in page.frames if f.url.endswith("?preview")), None)
                if frame is not None and frame.evaluate("window.Lattice && Lattice.state() ? Lattice.state().cur.step : -1") == 1:
                    break
                page.wait_for_timeout(50)
            assert frame.evaluate("Lattice.state().cur") == {"slide": "questions", "step": 1}
            assert frame.is_visible("#s-questions [data-lt-detour=q1]")
            assert page.is_hidden("#s-questions [data-lt-detour=q1]")
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PLACED_BADGE_DECK = """
# Two questions

:::: columns
::: column {width=2fr}
{.reveal}
- the program

::detour-badge{ref=assert}
:::
::: column {width=1fr}
::detour-badge{ref=useful label="Why?"}

::detour-badge{ref=useful badge=next label="Next: why?"}
:::
::::

::: detour {#assert label="What can we assert?" key=q at=1 badge=step}
# What we can assert
:::

::: detour {#useful label="Why is that useful?" key=w at=1 badge=step}
# Why it is useful
:::

# After
"""


def test_placed_badges_in_columns(tmp_path):
    """Spec 3.9: badges placed with ::detour-badge sit in their columns and wait for their detour step."""
    src = tmp_path / "talk.md"
    src.write_text(PLACED_BADGE_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())

            def press(*keys):
                for k in keys:
                    page.keyboard.press(k)
                return page.evaluate("Lattice.state().cur")

            def shown():
                """The current step, and the visible badges by column (label text)."""
                return page.evaluate("""() => [Lattice.state().cur.step,
                    [...document.querySelectorAll('#s-two-questions .lt-column')].map((c) =>
                      [...c.querySelectorAll('.lt-detour-badge')]
                        .filter((b) => !b.classList.contains('lt-hidden'))
                        .map((b) => b.querySelector('span').textContent))]""")

            assert page.locator("#s-two-questions > .lt-body > .lt-detour-badge").count() == 0  # no default badge
            assert shown() == [0, [[], []]]
            assert "What can we assert?" not in page.inner_text("#lt-progress")
            press("ArrowRight")
            assert shown() == [1, [["What can we assert?"], []]]
            assert "What can we assert?" in page.inner_text("#lt-progress")
            assert press("ArrowRight") == {"slide": "what-we-can-assert", "step": 0}
            assert press("ArrowRight") == {"slide": "two-questions", "step": 2}
            assert shown() == [2, [["What can we assert?"], ["Why?", "Next: why?"]]]
            assert press("ArrowRight") == {"slide": "why-it-is-useful", "step": 0}
            assert press("ArrowRight") == {"slide": "two-questions", "step": 3}
            assert shown() == [3, [["What can we assert?"], ["Why?"]]]  # the `next` override is done
            press("ArrowLeft")  # Left skips both detour steps
            assert shown() == [1, [["What can we assert?"], []]]
            page.click("#s-two-questions [data-lt-detour=assert]")  # a placed badge enters its detour
            assert page.evaluate("Lattice.state().cur") == {"slide": "what-we-can-assert", "step": 0}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PRESENTER_DECK = """
# Intro

# Steps
{.reveal}
- a
- b
- c

# Last
"""


def test_presenter_preview_and_scrubber(tmp_path):
    """Spec 7.5: the preview shows what NEXT would show; the scrubber moves between steps, not in history."""
    src = tmp_path / "talk.md"
    src.write_text(PRESENTER_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri() + "?presenter")
            preview = page.frame_locator(".lt-pp-preview")

            def previewed(expected):
                """What the preview pane shows, once it matches `expected` or after two seconds."""
                cur = None
                for _ in range(40):
                    frame = next((f for f in page.frames if f.url.endswith("?preview")), None)
                    if frame is not None:
                        cur = frame.evaluate("window.Lattice && Lattice.state() ? Lattice.state().cur : null")
                        if cur == expected:
                            break
                    page.wait_for_timeout(50)
                return cur

            assert previewed({"slide": "steps", "step": 0}) == {"slide": "steps", "step": 0}
            keys = page.inner_text(".lt-pp-keys")  # spec 7.5: every global binding is listed
            assert "Shift+\u2192" in keys and "End" in keys and "presenter view" in keys and "Space" in keys
            assert "\u00d73" in keys and "last or first step of the slide" in keys  # spec 7.6
            assert page.is_hidden(".lt-pp-scrub")
            page.keyboard.press("ArrowRight")
            assert page.is_visible(".lt-pp-scrub")
            assert previewed({"slide": "steps", "step": 1}) == {"slide": "steps", "step": 1}
            page.fill(".lt-pp-scrub input", "3")  # drag to the last step
            s = page.evaluate("Lattice.state()")
            assert s["cur"] == {"slide": "steps", "step": 3}
            assert s["H"] == [{"slide": "intro", "step": 0, "kind": "forward"}]  # scrubbing is not history
            assert previewed({"slide": "last", "step": 0}) == {"slide": "last", "step": 0}
            assert preview.locator("#lt-hud").is_hidden()
            page.keyboard.press("ArrowRight")
            assert page.evaluate("Lattice.state().cur") == {"slide": "last", "step": 0}
            assert page.locator(".lt-pp-next-none").inner_text() == "end of path"
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_tree_and_grid_runtimes_step_both_ways(tmp_path):
    """Every position of the tree and grid animations renders forward and backward without errors."""
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "examples" / "06-trees-and-grids" / "talk.md"
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(out.as_uri())
            seen = set()
            for _ in range(400):
                cur = page.evaluate("Lattice.state().cur")
                if (cur["slide"], cur["step"]) in seen:
                    break  # end of path
                seen.add((cur["slide"], cur["step"]))
                page.keyboard.press("ArrowRight")
            assert ("lcs", 43) in seen and ("avl-insertions", 22) in seen
            for _ in range(len(seen)):
                page.keyboard.press("ArrowLeft")
            assert page.evaluate("Lattice.state().cur") == {"slide": "trees-and-grids", "step": 0}
            nodes = page.evaluate("document.querySelectorAll('.lt-tree-anim .lt-node:not(.lt-ta-out)').length")
            assert nodes == 0  # back at step 0 of the AVL slide: the tree is empty
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_bbv_runtime_steps_both_ways(tmp_path):
    """Every position of the versioning animations renders forward and backward without errors,
    the source CFG follows the animation, and versions come and go with the frames."""
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "examples" / "07-basic-block-versioning" / "talk.md"
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(out.as_uri() + "#/find-sbbv/0")
            visible = "document.querySelectorAll('#s-find-sbbv %s .lt-bbv-node:not(.lt-gone)').length"
            assert page.evaluate(visible % ".lt-c-bbv-anim") == 1  # the generic entry only
            assert page.evaluate("document.querySelectorAll('.lt-c-bbv-cfg .lt-bbv-node.mk-active').length") == 1
            seen = set()
            for _ in range(600):
                cur = page.evaluate("Lattice.state().cur")
                if (cur["slide"], cur["step"]) in seen:
                    break
                seen.add((cur["slide"], cur["step"]))
                page.keyboard.press("ArrowRight")
            assert any(s == "find-sbbv" for s, _ in seen)
            page.evaluate("location.hash = '#/fact-lv/0'")  # off the main path (after the branch)
            page.wait_for_timeout(100)
            for _ in range(400):
                cur = page.evaluate("Lattice.state().cur")
                if (cur["slide"], cur["step"]) in seen:
                    break
                seen.add((cur["slide"], cur["step"]))
                page.keyboard.press("ArrowRight")
            assert sum(1 for s, _ in seen if s == "fact-lv") > 50
            for _ in range(len(seen)):
                page.keyboard.press("ArrowLeft")
            # jump to the last step: the final specialized CFG of figure 6 has 14 versions
            page.evaluate("location.hash = '#/find-sbbv/999'")
            page.wait_for_timeout(200)
            assert page.evaluate("Lattice.state().cur")["slide"] == "find-sbbv"
            assert page.evaluate(visible % ".lt-c-bbv-anim") == 14
            # origin colours survive a version being hidden and shown again (back to step 0, then forward)
            uncoloured = ("Array.from(document.querySelectorAll('#s-find-sbbv .lt-c-bbv-anim .lt-bbv-node:not(.lt-gone)'))"
                          ".filter(g => !g.classList.contains('has-origin')).length")
            assert page.evaluate(uncoloured) == 0
            page.evaluate("location.hash = '#/find-sbbv/0'")
            page.wait_for_timeout(100)
            for _ in range(12):
                page.keyboard.press("ArrowRight")
            page.wait_for_timeout(100)
            assert page.evaluate(visible % ".lt-c-bbv-anim") > 1 and page.evaluate(uncoloured) == 0
            # abstract interpretation: the context lines inside a block change with the frame
            page.evaluate("location.hash = '#/sum-to-n-ai/0'")
            page.wait_for_timeout(200)
            ctx = "Array.from(document.querySelectorAll('#s-sum-to-n-ai .lt-bbv-node')[1].querySelectorAll('.lt-bbv-ctx')).map(t => t.textContent).join(' ')"
            first = page.evaluate(ctx)
            page.evaluate("location.hash = '#/sum-to-n-ai/999'")
            page.wait_for_timeout(200)
            last = page.evaluate(ctx)
            assert first != last and "[0, ∞)" in last
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


ARROW_DECK = """
# Arrows

{#why}
A paragraph to point at.

```arrow {#walk label="here"}
steps:
  - why
  - to: .lt-title
    angle: 270
    length: 60
```
"""


def test_arrow_runtime_points_at_its_targets(tmp_path):
    """Spec 8.9: the arrow is an overlay on the slide, its head touches the target, and steps move it."""
    src = tmp_path / "talk.md"
    src.write_text(ARROW_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(300)

            def measure(target):
                return page.evaluate("""(sel) => {
                    const sec = document.querySelector('.lt-slide:not([hidden])');
                    const path = sec.querySelector('.lt-arrow-line');
                    const n = path.getTotalLength();
                    const pt = (q) => ({x: q.x, y: q.y});
                    const head = pt(path.getPointAtLength(n)), tail = pt(path.getPointAtLength(0));
                    const s = sec.getBoundingClientRect(), scale = s.width / sec.offsetWidth;
                    const r = document.querySelector(sel).getBoundingClientRect();
                    const box = {x: (r.left - s.left) / scale, y: (r.top - s.top) / scale, w: r.width / scale, h: r.height / scale};
                    return {head, tail, box, overlay: path.closest('.lt-c-arrow').parentElement === sec,
                            label: sec.querySelector('.lt-arrow-text').textContent};
                }""", target)

            m = measure("#why")
            assert m["overlay"] and m["label"] == "here"
            # 315 degrees: the arrow comes from the lower right, its head just outside the paragraph's box
            assert m["tail"]["x"] > m["head"]["x"] and m["tail"]["y"] > m["head"]["y"]
            assert m["box"]["x"] + m["box"]["w"] + 12 >= m["head"]["x"] >= m["box"]["x"]
            assert 0 < m["head"]["y"] - (m["box"]["y"] + m["box"]["h"]) < 12
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)  # the glide between steps
            m = measure(".lt-title")
            # 270 degrees: from below, pointing up at the title
            assert abs(m["tail"]["x"] - m["head"]["x"]) < 1 and 0 < m["tail"]["y"] - m["head"]["y"] <= 61
            assert 0 < m["head"]["y"] - (m["box"]["y"] + m["box"]["h"]) < 12
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


NULL_ARROW_DECK = """
# Arrows

{#why}
A paragraph to point at.

```arrow {#w}
steps:
  - null
  - {to: why, label: here}
  - null
  - {to: .lt-title, angle: 270, length: 60}
```
"""


def test_arrow_null_steps_hide_it(tmp_path):
    """Spec 8.9: no arrow at a null position, and the next arrow appears in place instead of gliding."""
    src = tmp_path / "talk.md"
    src.write_text(NULL_ARROW_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(300)
            state = """() => {
                const sec = document.querySelector('.lt-slide:not([hidden])');
                const svg = sec.querySelector('.lt-c-arrow svg');
                const path = sec.querySelector('.lt-arrow-line');
                const shown = getComputedStyle(svg).visibility !== 'hidden';
                const n = shown ? path.getTotalLength() : 0;
                return {shown, head: shown ? path.getPointAtLength(n).y : null};
            }"""
            assert not page.evaluate(state)["shown"]
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            first = page.evaluate(state)
            assert first["shown"]
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            assert not page.evaluate(state)["shown"]
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(30)  # right away: placed, not gliding from the paragraph
            early = page.evaluate(state)
            page.wait_for_timeout(500)
            last = page.evaluate(state)
            assert early["shown"] and abs(early["head"] - last["head"]) < 0.5 and last["head"] < first["head"]
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(500)
            assert not page.evaluate(state)["shown"]
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


ANCHOR_DECK = """
# Anchors

:::: columns
::: column
```code-steps {#cs lang=scheme file="sum.scm"}
steps: [i-init, body]
```
:::
::: column
{#note}
A note on the right.
:::
::::

```arrow {#a from=note from_anchor=left to_anchor=bottom}
steps:
  - i-init
  - to: body
    to_anchor: right
  - to: body
    from: ""
    to_anchor: center
  - to: note
    from: ""
    to_anchor: 45
    angle: 45
```

```timeline
a 1, cs 1
a 2, cs 2
a 3
```
"""

SUM_SCM = """\
(define (sum-to n)
  (let loop (#|@i-init|# (i 0) #|@end|#
             (acc 0))
    #|@body|#
    (if (> i n)
        acc
        (loop (+ i 1) (+ acc i)))
    #|@end|#))
"""


def test_arrow_anchors_and_code_segments(tmp_path):
    """Spec 8.9 and 8.10: anchored ends sit on the chosen side and leave or enter along it, a segment is
    measured as the union of its pieces, and code-steps highlight segments."""
    src = tmp_path / "talk.md"
    src.write_text(ANCHOR_DECK)
    (tmp_path / "sum.scm").write_text(SUM_SCM)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(300)

            def measure(target, source=None):
                return page.evaluate("""([target, source]) => {
                    const sec = document.querySelector('.lt-slide:not([hidden])');
                    const path = sec.querySelector('.lt-arrow-line');
                    const n = path.getTotalLength();
                    const pt = (q) => ({x: q.x, y: q.y});
                    const s = sec.getBoundingClientRect(), scale = s.width / sec.offsetWidth;
                    const boxOf = (sel) => {
                        let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
                        for (const e of sec.querySelectorAll(sel)) {
                            const range = document.createRange(); range.selectNodeContents(e);
                            const q = range.getBoundingClientRect();
                            l = Math.min(l, q.left); t = Math.min(t, q.top); r = Math.max(r, q.right); b = Math.max(b, q.bottom);
                        }
                        return {x: (l - s.left) / scale, y: (t - s.top) / scale, w: (r - l) / scale, h: (b - t) / scale};
                    };
                    return {head: pt(path.getPointAtLength(n)), nearHead: pt(path.getPointAtLength(n - 4)),
                            tail: pt(path.getPointAtLength(0)), nearTail: pt(path.getPointAtLength(4)),
                            box: boxOf(target), from: source ? boxOf(source) : null,
                            lit: Array.from(sec.querySelectorAll('.lt-seg.lt-hl')).map(e => e.dataset.ltSeg),
                            pieces: sec.querySelectorAll('[data-lt-seg="body"]').length};
                }""", [target, source])

            m = measure('[data-lt-seg="i-init"]', "#note")
            f, b = m["from"], m["box"]
            # leaves the left side of the note, in the middle, heading left
            assert 0 < f["x"] - m["tail"]["x"] < 12 and abs(m["tail"]["y"] - (f["y"] + f["h"] / 2)) < 1
            assert m["nearTail"]["x"] < m["tail"]["x"] and abs(m["nearTail"]["y"] - m["tail"]["y"]) < 0.5
            # enters the bottom of `(i 0)`, in the middle, heading up
            assert 0 < m["head"]["y"] - (b["y"] + b["h"]) < 12 and abs(m["head"]["x"] - (b["x"] + b["w"] / 2)) < 1
            assert m["nearHead"]["y"] > m["head"]["y"] and abs(m["nearHead"]["x"] - m["head"]["x"]) < 0.5
            assert m["lit"] == []

            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            m = measure('[data-lt-seg="body"]')
            b = m["box"]
            assert m["pieces"] == 3 and m["lit"] == ["i-init"]
            # the right side of the three-line segment, in the middle
            assert 0 < m["head"]["x"] - (b["x"] + b["w"]) < 12 and abs(m["head"]["y"] - (b["y"] + b["h"] / 2)) < 1

            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            m = measure('[data-lt-seg="body"]')
            b = m["box"]
            assert abs(m["head"]["x"] - (b["x"] + b["w"] / 2)) < 1 and abs(m["head"]["y"] - (b["y"] + b["h"] / 2)) < 1
            assert set(m["lit"]) == {"body"}

            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            m = measure("#note")
            b = m["box"]
            c = {"x": b["x"] + b["w"] / 2, "y": b["y"] + b["h"] / 2}
            # 45 degrees: up and to the right of the center, on the ray from it
            dx, dy = m["head"]["x"] - c["x"], c["y"] - m["head"]["y"]
            assert dx > 0 and dy > 0 and abs(dx - dy) < 1.5
            assert m["tail"]["x"] > m["head"]["x"] and m["tail"]["y"] < m["head"]["y"]
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


MORPH_DECK = """
# Fix {#fix}

```code-morph {#m lang=python title="fix" linenos=true}
versions:
  - code: |
      total = 0
      for i in range(len(xs) - 1):
          total += xs[i]
      print(total)
  - code: |
      total = 0
      for x in xs:
          total += x
      print(total)
  - code: |
      total = 0
      for x in xs:
          if x > 0:
              total += x
      print(total)
  - code: |
      total = sum(x for x in xs if x > 0)
      print(total)
```

# Bound {#bound}

```code-morph {#loop lang=scheme file="sum.scm" mark=true}
steps:
  - bound: "(>= i n)"
  - init: "(i 1)"
  - bound: |
      (or (> i n)
          (< n 0))
```

```arrow
to: bound
angle: 300
```

Text under the code.

# Fit {#fit}

```code-morph {#f room=fit}
versions:
  - code: "a = 1"
  - code: "a = 1\\nb = 2\\nc = 3"
```

Text under the fitted code.

# Highlighted {#hl}

```code-morph {#h lang=python linenos=true highlight=changed}
versions:
  - code: |
      total = 0
      for i in #|@rng|#range(len(xs) - 1)#|@end|#:
          total += xs[i]
      print(total)
    highlight: rng
  - code: |
      total = 0
      for x in xs:
          total += x
      print(total)
  - code: |
      total = sum(xs)
      print(total)
    highlight: "2"
```
"""

MORPH_SCM = """\
(define (sum-to n)
  (let loop (#|@init|# (i 0) #|@end|#
             (acc 0))
    (if #|@bound|# (> i n) #|@end|#
        acc
        (loop (+ i 1) (+ acc i)))))
"""

# Geometry of a morph: every unit (box relative to the text, opacity, visibility, colour), the line numbers,
# the text copy and its segments, the box of the code block and of the text under it, and the arrow.
MORPH_GEOMETRY = """(sid) => {
  const sec = document.querySelector(`#s-${CSS.escape(sid)}`);
  const stage = sec.querySelector('.lt-morph-stage');
  const o = stage.getBoundingClientRect();
  const r1 = (x) => Math.round(x * 2) / 2;
  const unit = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e), on = cs.visibility !== 'hidden';
    return [e.textContent, on ? r1(r.left - o.left) : null, on ? r1(r.top - o.top) : null, cs.opacity, cs.visibility,
            cs.color, cs.backgroundColor]; };  // a hidden unit has no place
  const seg = sec.querySelector('.lt-morph-text #bound') || sec.querySelector('.lt-morph-text .lt-seg[id]');
  const path = sec.querySelector('.lt-arrow-line');
  const head = path && path.getAttribute('d') ? path.getPointAtLength(path.getTotalLength()) : null;
  const below = sec.querySelector('.lt-body > p');
  return {units: Array.from(sec.querySelectorAll('.lt-mt')).map(unit),
          lines: Array.from(sec.querySelectorAll('.lt-morph-ln')).map(unit),
          text: sec.querySelector('.lt-morph-text').textContent,
          label: (sec.querySelector('.lt-morph-label') || {}).textContent || null,
          seg: seg ? [seg.id, seg.textContent, r1(seg.getBoundingClientRect().left - o.left), r1(seg.getBoundingClientRect().top - o.top)] : null,
          height: r1(stage.getBoundingClientRect().height),
          overflow: Math.max(0, sec.querySelector('pre').scrollHeight - sec.querySelector('pre').clientHeight),
          below: below ? r1(below.getBoundingClientRect().top) : null,
          head: head ? [r1(head.x), r1(head.y)] : null,
          dim: sec.querySelector('.lt-morph-box').classList.contains('lt-morph-dim'),
          hl: Array.from(sec.querySelectorAll('.lt-morph-hl')).filter(e => getComputedStyle(e).opacity !== '0')
                .map(e => [e.innerHTML, getComputedStyle(e).opacity])};
}"""


MORPH_ANIMATIONS = """document.getAnimations().filter(a => a.effect && a.effect.target
                       && a.effect.target.closest && a.effect.target.closest('.lt-morph')).length"""


def _morph_page(tmp_path):
    src = tmp_path / "talk.md"
    src.write_text(MORPH_DECK)
    (tmp_path / "sum.scm").write_text(MORPH_SCM)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    return out


def test_code_morph_runtime_renders_positions_alike(tmp_path):
    """Spec 8.11 and 10.2: a morph shows the same geometry at a position however it was reached: a fresh
    load, a jump in any order, a single animated step (once finished), an interrupted step, backward
    steps, skip playback; the arrow at a segment ends where a fresh load puts it."""
    import random

    out = _morph_page(tmp_path)
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 720})
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)

            fresh = {}
            for sid, n in (("fix", 4), ("bound", 4), ("fit", 2), ("hl", 3)):
                for k in range(n):
                    page.goto(f"{out.as_uri()}#/{sid}/{k}")
                    page.reload()
                    page.wait_for_timeout(250)
                    fresh[sid, k] = page.evaluate(MORPH_GEOMETRY, sid)
            assert fresh["fix", 0]["text"].startswith("total = 0\nfor i in range")
            assert fresh["fix", 3]["text"] == "total = sum(x for x in xs if x > 0)\nprint(total)"
            assert [u[3] for u in fresh["fix", 3]["lines"]] == ["0.6", "0.6", "0", "0", "0"]
            assert fresh["bound", 1]["seg"][:2] == ["bound", "(>= i n)"]
            assert fresh["bound", 3]["seg"][1] == "(or (> i n)\n          (< n 0))".split("\n")[0]
            assert fresh["fit", 0]["height"] < fresh["fit", 1]["height"]
            assert all(g["overflow"] == 0 for g in fresh.values())  # hidden units take no room
            assert fresh["fit", 0]["below"] < fresh["fit", 1]["below"]  # room=fit moves what follows
            assert fresh["bound", 0]["head"] != fresh["bound", 1]["head"]  # the arrow follows its segment
            # highlights (spec 8.11): one visible layer per position, units outside its rows dimmed
            assert not fresh["fix", 0]["dim"] and fresh["fix", 0]["hl"] == []
            assert [g["dim"] for g in (fresh["hl", k] for k in range(3))] == [True, True, True]
            assert all(len(fresh["hl", k]["hl"]) == 1 and fresh["hl", k]["hl"][0][1] == "1" for k in range(3))
            assert 'class="lt-seg lt-hl"' in fresh["hl", 0]["hl"][0][0]
            assert 'class="lt-line lt-hl" style="--r:1"' in fresh["hl", 2]["hl"][0][0]
            seen = sorted((u[0], u[3]) for u in fresh["hl", 2]["units"] if u[4] == "visible")
            assert seen == sorted([("total", "0.38"), ("=", "0.38"), ("sum", "0.38"), ("(", "0.38"), ("xs", "0.38"),
                                   (")", "0.38"), ("print", "1"), ("(", "1"), ("total", "1"), (")", "1")])
            assert [u[3] for u in fresh["hl", 2]["lines"][:2]] == ["0.23", "0.6"]  # line numbers dim with their row

            def settle(ms=450):
                page.evaluate("document.getAnimations().forEach(a => a.finish())")
                page.wait_for_timeout(ms)  # the arrow's own glide is not a CSS transition

            def now(sid):
                return page.evaluate(MORPH_GEOMETRY, sid)

            # jumps in a random order (no animation)
            rnd = random.Random(7)
            order = [(sid, k) for sid, n in (("fix", 4), ("bound", 4), ("hl", 3)) for k in range(n)]
            rnd.shuffle(order)
            last = None
            for sid, k in order:
                page.evaluate("(h) => { location.hash = h; }", f"#/{sid}/{k}")
                page.wait_for_timeout(120)
                if not (last and last[0] == sid and abs(last[1] - k) == 1):  # an adjacent step is a step
                    assert page.evaluate(MORPH_ANIMATIONS) == 0, (last, sid, k)
                last = (sid, k)
                settle(350)
                assert now(sid) == fresh[sid, k], (sid, k)

            # single steps forward and backward, animated, then finished
            for sid, n in (("fix", 4), ("bound", 4), ("fit", 2), ("hl", 3)):
                page.evaluate("(h) => { location.hash = h; }", f"#/{sid}/0")
                page.wait_for_timeout(150)
                for k in range(1, n):
                    page.keyboard.press("ArrowRight")
                    assert page.evaluate(MORPH_ANIMATIONS) > 0, (sid, k)
                    settle()
                    assert now(sid) == fresh[sid, k], (sid, k, "forward")
                for k in range(n - 2, -1, -1):
                    page.keyboard.press("ArrowLeft")
                    settle()
                    assert now(sid) == fresh[sid, k], (sid, k, "backward")

            # a step pressed in the middle of another: continues from where the units are, ends right
            page.evaluate("(h) => { location.hash = h; }", "#/fix/0")
            page.wait_for_timeout(150)
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(200)
            page.keyboard.press("ArrowRight")
            assert page.evaluate("document.querySelector('#s-fix .lt-morph-box').classList.contains('lt-morph-quick')")
            settle()
            assert now("fix") == fresh["fix", 2]

            # skip playback (several steps in rapid succession)
            page.evaluate("(h) => { location.hash = h; }", "#/bound/0")
            page.wait_for_timeout(150)
            page.evaluate("Lattice.actions()['last-step']()")
            page.wait_for_timeout(400)
            settle()
            assert page.evaluate("Lattice.state().cur") == {"slide": "bound", "step": 3}
            assert now("bound") == fresh["bound", 3]

            # reduced motion: steps are placed directly
            page.emulate_media(reduced_motion="reduce")
            page.evaluate("(h) => { location.hash = h; }", "#/fix/0")
            page.wait_for_timeout(150)
            page.keyboard.press("ArrowRight")
            assert page.evaluate(MORPH_ANIMATIONS) == 0
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_code_morph_in_preview_and_print(tmp_path):
    """Passive windows (spec 7.5, 11.5) render a morph position directly, without animation."""
    out = _morph_page(tmp_path)
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{out.as_uri()}#/fix/2")
            page.reload()
            page.wait_for_timeout(250)
            want = page.evaluate(MORPH_GEOMETRY, "fix")
            page.goto(out.as_uri() + "?preview")
            page.wait_for_timeout(250)
            page.evaluate("window.postMessage({lattice: 'preview', slide: 'fix', step: 1}, '*')")
            page.wait_for_timeout(100)
            page.evaluate("window.postMessage({lattice: 'preview', slide: 'fix', step: 2}, '*')")
            page.wait_for_timeout(150)
            assert page.evaluate(MORPH_ANIMATIONS) == 0
            assert page.evaluate(MORPH_GEOMETRY, "fix") == want
            page.goto(out.as_uri() + "?print")
            page.wait_for_timeout(250)
            plan = {"title": "t", "pageOf": {}, "sections": [],
                    "pages": [{"slide": "fix", "step": 1, "n": 1}, {"slide": "fix", "step": 2, "n": 2}]}
            assert page.evaluate("plan => Lattice.print(plan)", plan) == 2
            printed = page.evaluate("""() => Array.from(document.querySelectorAll('#lt-print-pages .lt-morph-text'))
                                       .map(e => e.textContent)""")
            assert printed[1] == want["text"] and printed[0] != printed[1]
            hidden = page.evaluate("""() => Array.from(document.querySelectorAll('#lt-page-2 .lt-mt'))
                                      .filter(e => getComputedStyle(e).visibility === 'hidden').length""")
            assert hidden == sum(1 for u in want["units"] if u[4] == "hidden")
            # a highlighted morph prints its position's layer and dimming (spec 8.11)
            plan = {"title": "t", "pageOf": {}, "sections": [], "pages": [{"slide": "hl", "step": 2, "n": 1}]}
            assert page.evaluate("plan => Lattice.print(plan)", plan) == 1
            printed = page.evaluate("""() => { const pg = document.querySelector('#s-hl-p1');
                const cur = Array.from(pg.querySelectorAll('.lt-morph-hl')).filter(e => getComputedStyle(e).opacity === '1');
                return [cur.length, cur.length ? cur[0].innerHTML : '', pg.querySelectorAll('.lt-morph-dim').length]; }""")
            assert printed[0] == 1 and 'class="lt-line lt-hl" style="--r:1"' in printed[1] and printed[2] == 1
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


HL_LOOK_DECK = """
# Morph {#mm}

```code-morph {#m lang=python}
versions:
  - code: "a = 1"
  - code: |
      total = 0
      for x in #|@it|#xs#|@end|#:
          total += x
      print(total)
    highlight: "3, it"
```

# Code {#cc}

```code {lang=python highlight="3, it"}
total = 0
for x in #|@it|#xs#|@end|#:
    total += x
print(total)
```

# Long {#lm}

```code-morph {#l lang=python}
versions:
  - long.py
  - {file: long2.py, highlight: 40}
```
"""

HL_LOOK = """(sid) => {
  const sec = document.querySelector(`#s-${sid}`), box = sec.querySelector('.lt-code').getBoundingClientRect();
  const rel = (e) => { const r = e.getBoundingClientRect();
    return [Math.round(r.left - box.left), Math.round(r.top - box.top), Math.round(r.width), Math.round(r.height)]; };
  const layer = sec.querySelector('.lt-morph-hl-cur') || sec;
  return {band: rel(layer.querySelector('.lt-line.lt-hl')), seg: rel(layer.querySelector('.lt-seg.lt-hl')),
          box: [Math.round(box.width), Math.round(box.height)]};
}"""


def test_code_morph_highlights_look_like_code(tmp_path):
    """Spec 8.11: at rest a highlighted morph looks like a `code` block of the same text with the same
    `highlight`: the band and the segment mark at the same place, with the same pixels, the other rows
    dimmed alike; an overflowing morph scrolls its first highlighted row a third of the way down."""
    import io

    from PIL import Image

    src = tmp_path / "talk.md"
    src.write_text(HL_LOOK_DECK)
    lines = [f"x{i} = {i}  # line {i}" for i in range(1, 81)]
    (tmp_path / "long.py").write_text("\n".join(lines) + "\n")
    lines[69] = "x70 = 70 + changed  # line 70"
    (tmp_path / "long2.py").write_text("\n".join(lines) + "\n")
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            shots, looks = {}, {}
            for sid, step in (("mm", 1), ("cc", 0)):
                page.goto(f"{out.as_uri()}#/{sid}/{step}")
                page.reload()
                page.wait_for_timeout(400)
                looks[sid] = page.evaluate(HL_LOOK, sid)
                looks[sid]["opacity"] = page.evaluate("""(sid) => Array.from(document.querySelectorAll(
                    `#s-${sid} .lt-mt, #s-${sid} .lt-line`)).filter(e => getComputedStyle(e).visibility !== 'hidden'
                    && !e.closest('.lt-morph-hl')).map(e => getComputedStyle(e).opacity).sort()""", sid)
                shots[sid] = Image.open(io.BytesIO(page.locator(f"#s-{sid} .lt-code").screenshot())).convert("RGB")
            # rows of a morph sit on whole pixels (spec 8.11), a code line may not: one pixel of slack
            assert all(abs(a - b) <= 1 for k in ("band", "seg", "box") for a, b in zip(looks["mm"][k], looks["cc"][k])), looks
            band, seg = looks["cc"]["band"], looks["cc"]["seg"]
            for x, y in [(band[0] + 1, band[1] + band[3] // 2), (band[0] + band[2] - 3, band[1] + 3),
                         (seg[0] + seg[2] // 2, seg[1] + seg[3] - 1)]:  # border, band, underline
                a, b = shots["mm"].getpixel((x, y)), shots["cc"].getpixel((x, y))
                assert sum(abs(i - j) for i, j in zip(a, b)) < 12, ((x, y), a, b)
            # the rows 1 and 4 are dimmed (units in the morph, lines in the code block), the others are not
            assert sorted(set(looks["mm"]["opacity"])) == sorted(set(looks["cc"]["opacity"])) == ["0.38", "1"]
            assert looks["mm"]["opacity"].count("0.38") == 7 and looks["cc"]["opacity"].count("0.38") == 2
            page.goto(f"{out.as_uri()}#/lm/1")
            page.reload()
            page.wait_for_timeout(400)
            at = page.evaluate("""() => { const pre = document.querySelector('#s-lm pre');
                const band = pre.querySelector('.lt-morph-hl-cur .lt-line.lt-hl');
                const p = pre.getBoundingClientRect(), r = band.getBoundingClientRect(), k = p.height / pre.offsetHeight;
                return [Math.round((r.top - p.top) / k), Math.round(pre.clientHeight / 3)]; }""")
            assert abs(at[0] - at[1]) <= 2, at  # line 40, not the changed line 70
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


SCROLL_DECK = """
# Long code {#long}

Some text above the block, to push it down the slide.

```code-steps {#walk lang=python file="long.py" title="long.py"}
steps: [40, 70, 5, 20]
```

# Long morph {#lmorph}

Some text above the block, to push it down the slide.

```code-morph {#lm lang=python}
versions: [long.py, long2.py]
```
"""

SCROLL_SEEN = """(sid) => { const pre = document.querySelector(`${sid} pre`);
  const line = pre.querySelector('.lt-line.lt-hl') || pre.querySelector('.lt-mt:not(.lt-mt-off)[data-probe]');
  const p = pre.getBoundingClientRect(), r = line.getBoundingClientRect(), scale = p.height / pre.offsetHeight;
  return {at: Math.round((r.top - p.top) / scale), third: Math.round(pre.clientHeight / 3),
          visible: r.top >= p.top - 1 && r.bottom <= p.bottom + 1}; }"""


def test_scrolled_code_shows_its_highlight_on_screen_and_in_print(tmp_path):
    """A code block taller than its space scrolls its highlight a third of the way down, whatever sits
    above it on the slide, however the step is reached; the print copy keeps the scroll (spec 8.8, 11.5).
    A morph scrolls its first changed row into view the same way (spec 8.11)."""
    src = tmp_path / "talk.md"
    src.write_text(SCROLL_DECK)
    lines = [f"x{i} = {i}  # line {i}" for i in range(1, 81)]
    (tmp_path / "long.py").write_text("\n".join(lines) + "\n")
    lines[69] = "x70 = 70 + changed  # line 70"
    (tmp_path / "long2.py").write_text("\n".join(lines) + "\n")
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    probe = "() => { const t = [...document.querySelectorAll('#s-lmorph .lt-mt')].find(e => e.textContent === 'changed'); t.dataset.probe = '1'; }"
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())
            page.wait_for_timeout(300)
            for k in range(1, 5):  # single steps, smooth
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(900)
                seen = page.evaluate(SCROLL_SEEN, "#s-long")
                assert seen["visible"], (k, seen)
                if k != 3:  # line 5 sits higher: the box cannot scroll above its start
                    assert abs(seen["at"] - seen["third"]) <= 2, (k, seen)
            page.evaluate("location.hash = '#/long/2'")  # a jump: placed at once
            page.wait_for_timeout(60)
            assert page.evaluate(SCROLL_SEEN, "#s-long")["visible"]
            page.goto(out.as_uri() + "#/lmorph/1")
            page.reload()
            page.wait_for_timeout(300)
            page.evaluate(probe)
            assert page.evaluate(SCROLL_SEEN, "#s-lmorph")["visible"]

            page.goto(out.as_uri() + "?print")
            page.wait_for_timeout(300)
            plan = {"title": "t", "pageOf": {}, "sections": [],
                    "pages": [{"slide": "long", "step": k, "n": k} for k in range(1, 5)]
                    + [{"slide": "lmorph", "step": 1, "n": 5}]}
            assert page.evaluate("plan => Lattice.print(plan)", plan) == 5
            for n in range(1, 5):
                assert page.evaluate(SCROLL_SEEN, f"#lt-page-{n}")["visible"], n
            page.evaluate("() => { const t = [...document.querySelectorAll('#lt-page-5 .lt-mt')].find(e => e.textContent === 'changed'); t.dataset.probe = '1'; }")
            assert page.evaluate(SCROLL_SEEN, "#lt-page-5")["visible"]
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


# ------------------------------------------------------------ enlarged blocks (spec 7.7, 9.5)

def _bbv_example(tmp_path):
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "examples" / "07-basic-block-versioning" / "talk.md"
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    return out


ZOOMED = "Lattice.zoomed()"
CARD_TEXT = "Array.from(document.querySelectorAll('.lt-zoom-card:not(.lt-closing) %s')).filter(t => t.style.display !== 'none').map(t => t.textContent)"


def _wait_closed(page):
    page.wait_for_timeout(400)  # the card shrinks back, then leaves the layer
    assert page.evaluate("document.querySelectorAll('.lt-zoom-card').length") == 0


def test_bbv_blocks_enlarge_and_any_key_or_outside_click_closes(tmp_path):
    out = _bbv_example(tmp_path)
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(out.as_uri() + "#/find-sbbv/12")
            page.wait_for_timeout(300)
            state = page.evaluate("JSON.stringify(Lattice.state())")
            anim = page.locator("#s-find-sbbv .lt-c-bbv-anim .lt-bbv-node:not(.lt-gone)")
            assert page.evaluate("document.querySelector('#s-find-sbbv .lt-c-bbv-anim svg').classList.contains('lt-bbv-clickable')")
            # the drawing shows label and context; the enlarged block adds the code and the exit context
            first = anim.first
            drawn = first.locator(".lt-bbv-code").count()
            first.click()
            page.wait_for_timeout(450)
            z = page.evaluate(ZOOMED)
            assert z and z["instance"] == "find-sbbv/trace"
            assert drawn == 0 and len(page.evaluate(CARD_TEXT % ".lt-bbv-code:not(.lt-bbv-ellipsis)")) > 0
            assert page.evaluate("document.getElementById('lt-stage').classList.contains('lt-zoomed')")
            assert page.evaluate("getComputedStyle(document.getElementById('lt-viewport')).filter").startswith("blur")
            # about 80% of the slide in its limiting dimension, centred, or capped for a small block
            box = page.evaluate("JSON.parse(JSON.stringify(document.querySelector('.lt-zoom-card').getBoundingClientRect()))")
            assert max(box["width"] / 1280, box["height"] / 720) <= 0.81
            assert abs(box["x"] + box["width"] / 2 - 640) < 2 and abs(box["y"] + box["height"] / 2 - 360) < 2
            # a bare modifier keeps it open; a click inside the card too
            page.keyboard.press("Shift")
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            assert page.evaluate(ZOOMED)
            # any other key closes it and does nothing else
            page.keyboard.press("ArrowRight")
            assert page.evaluate(ZOOMED) is None
            assert page.evaluate("JSON.stringify(Lattice.state())") == state and page.evaluate("location.hash") == "#/find-sbbv/12"
            _wait_closed(page)
            page.keyboard.press("ArrowRight")  # navigation resumes where it was
            assert page.evaluate("Lattice.state().cur") == {"slide": "find-sbbv", "step": 13}
            for key in ("Escape", " ", "o", "ArrowDown"):
                anim.first.click()
                assert page.evaluate(ZOOMED)
                page.keyboard.press(key)
                assert page.evaluate(ZOOMED) is None and page.evaluate("Lattice.state().cur") == {"slide": "find-sbbv", "step": 13}
                assert page.is_hidden("#lt-overlay")
            # a click outside closes it and does nothing else, even on a detour badge under the scrim
            badge = page.locator("#s-find-sbbv .lt-detour-badge").bounding_box()
            anim.first.click()
            page.mouse.click(badge["x"] + badge["width"] / 2, badge["y"] + badge["height"] / 2)
            assert page.evaluate(ZOOMED) is None and page.evaluate("Lattice.state().cur") == {"slide": "find-sbbv", "step": 13}
            _wait_closed(page)
            page.mouse.click(badge["x"] + badge["width"] / 2, badge["y"] + badge["height"] / 2)  # now it acts again
            assert page.evaluate("Lattice.state().cur")["slide"] == "one-block-steps"
            page.keyboard.press("ArrowUp")
            # the source CFG following the run is clickable too, with its code and parameters
            cfg = page.locator("#s-find-sbbv .lt-c-bbv-cfg .lt-bbv-node:not(.lt-gone)").first
            assert cfg.locator(".lt-bbv-code").count() == 0
            cfg.click()
            assert page.evaluate(ZOOMED)["instance"] == "find-sbbv/src"
            assert page.evaluate(CARD_TEXT % ".lt-bbv-code:not(.lt-bbv-ellipsis)")
            # a position change from elsewhere (the URL) closes it at once
            page.evaluate("location.hash = '#/find-sbbv/2'")
            page.wait_for_timeout(100)
            assert page.evaluate(ZOOMED) is None and page.evaluate("document.querySelectorAll('.lt-zoom-card').length") == 0
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_enlarged_blocks_show_the_current_step(tmp_path):
    out = _bbv_example(tmp_path)
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # abstract interpretation: the context of the current frame, and the exit context
            page.goto(out.as_uri() + "#/sum-to-n-ai/6")
            page.wait_for_timeout(300)
            node = page.locator("#s-sum-to-n-ai .lt-bbv-node").nth(1)
            drawn = node.locator(".lt-bbv-ctx").evaluate_all("ts => ts.map(t => t.textContent).filter(Boolean)")
            node.click()
            card = page.evaluate(CARD_TEXT % ".lt-bbv-ctx:not(.lt-bbv-after):not(.lt-bbv-after-head)")
            assert card == drawn
            assert page.evaluate(CARD_TEXT % ".lt-bbv-after-head") == [";; after:"]
            page.keyboard.press("Escape")
            _wait_closed(page)
            # instruction granularity: only the lines specialized so far, no exit context yet
            page.goto(out.as_uri() + "#/one-block-steps/0")
            page.wait_for_timeout(200)
            partial = None
            for step in range(1, 40):
                page.evaluate(f"location.hash = '#/one-block-steps/{step}'")
                page.wait_for_timeout(30)
                partial = page.evaluate("""(() => {
                  const nodes = Array.from(document.querySelectorAll('#s-one-block-steps .lt-c-bbv-anim .lt-bbv-node.st-done:not(.lt-gone)'));
                  return nodes.findIndex(n => Array.from(n.querySelectorAll('.lt-bbv-code:not(.lt-bbv-ellipsis)')).some(t => t.style.display === 'none')
                    && Array.from(n.querySelectorAll('.lt-bbv-code:not(.lt-bbv-ellipsis)')).some(t => t.style.display !== 'none'));
                })()""")
                if partial >= 0:
                    break
            assert partial >= 0
            node = page.locator("#s-one-block-steps .lt-c-bbv-anim .lt-bbv-node.st-done:not(.lt-gone)").nth(partial)
            drawn = node.locator(".lt-bbv-code:not(.lt-bbv-ellipsis)").evaluate_all(
                "ts => ts.filter(t => t.style.display !== 'none').map(t => t.textContent)")
            node.click()
            assert page.evaluate(CARD_TEXT % ".lt-bbv-code:not(.lt-bbv-ellipsis)") == drawn
            assert page.evaluate(CARD_TEXT % ".lt-bbv-after-head") == []
            page.keyboard.press("Escape")
            # a queued version shows its ellipsis
            queued = page.locator("#s-one-block-steps .lt-c-bbv-anim .lt-bbv-node.st-queued:not(.lt-gone)")
            if queued.count():
                queued.first.click()
                assert page.evaluate(CARD_TEXT % ".lt-bbv-code:not(.lt-bbv-ellipsis)") == []
                assert page.evaluate(CARD_TEXT % ".lt-bbv-ellipsis") == ["…"]
                page.keyboard.press("Escape")
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


ZOOM_DECK = """
# Off {#off}
```bbv-anim {#a clickable=off}
source: |
  function f(x)
  A:  if fixnum?(x) goto B else goto C
  B:  return fx+(x, 1)
  C:  return x
```

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
"""


def test_clickable_off_passive_windows_and_presenter_sync(tmp_path):
    src = tmp_path / "talk.md"
    src.write_text(ZOOM_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri() + "#/off/999")
            page.wait_for_timeout(200)
            page.locator("#s-off .lt-bbv-node:not(.lt-gone)").first.click()
            assert page.evaluate(ZOOMED) is None
            assert not page.evaluate("document.querySelector('#s-off svg').classList.contains('lt-bbv-clickable')")
            # clickable_show picks what the enlarged block shows: here the code, not the context
            page.evaluate("location.hash = '#/on/999'")
            page.wait_for_timeout(200)
            page.locator("#s-on .lt-bbv-node:not(.lt-gone)").first.click()
            assert page.evaluate(CARD_TEXT % ".lt-bbv-code:not(.lt-bbv-ellipsis)")
            assert page.evaluate(CARD_TEXT % ".lt-bbv-ctx") == []
            page.keyboard.press("Escape")
            # passive windows never enlarge
            for mode in ("?preview", "?print"):
                passive = context.new_page()
                passive.goto(out.as_uri() + mode)
                passive.wait_for_timeout(300)
                if mode == "?preview":
                    passive.evaluate("window.postMessage({lattice: 'preview', slide: 'on', step: 0}, '*')")
                    passive.wait_for_timeout(100)
                    passive.locator("#s-on .lt-bbv-node:not(.lt-gone)").first.click(force=True)
                    assert passive.evaluate(ZOOMED) is None and passive.evaluate("document.getElementById('lt-zoom')") is None
                    assert passive.evaluate("getComputedStyle(document.querySelector('#s-on .lt-bbv-node')).cursor") == "auto"
                passive.close()
            # the presenter view: the card stays over the slide pane, and the audience window mirrors it
            pres = context.new_page()
            pres.set_viewport_size({"width": 1600, "height": 800})
            pres.goto(out.as_uri() + "?presenter#/on/0")
            pres.wait_for_timeout(400)
            page.wait_for_timeout(200)
            assert "enlarge a block" in pres.inner_text(".lt-pp-keys")
            pres.locator("#s-on .lt-bbv-node:not(.lt-gone)").first.click()
            pres.wait_for_timeout(450)
            assert pres.evaluate(ZOOMED) == {"instance": "on/b", "key": "1"}
            stage = pres.locator("#lt-stage").bounding_box()
            panel = pres.locator("#lt-presenter-panel").bounding_box()
            card = pres.locator(".lt-zoom-card").bounding_box()
            assert card["x"] >= stage["x"] and card["x"] + card["width"] <= panel["x"]
            page.wait_for_timeout(200)
            assert page.evaluate(ZOOMED) == {"instance": "on/b", "key": "1"}
            # a click on the presenter panel closes it without resetting the timer or moving anything,
            # in both windows
            pres.mouse.click(panel["x"] + panel["width"] / 2, panel["y"] + panel["height"] - 20)
            pres.wait_for_timeout(200)
            assert pres.evaluate(ZOOMED) is None and page.evaluate(ZOOMED) is None
            # nor does a press on the scrubber move the step
            scrub = pres.locator(".lt-pp-scrub input").bounding_box()
            pres.locator("#s-on .lt-bbv-node:not(.lt-gone)").first.click()
            pres.mouse.click(scrub["x"] + scrub["width"] - 4, scrub["y"] + scrub["height"] / 2)
            pres.wait_for_timeout(200)
            assert pres.evaluate(ZOOMED) is None and pres.evaluate("Lattice.state().cur") == {"slide": "on", "step": 0}
            pres.wait_for_timeout(300)
            # closing in the audience window closes the presenter's card too
            pres.locator("#s-on .lt-bbv-node:not(.lt-gone)").first.click()
            page.wait_for_timeout(200)
            assert page.evaluate(ZOOMED)
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(200)
            assert page.evaluate(ZOOMED) is None and pres.evaluate(ZOOMED) is None
            assert pres.evaluate("Lattice.state().cur") == {"slide": "on", "step": 0}
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


LIST_DECK = """
# Bullets

:::: columns
::: column
{#p}
A paragraph on the left.
:::
::: column
{#facts}
- `vector-ref` fails if `v` is empty
- the loop guard makes `i` a valid index
  - nested one
  - nested two

{#nums}

9. nine
10. ten

<ul id="bare" style="list-style:none"><li>no marker</li></ul>
:::
::::

```arrow {#a color=red from_anchor=bullet to_anchor=right}
steps:
  - from: facts[1]
    to: p
  - from: facts[2][-1]
    to: p
  - from: nums[2]
    to: p
  - from: bare[1]
    to: p
  - to: facts[2]
    from: p
    from_anchor: right
    to_anchor: left
  - to: nums[-2]
    to_anchor: bullet
```
"""


def test_arrow_at_bullets(tmp_path):
    """Spec 8.9: `LIST[N]` names an item, `bullet` puts the end just left of the item's marker (measured
    against the pixels of the marker), leaving to the left; an item's box leaves out its nested list."""
    src = tmp_path / "talk.md"
    src.write_text(LIST_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(300)

            def ends():
                return page.evaluate("""() => {
                    const sec = document.querySelector('.lt-slide:not([hidden])');
                    const path = sec.querySelector('.lt-arrow-line');
                    const n = path.getTotalLength();
                    const s = sec.getBoundingClientRect(), scale = s.width / sec.offsetWidth;
                    const page = (q) => ({x: s.left + q.x * scale, y: s.top + q.y * scale});
                    return {tail: page(path.getPointAtLength(0)), nearTail: page(path.getPointAtLength(4)),
                            head: page(path.getPointAtLength(n)), nearHead: page(path.getPointAtLength(n - 4)), scale};
                }""")

            def rect(sel, own=False):
                return page.evaluate("""([sel, own]) => {
                    const e = document.querySelector(sel);
                    const r = document.createRange(); r.selectNodeContents(e);
                    if (own) { const k = Array.from(e.childNodes).findIndex(c => c.tagName === 'UL'); if (k >= 0) r.setEnd(e, k); }
                    const q = r.getBoundingClientRect();
                    return {x: q.left, y: q.top, w: q.width, h: q.height};
                }""", [sel, own])

            def marker_ink(item):
                """The marker of an item as drawn: accent pixels left of the item's text, on its first line."""
                import io

                from PIL import Image

                r = rect(item)
                clip = {"x": r["x"] - 80, "y": r["y"], "width": 80, "height": 40}
                png = Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("RGB")
                accent = page.evaluate("getComputedStyle(document.querySelector('.lt-slide')).getPropertyValue('--lt-accent')")
                ar, ag, ab = (int(accent.strip()[i:i + 2], 16) for i in (1, 3, 5))
                pts = [(x, y) for x in range(80) for y in range(40)
                       if sum(abs(a - b) for a, b in zip(png.getpixel((x, y)), (ar, ag, ab))) < 90]
                xs, ys = [x for x, _ in pts], [y for _, y in pts]
                return {"l": clip["x"] + min(xs), "r": clip["x"] + max(xs) + 1,
                        "t": clip["y"] + min(ys), "b": clip["y"] + max(ys) + 1}

            def at_bullet(e, ink, which="tail"):
                pt, near = e[which], e["nearTail" if which == "tail" else "nearHead"]
                # a gap left of the marker's ink, at its vertical middle, the curve leaving to the left
                assert 0 < ink["l"] - pt["x"] < 14, (pt, ink)
                assert abs(pt["y"] - (ink["t"] + ink["b"]) / 2) < 3, (pt, ink)
                assert near["x"] < pt["x"] and abs(near["y"] - pt["y"]) < 0.5

            at_bullet(ends(), marker_ink("#facts > li:nth-child(1)"))
            for i, item in enumerate(["#facts > li:nth-child(2) li:nth-child(2)", "#nums > li:nth-child(2)"]):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(500)
                at_bullet(ends(), marker_ink(item))

            page.keyboard.press("ArrowRight")  # no marker: the left of the item's first line
            page.wait_for_timeout(500)
            e, r = ends(), rect("#bare > li")
            assert 0 < r["x"] - e["tail"]["x"] < 14 and r["y"] < e["tail"]["y"] < r["y"] + r["h"]

            page.keyboard.press("ArrowRight")  # an item with a nested list: its own line only
            page.wait_for_timeout(500)
            e, own, whole = ends(), rect("#facts > li:nth-child(2)", own=True), rect("#facts > li:nth-child(2)")
            assert whole["h"] > 2 * own["h"]
            assert abs(e["head"]["y"] - (own["y"] + own["h"] / 2)) < 1 and 0 < own["x"] - e["head"]["x"] < 14

            page.keyboard.press("ArrowRight")  # `[-2]` and a bullet head without `from`: from the left
            page.wait_for_timeout(500)
            e = ends()
            at_bullet(e, marker_ink("#nums > li:nth-child(1)"), "head")
            assert e["tail"]["x"] < e["head"]["x"] and abs(e["tail"]["y"] - e["head"]["y"]) < 0.5
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


COLS_DECK = """
# Cols {#cols}

::: columns {duration=800}
::: column {#a}
{#aq}
Left text, long enough to wrap when its column is narrow, so that a reflow would show.

```diff-steps {#d lang=python}
versions:
  - {code: "x = 1"}
  - {code: "x = 2"}
  - {code: "x = 3"}
```
:::
::: column {#b}
{#pt}
Target in b
:::
::: column {#c width=0}
{.reveal}
- one
- two
:::
:::

```arrow {#p to=pt angle=270 length=60}
```

```arrow {#q to=aq angle=300 length=60}
```

```timeline
reveal 1
width a=0 c=1fr
d ..end
width a=1fr c=0, reveal end
width b=200px
```
"""

# Columns of a slide (left and width relative to the body, collapsed, visibility, inert, the opacity and width
# of their contents, moving), the heads of the two arrows (null when hidden), the diff shown and the fragments.
COLS_GEOMETRY = """(sid) => {
  const sec = document.querySelector(`#s-${sid}`), body = sec.querySelector('.lt-body').getBoundingClientRect();
  const r1 = (x) => Math.round(x * 2) / 2;
  const cols = Array.from(sec.querySelectorAll('.lt-column')).map((c) => {
    const r = c.getBoundingClientRect(), cs = getComputedStyle(c), inner = c.querySelector('.lt-column-in');
    return [c.id, r1(r.left - body.left), r1(r.width), c.classList.contains('lt-col-shut'), cs.visibility, c.inert,
            getComputedStyle(inner).opacity, c.classList.contains('lt-col-moving')]; });
  const head = (id) => { const el = sec.querySelector(`[data-instance="${sid}/${id}"]`), svg = el.querySelector('svg');
    const path = el.querySelector('path.lt-arrow-line');
    if (svg.style.visibility === 'hidden' || !path.getAttribute('d')) return null;
    const p = path.getPointAtLength(path.getTotalLength()); return [r1(p.x), r1(p.y)]; };
  const pt = sec.querySelector('#pt').getBoundingClientRect(), s = sec.getBoundingClientRect();
  return {cols, body: r1(body.width), p: head('p'), q: head('q'),
          target: [r1(pt.left - s.left), r1(pt.bottom - s.top)],
          diff: Array.from(sec.querySelectorAll('[data-instance="cols/d"] .lt-diff-pane')).findIndex((e) => !e.hidden),
          shown: Array.from(sec.querySelectorAll('#c li')).map((li) => !li.classList.contains('lt-hidden'))};
}"""


def _near(a, b, tol=1.5):
    """Two geometries alike: the columns exactly, the arrow heads within `tol` slide pixels."""
    if a["cols"] != b["cols"] or a["diff"] != b["diff"] or a["shown"] != b["shown"]:
        return False
    for k in ("p", "q"):
        if (a[k] is None) != (b[k] is None):
            return False
        if a[k] and max(abs(x - y) for x, y in zip(a[k], b[k])) > tol:
            return False
    return True


def test_columns_change_width_however_a_step_is_reached(tmp_path):
    """Spec 3.8 and 10.4: the widths of a step are the same from a fresh load, a jump, an animated step, an
    interrupted one, skip playback, the preview and print. A collapsed column takes no width and gives back
    its gap, is hidden and inert, and an arrow into it is hidden; while columns move, their contents keep a
    fixed width and an arrow follows its target."""
    import random

    src = tmp_path / "talk.md"
    src.write_text(COLS_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)

            def geo():
                return page.evaluate(COLS_GEOMETRY, "cols")

            def go(step):
                page.evaluate("(h) => { location.hash = h; }", f"#/cols/{step}")
                page.wait_for_timeout(150)

            fresh = {}
            for k in range(7):
                page.goto(f"{out.as_uri()}#/cols/{k}")
                page.reload()
                page.wait_for_timeout(250)
                fresh[k] = geo()
            body = fresh[0]["body"]
            ids = lambda g: {c[0]: c for c in g["cols"]}  # noqa: E731
            # step 0: c collapsed; a and b share the row exactly, with one gap of 40 between them
            a, b, c = (ids(fresh[0])[x] for x in "abc")
            assert a[1] == 0 and b[1] + b[2] == body and b[1] == a[2] + 40 and c[2] == 0
            assert c[3:7] == [True, "hidden", True, "0"] and a[3:7] == [False, "visible", False, "1"]
            # step 2: a collapsed, b and c share the row; the arrow into a is hidden, the other moved with pt
            a, b, c = (ids(fresh[2])[x] for x in "abc")
            assert a[2] == 0 and b[1] == 0 and c[1] + c[2] == body and a[3]
            assert fresh[2]["q"] is None and fresh[1]["q"] is not None and fresh[2]["p"] != fresh[1]["p"]
            # the fragment revealed while c was collapsed is there when it opens; the diff stepped while a was
            assert fresh[2]["shown"] == [True, False] and fresh[5]["shown"] == [True, True]
            assert fresh[4]["diff"] != fresh[2]["diff"] and fresh[5]["diff"] == fresh[4]["diff"]
            # step 6: a length
            assert ids(fresh[6])["b"][2] == 200 and ids(fresh[5])["b"][2] != 200

            # jumps in a random order: placed directly
            order = list(range(7)) * 2
            random.Random(3).shuffle(order)
            last = None
            for k in order:
                go(k)
                if last is None or abs(last - k) != 1:
                    assert not any(col[7] for col in geo()["cols"]), (last, k)
                page.wait_for_timeout(300 if last is None or abs(last - k) != 1 else 1000)  # an adjacent step moves
                assert _near(geo(), fresh[k]), (last, k)
                last = k

            # an animated step: a closes, c opens; frozen halfway, the contents keep their width and the
            # arrow at pt follows it
            go(1)
            page.wait_for_timeout(200)
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(150)
            page.evaluate("document.getAnimations().forEach(a => a.pause())")
            page.wait_for_timeout(100)
            mid = geo()
            a, b, c = (ids(mid)[x] for x in "abc")
            assert a[7] and c[7] and 0 < c[2] < ids(fresh[2])["c"][2] and c[4] == "visible"
            widths = page.evaluate("""() => Object.fromEntries(Array.from(document.querySelectorAll('#s-cols .lt-column'))
                .map(c => [c.id, c.querySelector('.lt-column-in').getBoundingClientRect().width]))""")
            assert abs(widths["a"] - ids(fresh[1])["a"][2]) < 1   # a collapsing column keeps its own width
            assert abs(widths["c"] - ids(fresh[2])["c"][2]) < 1   # an opening one has its final width
            assert abs(widths["b"] - ids(fresh[2])["b"][2]) < 1   # and so has every other one
            assert mid["q"] is None  # into a closing column
            # the arrow ends below the middle of pt, as measured now (its GAP is 6)
            pt = page.evaluate("""() => { const r = document.querySelector('#s-cols #pt').getBoundingClientRect(),
                s = document.querySelector('#s-cols').getBoundingClientRect(); return [r.left - s.left, r.right - s.left]; }""")
            assert pt[0] < mid["p"][0] < pt[1] and mid["p"] != fresh[1]["p"] and mid["p"] != fresh[2]["p"]
            page.evaluate("document.getAnimations().forEach(a => a.cancel())")  # the paused transitions
            page.wait_for_timeout(900)  # the move still ends with its final values
            assert _near(geo(), fresh[2])

            # every step forward and backward, animated, then at rest
            go(0)
            page.wait_for_timeout(300)
            for k in range(1, 7):
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(1000)
                assert _near(geo(), fresh[k]), (k, "forward")
            for k in range(5, -1, -1):
                page.keyboard.press("ArrowLeft")
                page.wait_for_timeout(1000)
                assert _near(geo(), fresh[k]), (k, "backward")

            # a step pressed in the middle of another: a short move from where the columns are
            go(1)
            page.wait_for_timeout(300)
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(120)
            page.keyboard.press("ArrowLeft")
            # it heads for the widths of step 1 (the transitions under way are not taken for the final layout)
            heading = page.evaluate("""() => Array.from(document.querySelectorAll('#s-cols .lt-column'))
                .map(c => Math.round(parseFloat(c.style.flex.split(' ')[2]) * 2) / 2)""")
            assert heading == [c[2] for c in fresh[1]["cols"]]
            assert any(col[7] for col in geo()["cols"])  # still moving (a short move of 140 ms)
            page.wait_for_timeout(350)
            assert _near(geo(), fresh[1])

            # skip playback
            go(0)
            page.wait_for_timeout(300)
            page.evaluate("Lattice.actions()['last-step']()")
            page.wait_for_timeout(1600)
            assert page.evaluate("Lattice.state().cur") == {"slide": "cols", "step": 6}
            assert _near(geo(), fresh[6])

            # reduced motion: placed directly
            page.emulate_media(reduced_motion="reduce")
            go(1)
            page.keyboard.press("ArrowRight")
            assert not any(col[7] for col in geo()["cols"])
            page.emulate_media(reduced_motion="no-preference")

            # the preview renders the position it is sent, directly
            page.goto(out.as_uri() + "?preview")
            page.wait_for_timeout(250)
            page.evaluate("window.postMessage({lattice: 'preview', slide: 'cols', step: 1}, '*')")
            page.wait_for_timeout(100)
            page.evaluate("window.postMessage({lattice: 'preview', slide: 'cols', step: 2}, '*')")
            page.wait_for_timeout(50)
            assert not any(col[7] for col in geo()["cols"])
            page.wait_for_timeout(250)
            assert _near(geo(), fresh[2])

            # print: each page has the widths of its step
            page.goto(out.as_uri() + "?print")
            page.wait_for_timeout(250)
            plan = {"title": "t", "pageOf": {}, "sections": [],
                    "pages": [{"slide": "cols", "step": 0, "n": 1}, {"slide": "cols", "step": 2, "n": 2},
                              {"slide": "cols", "step": 6, "n": 3}]}
            assert page.evaluate("plan => Lattice.print(plan)", plan) == 3
            printed = page.evaluate("""() => [1, 2, 3].map(n => Array.from(document.querySelectorAll(`#lt-page-${n} .lt-column`))
                .map(c => Math.round(c.getBoundingClientRect().width * 2) / 2))""")
            assert printed == [[c[2] for c in fresh[k]["cols"]] for k in (0, 2, 6)]
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PROG = """source: |
  function f(n)
  A:  goto B(i=0)
  B:  if <(i, n) goto C else goto D
  C:  i2 = +(i, 1)
      goto B(i=i2)
  D:  return i
panel: [worklist]"""

def test_columns_settle_when_their_move_ends(tmp_path):
    """Spec 3.8: when a move of columns ends, the columns are at their final widths and the arrows measure them
    there, even if the browser started the move's transitions late (a busy page): they used to keep running past
    the end of the move, and an arrow measured a column a few pixels short (the flaky skip playback of 0.24 to 0.26)."""
    src = tmp_path / "talk.md"
    src.write_text(COLS_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{out.as_uri()}#/cols/6")
            page.reload()
            page.wait_for_timeout(250)
            fresh = page.evaluate(COLS_GEOMETRY, "cols")
            page.evaluate("location.hash = '#/cols/5'")
            page.wait_for_timeout(250)
            page.keyboard.press("ArrowRight")
            # the move's transitions start 400 ms late, as on a busy page: they outlast the move (800 ms)
            assert page.evaluate("""() => { const as = document.getAnimations().filter(a => a.effect && a.effect.target
                && a.effect.target.closest('#s-cols .lt-columns')); as.forEach(a => { a.currentTime = -400; }); return as.length; }""")
            page.wait_for_timeout(1000)
            got = page.evaluate(COLS_GEOMETRY, "cols")
            assert not any(col[7] for col in got["cols"])
            assert _near(got, fresh, tol=0.5), (got, fresh)
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PANEL_DECK = f"""
# Narrow {{#narrow}}

::: columns
::: column
```abstract-interp-anim {{#n-auto height=200}}
{PROG}
```
:::
::: column
```abstract-interp-anim {{#n-right height=200 panel_at=right}}
{PROG}
```
:::
:::

```timeline
n-auto 1, n-right 1
```

# Wide {{#wide}}

```abstract-interp-anim {{#w-below height=200 panel_at=below}}
{PROG}
```
"""

# Where the panel of an instance sits relative to its drawing.
PANEL_PLACE = """(inst) => {
  const el = document.querySelector(`[data-instance="${inst}"]`);
  const c = el.querySelector('.lt-ga-canvas').getBoundingClientRect(), p = el.querySelector('.lt-ga-panel').getBoundingClientRect();
  return p.left >= c.right - 1 ? 'right' : p.top >= c.bottom - 1 ? 'below' : 'other';
}"""


def test_panel_at_places_the_panel(tmp_path):
    """Spec 8.8: `auto` puts the panel under the drawing in a narrow component, `right` keeps it beside the
    drawing there, and `below` puts it under the drawing at any width; the drawing keeps its `height`."""
    src = tmp_path / "talk.md"
    src.write_text(PANEL_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{out.as_uri()}#/narrow/1")
            page.wait_for_timeout(300)
            assert page.evaluate(PANEL_PLACE, "narrow/n-auto") == "below"
            assert page.evaluate(PANEL_PLACE, "narrow/n-right") == "right"
            page.goto(f"{out.as_uri()}#/wide/1")
            page.wait_for_timeout(300)
            assert page.evaluate(PANEL_PLACE, "wide/w-below") == "below"
            height = page.evaluate("""() => document.querySelector('[data-instance="wide/w-below"] .lt-ga-canvas')
                                      .getBoundingClientRect().height""")
            assert abs(height - 200) < 1
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PARTS_JS = """([inst, sel]) => {
    const sec = document.querySelector('.lt-slide:not([hidden])');
    const wrap = sec.querySelector(`[data-instance="${inst}"]`);
    const svg = wrap.querySelector('svg');
    const path = wrap.querySelector('.lt-arrow-line');
    const s = sec.getBoundingClientRect(), scale = s.width / sec.offsetWidth;
    const unit = (r) => ({x: (r.left - s.left) / scale, y: (r.top - s.top) / scale, w: r.width / scale, h: r.height / scale});
    const els = Array.from(sec.querySelectorAll(sel));
    let box = null;
    for (const e of els) {
        const b = unit(e.getBoundingClientRect());
        box = box ? {x: Math.min(box.x, b.x), y: Math.min(box.y, b.y),
                     w: Math.max(box.x + box.w, b.x + b.w) - Math.min(box.x, b.x),
                     h: Math.max(box.y + box.h, b.y + b.h) - Math.min(box.y, b.y)} : b;
    }
    const shown = svg.style.visibility !== 'hidden' && !!path.getAttribute('d');
    const head = shown ? path.getPointAtLength(path.getTotalLength()) : {x: NaN, y: NaN};
    return {shown, head: {x: head.x, y: head.y}, box};
}"""


def _near_box(m, gap=14):
    """The head sits just outside the box (within `gap` slide pixels of it), not inside it or far away."""
    b, h = m["box"], m["head"]
    dx = max(b["x"] - h["x"], 0, h["x"] - (b["x"] + b["w"]))
    dy = max(b["y"] - h["y"], 0, h["y"] - (b["y"] + b["h"]))
    inside = dx == 0 and dy == 0
    return (not inside or b["w"] < 1) and max(dx, dy) <= gap


CFG_PARTS_DECK = """
# Parts {#parts}

```bbv-cfg {#g program="find.bbv" height=560}
```

```arrow {#p}
steps:
  - {to: g.A, angle: 0, label: block}
  - {to: "g.A->B:#t", angle: 180, label: branch}
  - {to: g.J2->A, angle: 0, label: back}
  - {to: g.F->G, angle: 0, label: return}
```
"""


def test_arrow_at_parts_of_a_cfg(tmp_path):
    """Spec 8.9 and 9.5: the head touches the block, or the mark at the middle of an edge, which covers its label."""
    import shutil
    from pathlib import Path

    shutil.copy(Path(__file__).resolve().parent.parent / "user_manual" / "programs" / "find.bbv", tmp_path)
    src = tmp_path / "talk.md"
    src.write_text(CFG_PARTS_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    targets = ['.lt-bbv-node[data-vid="1"]', '.lt-bbv-edge[data-key="1->3:true"] > .lt-bbv-edge-mark',
               '.lt-bbv-edge[data-key="14->1:goto"] > .lt-bbv-edge-mark', '.lt-bbv-edge[data-key="7->8:return"] > .lt-bbv-edge-mark']
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(400)
            heads = []
            for i, sel in enumerate(targets):
                if i:
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(500)
                m = page.evaluate(PARTS_JS, ["parts/p", sel])
                assert m["shown"] and m["box"] and _near_box(m), (i, m)
                heads.append(m["head"])
            # the mark of a labelled edge covers its label; the mark of an unlabelled edge is a point
            label = page.evaluate("""() => {
                const g = document.querySelector('.lt-bbv-edge[data-key="1->3:true"]');
                const a = g.querySelector('.lt-bbv-edge-label').getBBox(), b = g.querySelector('.lt-bbv-edge-mark').getBBox();
                const r = document.querySelector('.lt-bbv-edge[data-key="14->1:goto"] .lt-bbv-edge-mark').getBBox();
                return {inside: a.x >= b.x - 1 && a.x + a.width <= b.x + b.width + 1 && a.y >= b.y - 1 && a.y + a.height <= b.y + b.height + 1,
                        point: r.width === 0 && r.height === 0};
            }""")
            assert label == {"inside": True, "point": True}
            # the same geometry on a fresh load of each step, in the preview and in print mode
            paths = []
            for i in range(len(targets)):
                page.goto(out.as_uri() + f"#/parts/{i}")
                page.wait_for_timeout(400)
                m = page.evaluate(PARTS_JS, ["parts/p", targets[i]])
                assert abs(m["head"]["x"] - heads[i]["x"]) < 1 and abs(m["head"]["y"] - heads[i]["y"]) < 1, i
                paths.append(page.evaluate("document.querySelector('.lt-slide:not([hidden]) .lt-arrow-line').getAttribute('d')"))
            page.goto(out.as_uri() + "?preview")
            page.wait_for_timeout(300)
            for i in (2, 1):
                page.evaluate(f"window.postMessage({{lattice: 'preview', slide: 'parts', step: {i}}}, '*')")
                page.wait_for_timeout(300)
                assert page.evaluate("document.querySelector('.lt-slide:not([hidden]) .lt-arrow-line').getAttribute('d')") == paths[i]
            page.goto(out.as_uri() + "?print")
            page.wait_for_timeout(300)
            plan = {"title": "t", "pageOf": {}, "sections": [],
                    "pages": [{"slide": "parts", "step": i, "n": i + 1} for i in (3, 0, 2)]}
            assert page.evaluate("plan => Lattice.print(plan)", plan) == 3
            printed = page.evaluate("""() => Array.from(document.querySelectorAll('#lt-print-pages .lt-arrow-line'))
                                       .map(e => e.getAttribute('d'))""")
            assert printed == [paths[3], paths[0], paths[2]]
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


def test_arrow_at_an_unlabelled_edge_in_firefox(tmp_path):
    """Spec 8.9 and 9.5, in Firefox: the mark of an unlabelled edge has no area, and Firefox gives such an SVG
    element an empty box at the origin; the head must still reach the middle of the edge (0.26.1)."""
    import shutil
    from pathlib import Path

    shutil.copy(Path(__file__).resolve().parent.parent / "user_manual" / "programs" / "find.bbv", tmp_path)
    src = tmp_path / "talk.md"
    src.write_text(CFG_PARTS_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    # where the mark is, from its own coordinates rather than from the box the browser reports
    mark_js = """() => {
        const sec = document.querySelector('.lt-slide:not([hidden])');
        const s = sec.getBoundingClientRect(), scale = s.width / sec.offsetWidth;
        const r = sec.querySelector('.lt-bbv-edge[data-key="14->1:goto"] > .lt-bbv-edge-mark');
        const m = r.getScreenCTM(), x = r.x.baseVal.value, y = r.y.baseVal.value;
        const p = {x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f};
        return {x: (p.x - s.left) / scale, y: (p.y - s.top) / scale, w: 0, h: 0};
    }"""
    try:
        with pw.sync_playwright() as p:
            browser = p.firefox.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # stepped to, and loaded at that step
            for how in ("step", "load"):
                if how == "step":
                    page.goto(out.as_uri())
                    page.wait_for_timeout(400)
                    for _ in range(2):
                        page.keyboard.press("ArrowRight")
                        page.wait_for_timeout(500)
                else:
                    page.goto(out.as_uri() + "#/parts/2")
                    page.wait_for_timeout(400)
                m = page.evaluate(PARTS_JS, ["parts/p", '.lt-bbv-edge[data-key="14->1:goto"] > .lt-bbv-edge-mark'])
                m["box"] = page.evaluate(mark_js)
                assert m["shown"] and m["box"]["x"] > 50 and _near_box(m), (how, m)
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Firefox for Playwright is not installed (optional, docs/SKILL.md, Setup)")
        raise
    assert not errors


RUN_PARTS_DECK = """
# Run {#run}

```bbv-anim {#t program="find.bbv" height=520 panel_at=below}
```

```arrow {#v}
to: t.A2
angle: 0
```

```arrow {#b color=muted}
to: t.B
angle: 0
```

```arrow {#w color=ink}
to: t.B1
angle: 180
```
"""


def test_arrow_follows_versions_of_a_run(tmp_path):
    """Spec 8.9 and 9.5: hidden while its version is not drawn, on it while it glides, around all versions of a block."""
    import shutil
    from pathlib import Path

    shutil.copy(Path(__file__).resolve().parent.parent / "user_manual" / "programs" / "find.bbv", tmp_path)
    src = tmp_path / "talk.md"
    src.write_text(RUN_PARTS_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(400)
            vid = page.evaluate("""() => {
                const d = JSON.parse(document.getElementById('lt-data-run/t').textContent);
                const out = {};
                for (const [k, v] of Object.entries(d.tables.versions)) out[v.label] = k;
                return out;
            }""")
            a2 = f'.lt-bbv-node[data-vid="{vid["A2"]}"]'
            blocks_b = f'.lt-bbv-node[data-vid="{vid["B1"]}"], .lt-bbv-node[data-vid="{vid["B2"]}"]'
            assert not page.evaluate(PARTS_JS, ["run/v", a2])["shown"]  # A2 does not exist at frame 0
            page.goto(out.as_uri() + "#/run/22")
            page.wait_for_timeout(400)
            m = page.evaluate(PARTS_JS, ["run/v", a2])
            assert m["shown"] and _near_box(m), m
            # frames 23 to 24 move B1: halfway through the glide the head is still beside the moving node
            b1 = f'.lt-bbv-node[data-vid="{vid["B1"]}"]'
            page.goto(out.as_uri() + "#/run/23")
            page.wait_for_timeout(400)
            before = page.evaluate(PARTS_JS, ["run/w", b1])["box"]
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(170)
            mid = page.evaluate(PARTS_JS, ["run/w", b1])
            page.wait_for_timeout(600)
            end = page.evaluate(PARTS_JS, ["run/w", b1])
            assert abs(end["box"]["x"] - before["x"]) > 5, "B1 should move between frames 23 and 24"
            assert 2 < abs(mid["box"]["x"] - before["x"]) < abs(end["box"]["x"] - before["x"]) - 2, "not halfway"
            assert _near_box(mid, gap=20) and _near_box(end), (mid, end)
            # a block names all its drawn versions: the head is beside the box around B1 and B2
            m = page.evaluate(PARTS_JS, ["run/b", blocks_b])
            assert m["shown"] and _near_box(m), m
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


PROBE_PLUGIN = '''
from pathlib import Path
from lattice import Component, RenderResult, register


@register("probe")
class Probe(Component):
    body = "none"
    runtime = str(Path(__file__).with_name("probe.js"))

    def render(self, block, opts, ctx):
        return RenderResult('<div class="probe"></div>', data={}, positions=4)
'''

PROBE_JS = """
Lattice.component("probe", {
  mount(el) { return {}; },
  show(inst, position, info) { (window.__shows ||= []).push([position, info.animate]); },
});
"""


def test_a_hash_change_to_an_adjacent_step_does_not_animate(tmp_path):
    """Spec 7.2 and 10.1: a change of the URL hash is a jump, never animated, even to the next or previous step."""
    (tmp_path / "lattice_plugins.py").write_text(PROBE_PLUGIN)
    (tmp_path / "probe.js").write_text(PROBE_JS)
    src = tmp_path / "talk.md"
    src.write_text("# Probe {#pr}\n\n```probe {#p}\n```\n")
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(out.as_uri())
            page.wait_for_timeout(200)

            def shows_after(action):
                page.evaluate("window.__shows = []")
                action()
                page.wait_for_timeout(120)
                return page.evaluate("window.__shows")

            assert shows_after(lambda: page.keyboard.press("ArrowRight")) == [[1, True]]  # a single step animates
            assert shows_after(lambda: page.evaluate("location.hash = '#/pr/2'")) == [[2, False]]
            assert shows_after(lambda: page.evaluate("location.hash = '#/pr/1'")) == [[1, False]]
            assert shows_after(lambda: page.keyboard.press("ArrowLeft")) == [[0, True]]
            assert page.evaluate("Lattice.state().H") == []  # a hash change on the same slide records nothing
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors


SAME_TARGET_DECK = """
# Same target {#same}

```bbv-cfg {#g height=420}
source: |
  function f(x)
  A:  if fixnum?(x) goto L else goto L
  L:  return x
```

```arrow {#p}
steps:
  - {to: "g.A->L:#t", angle: 180}
  - {to: "g.A->L:#f", angle: 0}
```
"""


def test_two_edges_between_the_same_blocks_are_drawn_apart(tmp_path):
    """Spec 9.5: the `true` and `false` edges of `if x goto L else goto L` are both drawn, side by side, each with its
    own label and mark, so that an arrow can point at either."""
    src = tmp_path / "talk.md"
    src.write_text(SAME_TARGET_DECK)
    out = tmp_path / "talk.html"
    assert main(["build", str(src), "-o", str(out), "--no-cache"]) == 0
    geo = """() => Object.fromEntries(['true', 'false'].map(k => {
        const g = document.querySelector(`.lt-bbv-edge[data-key="1->2:${k}"]`);
        const l = g.querySelector('.lt-bbv-edge-label').getBBox(), m = g.querySelector('.lt-bbv-edge-mark').getBBox();
        return [k, {d: g.querySelector('path').getAttribute('d'), label: g.querySelector('.lt-bbv-edge-label').textContent,
                    lx: l.x + l.width / 2, mx: m.x + m.width / 2, my: m.y + m.height / 2, gone: g.classList.contains('lt-gone')}];
    }))"""
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
            page.goto(out.as_uri())
            page.wait_for_timeout(400)
            g = page.evaluate(geo)
            assert not g["true"]["gone"] and not g["false"]["gone"]
            assert (g["true"]["label"], g["false"]["label"]) == ("#t", "#f")
            assert g["true"]["d"] != g["false"]["d"]
            assert g["false"]["mx"] - g["true"]["mx"] > 30  # true on the left, false on the right, labels apart
            assert abs(g["true"]["lx"] - g["true"]["mx"]) < 1 and abs(g["false"]["lx"] - g["false"]["mx"]) < 1
            for i, k in enumerate(("true", "false")):
                if i:
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(500)
                m = page.evaluate(PARTS_JS, ["same/p", f'.lt-bbv-edge[data-key="1->2:{k}"] > .lt-bbv-edge-mark'])
                assert m["shown"] and _near_box(m), (k, m)
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors
