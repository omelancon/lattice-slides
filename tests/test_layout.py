"""Layout checks in a real browser: nothing drawn in a column may spill into its neighbour.

Every slide of every example is visited. Content inside a clipping container (overflow other than
`visible`, such as a scrolling code block) is skipped, since it cannot paint outside that container.
"""
from pathlib import Path

import pytest

from lattice.build import build_deck
from lattice.emit import emit_html

pw = pytest.importorskip("playwright.sync_api")

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

FIND_OVERFLOW = """(id) => {
  const out = [];
  for (const col of document.querySelectorAll(`#s-${CSS.escape(id)} .lt-column`)) {
    const box = col.getBoundingClientRect();
    for (const el of col.querySelectorAll("*")) {
      let clipped = false;
      for (let a = el.parentElement; a && a !== col; a = a.parentElement) {
        if (getComputedStyle(a).overflowX !== "visible") { clipped = true; break; }
      }
      if (clipped || el.closest("svg") !== null && el.tagName.toLowerCase() !== "svg") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > box.right + 1 || r.left < box.left - 1) {
        out.push(`${el.tagName.toLowerCase()}.${el.className} spills ${Math.round(Math.max(r.right - box.right, box.left - r.left))}px`);
        break;
      }
    }
  }
  return out;
}"""


def example_pages(tmp_path_factory):
    out = tmp_path_factory.mktemp("layout")
    pages = []
    for talk in sorted(EXAMPLES.glob("*/talk.md")):
        html = out / f"{talk.parent.name}.html"
        html.write_text(emit_html(build_deck(talk, use_cache=False)), encoding="utf-8")
        pages.append(html)
    return pages


def test_columns_do_not_overlap(tmp_path_factory):
    pages = example_pages(tmp_path_factory)
    problems = []
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            for html in pages:
                page.goto(html.as_uri())
                page.wait_for_timeout(200)
                for sid in page.evaluate("Object.keys(JSON.parse(document.getElementById('lt-deck').textContent).slides)"):
                    page.evaluate("(id) => Lattice.actions().jump(id)", sid)
                    page.wait_for_timeout(60)
                    for issue in page.evaluate(FIND_OVERFLOW, sid):
                        problems.append(f"{html.stem} #{sid}: {issue}")
            browser.close()
    except Exception as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    assert not problems, "\n".join(problems)
