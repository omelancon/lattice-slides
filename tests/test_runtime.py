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
