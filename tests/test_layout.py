"""Layout checks in a real browser: nothing drawn in a column may spill into its neighbour, nothing drawn by
a component outside its box may cover another block of the slide, and nothing drawn in a slide may spill below
its body (over the footer).

Every slide of every example and of the user manual is visited at its first and at its last step.
Content inside a clipping
container (overflow other than `visible`, such as a scrolling code block) is skipped, since it cannot
paint outside that container, and so is the content of a collapsed column (spec 3.8), which paints nothing.
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
    if (col.closest(".lt-col-shut")) continue;
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
  // what a component draws does not cover the blocks around it (0.24 to 0.26: the caption of an animation without
  // `height` in a column, pushed out of the component's box over a paragraph under the columns)
  const blocks = Array.from(section.querySelectorAll(".lt-body > *, .lt-column > *, .lt-column-in > *"))
    .filter((b) => !b.closest(".lt-col-shut") && !b.classList.contains("lt-column-in") && getComputedStyle(b).position !== "absolute");
  for (const comp of section.querySelectorAll(".lt-c:not(.lt-c-arrow)")) {
    if (comp.closest(".lt-col-shut")) continue;
    const others = blocks.filter((b) => !b.contains(comp) && !comp.contains(b));
    const cb = comp.getBoundingClientRect();
    let found = null;
    for (const el of comp.querySelectorAll("*")) {
      // a drawing is letterboxed in its canvas, whose box is larger than what it paints: its text and panels count
      if (clipped(el, comp, "overflowY") || el.closest("svg, .lt-ga-canvas") !== null) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0 || (r.bottom <= cb.bottom + 1 && r.top >= cb.top - 1)) continue;
      const hit = others.find((b) => { const o = b.getBoundingClientRect();
        return o.width && o.height && r.left < o.right - 1 && o.left < r.right - 1 && r.top < o.bottom - 1 && o.top < r.bottom - 1; });
      if (hit) { found = `${el.tagName.toLowerCase()}.${el.className} of ${comp.dataset.instance} covers ${hit.tagName.toLowerCase()}.${hit.className}`; break; }
    }
    if (found) out.push(found);
  }
  const body = section.querySelector(".lt-body");
  if (body) {
    const bottom = body.getBoundingClientRect().bottom;
    for (const el of body.querySelectorAll("*")) {
      if (clipped(el, body, "overflowY") || el.closest("svg") !== null && el.tagName.toLowerCase() !== "svg") continue;
      if (el.closest(".lt-arrow-box") || getComputedStyle(el).position === "absolute") continue;  // overlays
      if (el.closest(".lt-col-shut")) continue;
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


def check_pages(pages):
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
    return problems


def test_columns_and_bodies_contain_their_content(tmp_path_factory):
    problems = check_pages(example_pages(tmp_path_factory))
    assert not problems, "\n".join(problems)


SHORT_ROOM = """
# Short room {#room}

::: columns
::: column
Some text on the left.
:::
::: column
```abstract-interp-anim {#ai program="sum-to-n.bbv" direction=LR}
```
:::
:::

A paragraph under the columns, which the caption must not cover.

# Beside {#beside}

```bbv-anim {#run program="sum-to-n.bbv" panel_at=right}
panel: [queue, versions]
```

A paragraph under the run, which takes some of the room.

A second one.
"""


def test_animations_without_height_fit_the_room_left(tmp_path):
    """Spec 9.5: without `height`, a versioning drawing shrinks to the room the slide leaves instead of pushing its
    caption out of its box; its size is the same at every frame (the caption claims only its minimum height)."""
    import shutil

    shutil.copy(MANUAL.parent / "programs" / "sum-to-n.bbv", tmp_path)
    (tmp_path / "talk.md").write_text(SHORT_ROOM)
    html = tmp_path / "talk.html"
    html.write_text(emit_html(build_deck(tmp_path / "talk.md", use_cache=False)), encoding="utf-8")
    assert check_pages([html]) == []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        for sid, inst in (("room", "room/ai"), ("beside", "beside/run")):
            sizes = set()
            page.goto(f"{html.as_uri()}#/{sid}/0")
            page.wait_for_timeout(250)
            steps = page.evaluate(f"JSON.parse(document.getElementById('lt-deck').textContent).slides['{sid}'].steps")
            for k in range(0, steps, max(1, steps // 8)):
                page.evaluate("(h) => { location.hash = h; }", f"#/{sid}/{k}")
                page.wait_for_timeout(60)
                sizes.add(tuple(page.evaluate("""(inst) => { const c = document.querySelector(`[data-instance="${inst}"] .lt-ga-canvas`);
                    const r = c.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }""", inst)))
            assert len(sizes) == 1, (sid, sizes)  # the drawing never rescales between frames
        browser.close()
