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
