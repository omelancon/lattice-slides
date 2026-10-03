import json
import re
from pathlib import Path

import pytest

from lattice.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
MANUAL = Path(__file__).resolve().parent.parent / "user_manual" / "manual.md"


def test_new_and_build(tmp_path, capsys):
    assert main(["new", str(tmp_path / "demo")]) == 0
    out = tmp_path / "out.html"
    assert main(["build", str(tmp_path / "demo" / "talk.md"), "-o", str(out), "--no-cache"]) == 0
    html = out.read_text()
    deck = json.loads(re.search(r'id="lt-deck">(.*?)</script>', html, re.S).group(1))
    assert deck["lattice"] == 1 and deck["start"] == "demo"
    assert main(["check", str(tmp_path / "demo" / "talk.md")]) == 0


def test_check_reports_errors(tmp_path, capsys):
    p = tmp_path / "bad.md"
    p.write_text("# A\n[[missing]]\n")
    assert main(["check", str(p)]) == 1
    assert "LT011" in capsys.readouterr().err


@pytest.mark.parametrize("example", sorted(p.name for p in EXAMPLES.iterdir() if (p / "talk.md").is_file()))
def test_examples_build(example, tmp_path):
    assert main(["build", str(EXAMPLES / example / "talk.md"), "-o", str(tmp_path / "x.html"), "--no-cache"]) == 0


def test_user_manual_builds_without_warnings(tmp_path, capsys):
    """The manual uses every component and documents every feature: it must stay clean."""
    assert main(["check", str(MANUAL), "--strict", "--no-cache"]) == 0
    assert main(["build", str(MANUAL), "-o", str(tmp_path / "manual.html"), "--no-cache"]) == 0
    deck = json.loads(re.search(r'id="lt-deck">(.*?)</script>', (tmp_path / "manual.html").read_text(), re.S).group(1))
    used = {i["component"] for i in deck["instances"].values()}
    for name in ("graph-anim", "array-anim", "tree-anim", "grid-anim", "bbv-anim", "bbv-cfg", "abstract-interp-anim",
                 "code-steps", "diff-steps", "code-morph", "plot", "arrow", "stack-anim"):
        assert name in used, name
