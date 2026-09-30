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
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not errors
