"""PDF export (spec 11.5): the plan is checked without a browser, the file itself with Chromium."""
import re

import pytest

from lattice.build import build_deck, check_deck
from lattice.cli import main
from lattice.pdf import PdfError, parse_steps, pdf_plan, select_steps

DECK = """
---
title: T
tours:
  short: [intro, end]
---
# Intro
{.reveal}
- a
- b

# Middle {pdf="0,end"}
{.reveal}
- a
- b

See [[backup]].

::::: detour {#more label="More" key=m}
# More one
::: detour {#deeper label="Deeper"}
# Deepest
:::
# More two
:::::

# Choice
::: branch
- [[left]]
- [[right]]
:::

# Left {next=end}
# Right {next=end}

# End {#end}

# Backup {offpath=true}
"""


def codes(diags):
    return {d.code for d in diags.items}


def test_parse_and_select_steps():
    assert parse_steps("last") == "last"
    assert parse_steps("0, 3,end") == [0, 3, "end"]
    for bad in ("", "1..3", "later", "1,,2", "-1"):
        with pytest.raises(ValueError):
            parse_steps(bad)
    assert select_steps("first", 4) == [0]
    assert select_steps("last", 4) == [3]
    assert select_steps("all", 3) == [0, 1, 2]
    assert select_steps([2, "end", 0, 3], 4) == [0, 2, 3]


def test_pdf_attribute_diagnostics(deck):
    root = deck({"talk.md": "# A {pdf=sometimes}\n# B {pdf=\"0,5\"}\n"})
    diags = check_deck(root, use_cache=False)
    assert "LT053" in codes(diags) and "LT010" not in codes(diags)
    root = deck({"talk.md": "# A {pdf=\"0,5\"}\n{.reveal}\n- x\n"})
    msgs = [d.message for d in check_deck(root, use_cache=False).items if d.code == "LT053"]
    assert msgs and "out of range" in msgs[0]


def test_plan_follows_the_main_path_then_the_appendix(deck):
    d = build_deck(deck({"talk.md": DECK}), use_cache=False)
    plan = pdf_plan(d)
    pages = [(p["slide"], p["step"]) for p in plan["pages"]]
    assert pages[:3] == [("intro", 2), ("middle", 0), ("middle", 2)]  # default last, then the pdf attribute
    main_pages = [p["slide"] for p in plan["pages"] if p["section"] is None]
    assert main_pages[-1] == "choice"  # the main path stops at the branch
    titles = [s["title"] for s in plan["sections"]]
    assert titles == ["More", "Option 1: Left", "Option 2: Right", "Deeper", "Linked slides"]
    by_slide = {p["slide"]: p for p in plan["pages"]}
    assert by_slide["more-one"]["from"] == plan["pageOf"]["middle"]
    assert by_slide["deepest"]["from"] == plan["pageOf"]["more-one"]
    assert [p["slide"] for p in plan["pages"] if p["section"] == 1] == ["left", "end"]
    assert [p["slide"] for p in plan["pages"] if p["section"] == 2] == ["right"]  # stops at a printed slide
    assert by_slide["backup"]["from"] == plan["pageOf"]["middle"]
    assert [p["n"] for p in plan["pages"]] == list(range(1, len(plan["pages"]) + 1))


def test_plan_options(deck):
    d = build_deck(deck({"talk.md": DECK}), use_cache=False)
    short = pdf_plan(d, tour="short", steps="all", appendix=False)
    assert [(p["slide"], p["step"]) for p in short["pages"]] == [("intro", 0), ("intro", 1), ("intro", 2), ("end", 0)]
    assert short["sections"] == []
    with pytest.raises(PdfError, match="available: main, short"):
        pdf_plan(d, tour="nope")


def test_cli_unknown_tour(deck, capsys):
    root = deck({"talk.md": DECK})
    assert main(["pdf", str(root), "--tour", "nope", "--no-cache"]) == 2
    assert "unknown tour" in capsys.readouterr().err


def test_export(deck, tmp_path):
    pytest.importorskip("playwright.sync_api")
    root = deck({"talk.md": DECK})
    out = tmp_path / "talk.pdf"
    try:
        code = main(["pdf", str(root), "-o", str(out), "--no-cache"])
    except Exception as e:  # noqa: BLE001
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    if code == 2:
        pytest.skip("Chromium for Playwright is not available")
    data = out.read_bytes()
    plan = pdf_plan(build_deck(root, use_cache=False))
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page\b(?!s)", data)) == len(plan["pages"])
    assert b"/Link" in data  # detour badges, branch options, wiki links and back links point inside the file
