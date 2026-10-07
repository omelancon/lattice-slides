"""Lattice: compile Markdown into non-linear HTML slide decks."""
__version__ = "0.26.1"

from .anim import ArrayTrace, GraphTrace, GridTrace, Trace, TreeTrace  # noqa: E402,F401
from .components.base import (Component, ComponentError, Part, RenderContext, RenderResult,  # noqa: E402,F401
                              register)
from .diagnostics import BuildError, Diagnostics  # noqa: E402,F401


def build(path, output=None, *, use_cache: bool = True):
    """Build the deck at ``path``. Returns the HTML, and writes it to ``output`` if given."""
    from .build import build_deck
    from .emit import emit_html

    deck = build_deck(path, use_cache=use_cache)
    page = emit_html(deck)
    if output is not None:
        from pathlib import Path

        Path(output).write_text(page, encoding="utf-8")
    return page
