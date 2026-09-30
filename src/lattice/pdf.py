"""PDF export following a tour (spec 11.5).

Python decides which pages exist (the plan); the runtime renders each one in print mode and copies it
into a print container; Chromium prints that container once, so links between pages keep working.
"""
from __future__ import annotations

import html
import re
import tempfile
from pathlib import Path

from .model import Deck

STEPS_RE = re.compile(r"^(?:first|last|all|(?:\d+|end)(?:,(?:\d+|end))*)$")


class PdfError(Exception):
    """A PDF export that cannot run: unknown tour, missing Playwright or Chromium."""


def parse_steps(value: str) -> str | list[int | str]:
    """Parse a ``pdf`` slide attribute or ``--steps`` value. Raises ``ValueError`` when malformed."""
    text = re.sub(r"\s+", "", value)
    if not STEPS_RE.match(text):
        raise ValueError(f"invalid pdf steps {value!r}: expected first, last, all or a list like 0,3,end")
    if text in ("first", "last", "all"):
        return text
    return [x if x == "end" else int(x) for x in text.split(",")]


def select_steps(spec: str | list, count: int) -> list[int]:
    """The steps (0-based) printed for a slide with ``count`` steps. Out-of-range indexes are dropped."""
    if spec == "first":
        return [0]
    if spec == "last":
        return [count - 1]
    if spec == "all":
        return list(range(count))
    picked = {count - 1 if x == "end" else x for x in spec}
    return sorted(i for i in picked if 0 <= i < count)


def check_steps(deck: Deck) -> None:
    """LT053 for ``pdf`` steps beyond the end of their slide (the syntax is checked by the parser)."""
    for s in deck.slides.values():
        if isinstance(s.pdf_steps, list):
            bad = [x for x in s.pdf_steps if x != "end" and x >= s.steps]
            if bad:
                deck.diagnostics.error("LT053", f"pdf step {bad[0]} is out of range: slide {s.id!r} has {s.steps} "
                                       f"step(s), numbered from 0", s.loc)


def pdf_plan(deck: Deck, *, tour: str | None = None, steps: str = "last", appendix: bool = True) -> dict:
    """Pages to print: the tour (default: the main path), then an appendix.

    The appendix holds, for every printed slide (recursively): its detours, the branch options not printed
    (each followed along ``next`` until a slide already printed), and the off-path slides it links to.
    Each page is ``{"slide", "step", "n", "section"}``, plus ``from`` (the page leading to it) in the
    appendix; ``section`` indexes ``sections`` (``{"code", "title", "kind"}``) or is ``None``.
    """
    from .graph import resolve_target

    if tour in (None, "main"):
        sequence = list(deck.main_path)
    elif tour in deck.tours:
        sequence = list(deck.tours[tour])
    else:
        names = ", ".join(["main", *deck.tours])
        raise PdfError(f"unknown tour {tour!r} (available: {names})")
    default = parse_steps(steps)
    pages: list[dict] = []
    page_of: dict[str, int] = {}

    def add(slide_id: str, section: int | None) -> None:
        s = deck.slides[slide_id]
        for step in select_steps(s.pdf_steps if s.pdf_steps is not None else default, s.steps):
            pages.append({"slide": slide_id, "step": step, "n": len(pages) + 1, "section": section})
            page_of.setdefault(slide_id, len(pages))

    for sid in sequence:
        add(sid, None)

    sections: list[dict] = []
    origin: dict[str, str] = {}  # appendix slide -> the printed slide that leads to it
    if appendix:
        queued = set(sequence)
        linked: list[str] = []
        todo = list(sequence)
        while todo:  # breadth first: nested detours and links of appendix slides come later
            batch, todo = todo, []
            for sid in batch:
                s = deck.slides[sid]
                for d in s.detours:
                    new = [x.id for x in d.slides if x.id not in queued]
                    if not new:
                        continue
                    queued.update(new)
                    origin.update({x: sid for x in new})
                    sections.append({"title": d.label, "kind": "detour", "slides": new})
                    todo.extend(new)
                for opt in (s.branch.options if s.branch else []):
                    chain, cur = [], resolve_target(deck, opt.target)
                    while cur and cur not in queued and cur in deck.slides:  # the option's own sequence
                        chain.append(cur)
                        queued.add(cur)
                        nxt = deck.slides[cur].next
                        cur = nxt if nxt not in (None, "back") else None
                    if chain:
                        origin.update({x: sid for x in chain})
                        label = html.unescape(re.sub(r"<[^>]+>", "", opt.label_html or "")) or deck.slides[chain[0]].title_text
                        sections.append({"title": f"Option {opt.key}: {label}", "kind": "branch", "slides": chain})
                        todo.extend(chain)
                for target in s.links:
                    t = resolve_target(deck, target)
                    if t and t not in queued and deck.slides[t].offpath and deck.slides[t].scope is None:
                        queued.add(t)
                        origin[t] = sid
                        linked.append(t)
                        todo.append(t)
        if linked:
            sections.append({"title": "Linked slides", "kind": "links", "slides": linked})
        for i, sec in enumerate(sections):
            sec["code"] = chr(ord("A") + i) if i < 26 else f"A{i}"
            for sid in sec.pop("slides"):
                add(sid, i)
    for page in pages:
        if page["slide"] in origin:
            page["from"] = page_of[origin[page["slide"]]]

    return {"title": deck.meta.title or "", "pages": pages, "pageOf": page_of, "sections": sections}


def export_pdf(deck: Deck, out: Path, *, tour: str | None = None, steps: str = "last",
               appendix: bool = True) -> tuple[int, list[str]]:
    """Write the PDF. Returns the page count and any JavaScript errors reported by the page."""
    from .emit import DESIGN_SIZES, emit_html

    plan = pdf_plan(deck, tour=tour, steps=steps, appendix=appendix)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise PdfError("PDF export needs Playwright: pip install 'lattice-slides[pdf]', "
                       "then: playwright install chromium") from e
    width, height = DESIGN_SIZES[deck.meta.aspect]
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "deck.html"
        page_file.write_text(emit_html(deck), encoding="utf-8")
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as e:  # noqa: BLE001
                if "Executable doesn't exist" in str(e):
                    raise PdfError("Chromium for Playwright is not installed: playwright install chromium") from e
                raise PdfError(f"cannot start Chromium: {e}") from e
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.goto(page_file.as_uri() + "?print")
                page.wait_for_function("document.documentElement.classList.contains('lt-ready')")
                count = page.evaluate("plan => Lattice.print(plan)", plan)
                page.evaluate("document.fonts.ready.then(() => true)")
                out.parent.mkdir(parents=True, exist_ok=True)
                page.pdf(path=str(out), width=f"{width}px", height=f"{height}px", print_background=True,
                         margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            finally:
                browser.close()
    return count, errors
