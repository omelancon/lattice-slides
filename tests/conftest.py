import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def deck(tmp_path):
    """Write files into a temporary project and return the path of the first one."""

    def make(files: dict[str, str]) -> Path:
        first = None
        for name, text in files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
            first = first or p
        return first

    return make
