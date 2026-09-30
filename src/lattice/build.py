"""Build orchestration: load, build bodies, resolve, render (spec 8.1 and the pipeline of the report)."""
from __future__ import annotations

import html
import importlib
import re
from importlib.metadata import entry_points
from pathlib import Path

from . import components  # noqa: F401  (registers built-ins)
from .body import BodyBuilder
from .components.base import RegistryError, import_path
from .diagnostics import BuildError, Diagnostics, SourceLoc
from .graph import resolve_target, resolve_graph
from .markdown import create_markdown
from .model import Deck
from .parser import Loader
from .render import render_components

_TITLE_RE = re.compile(r"\x00T:([^\x00]*)\x00")


def load_plugins(deck_root: Path, names: list[str], diags: Diagnostics) -> list[Path]:
    loaded: list[Path] = []
    try:
        eps = {ep.name: ep for ep in entry_points(group="lattice.plugins")}
    except TypeError:  # pragma: no cover
        eps = {}
    for name in names:
        try:
            if name in eps:
                eps[name].load()
            else:
                importlib.import_module(name)
        except RegistryError as e:
            diags.error("LT044", str(e))
        except Exception as e:  # noqa: BLE001
            diags.error("LT050", f"cannot load plugin {name!r}: {e}")
    local = deck_root.parent / "lattice_plugins.py"
    if local.is_file():
        try:
            import_path(local)
            loaded.append(local)
        except RegistryError as e:
            diags.error("LT044", str(e), SourceLoc(Path(local.name)))
        except Exception as e:  # noqa: BLE001
            diags.error("LT050", f"cannot import lattice_plugins.py: {e}", SourceLoc(Path(local.name)))
    return loaded


def build_deck(path: str | Path, *, use_cache: bool = True) -> Deck:
    root = Path(path).resolve()
    if not root.is_file():
        raise FileNotFoundError(root)
    diags = Diagnostics()
    md = create_markdown()
    loader = Loader(root, md, diags)
    loader.load()
    deck = Deck(root=root, meta=loader.meta, slides={}, detours={}, diagnostics=diags, files=list(loader.files))
    for s in loader.order:
        deck.slides.setdefault(s.id, s)
    for d in loader.detours:
        deck.detours.setdefault(d.id, d)
    if deck.meta.title is None:
        deck.meta.title = root.stem
    from .themes import THEMES

    if deck.meta.theme not in THEMES:
        diags.warn("LT052", f"unknown theme {deck.meta.theme!r}; using 'default' (available: {', '.join(THEMES)})",
                   SourceLoc(Path(root.name), 1, 1))
    deck.dependencies.update(loader.files)
    deck.dependencies.update(load_plugins(root, deck.meta.plugins, diags))
    diags.raise_if_errors()

    builder = BodyBuilder(md, diags, loader.rel)
    for s in deck.slides.values():
        builder.build(s)
    resolve_graph(deck)
    diags.raise_if_errors()

    render_components(deck, use_cache=use_cache)

    def title(m: re.Match) -> str:
        t = resolve_target(deck, m.group(1))
        return html.escape(deck.slides[t].title_text) if t else html.escape(m.group(1))

    for s in deck.slides.values():
        s.body_html = _TITLE_RE.sub(title, s.body_html)
        if s.notes_html:
            s.notes_html = _TITLE_RE.sub(title, s.notes_html)
        if 'class="lt-math' in s.body_html or (s.notes_html and 'class="lt-math' in s.notes_html):
            s.uses_math = True
    deck.uses_math = any(s.uses_math for s in deck.slides.values())
    diags.raise_if_errors()
    return deck


def check_deck(path: str | Path, *, use_cache: bool = True) -> Diagnostics:
    try:
        return build_deck(path, use_cache=use_cache).diagnostics
    except BuildError as e:
        return e.diagnostics
