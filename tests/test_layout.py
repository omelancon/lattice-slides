"""Layout checks in a real browser: nothing drawn in a column may spill into its neighbour, and
nothing drawn in a slide may spill below its body (over the footer).

Every slide of every example and of the user manual is visited at its first and at its last step.
Content inside a clipping
container (overflow other than `visible`, such as a scrolling code block) is skipped, since it cannot
paint outside that container.
"""
from pathlib import Path

import pytest

from lattice.build import build_deck
from lattice.emit import emit_html

pw = pytest.importorskip("playwright.sync_api")

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MANUAL = Path(__file__).resolve().parent.parent / "user_manual" / "manual.md"

FIND_OVERFLOW = """(id) => {
  const out = [];
  const clipped = (el, root, axis) => {
    for (let a = el.parentElement; a && a !== root; a = a.parentElement) {
      if (getComputedStyle(a)[axis] !== "visible") return true;
    }
    return false;
  };
  const section = document.querySelector(`#s-${CSS.escape(id)}`);
  for (const col of section.querySelectorAll(".lt-column")) {
    const box = col.getBoundingClientRect();
    for (const el of col.querySelectorAll("*")) {
      if (clipped(el, col, "overflowX") || el.closest("svg") !== null && el.tagName.toLowerCase() !== "svg") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > box.right + 1 || r.left < box.left - 1) {
        out.push(`${el.tagName.toLowerCase()}.${el.className} spills ${Math.round(Math.max(r.right - box.right, box.left - r.left))}px sideways`);
        break;
      }
    }
  }
  const body = section.querySelector(".lt-body");
  if (body) {
    const bottom = body.getBoundingClientRect().bottom;
    for (const el of body.querySelectorAll("*")) {
      if (clipped(el, body, "overflowY") || el.closest("svg") !== null && el.tagName.toLowerCase() !== "svg") continue;
      if (el.closest(".lt-arrow-box") || getComputedStyle(el).position === "absolute") continue;  // overlays
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.bottom > bottom + 1) {
        out.push(`${el.tagName.toLowerCase()}.${el.className} spills ${Math.round(r.bottom - bottom)}px below the body`);
        break;
      }
    }
  }
  return out;
}"""


def example_pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("layout")
    pages = []
    for talk in sorted(EXAMPLES.glob("*/talk.md")) + [MANUAL]:
        html = out / f"{talk.parent.name}.html"
        html.write_text(emit_html(build_deck(talk, use_cache=False)), encoding="utf-8")
        pages.append(html)
    return pages


def test_columns_and_bodies_contain_their_content(tmp_path_factory):
    pages = example_pages(tmp_path_factory)
    problems = []
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            for html in pages:
                page.goto(html.as_uri())
                page.wait_for_timeout(200)
                slides = page.evaluate("JSON.parse(document.getElementById('lt-deck').textContent).slides")
                for sid, slide in slides.items():
                    for step in sorted({0, slide["steps"] - 1}):
                        page.evaluate("(h) => { location.hash = h; }", f"#/{sid}/{step}")
                        page.wait_for_timeout(80)
                        assert page.evaluate("Lattice.state().cur") == {"slide": sid, "step": step}
                        for issue in page.evaluate(FIND_OVERFLOW, sid):
                            problems.append(f"{html.stem} #{sid} step {step}: {issue}")
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not problems, "\n".join(problems)
