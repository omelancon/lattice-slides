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
