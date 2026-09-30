"""HTML output (spec section 11): single self-contained file, or a directory served over HTTP."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from pygments.formatters import HtmlFormatter

from . import __version__
from .components.base import REGISTRY
from .graphs import overview_layout
from .model import DEFAULT_KEYS, DEFAULT_TRANSITIONS, Deck
from .themes import get_theme

RUNTIME = resources.files("lattice") / "runtime"
DESIGN_SIZES = {"16:9": (1280, 720), "16:10": (1280, 800), "4:3": (1024, 768)}
SHARED_LIBS = {"vega": ["vega.min.js", "vega-lite.min.js"], "plotly": ["plotly.min.js"], "katex": ["katex.min.js"]}
_IMG_RE = re.compile(r'(<img\b[^>]*?\ssrc=")([^"]+)(")', re.I)


def _read(rel: str) -> str:
    return (RUNTIME / rel).read_text(encoding="utf-8")


def _json_script(obj) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name)


def _katex_css() -> str:
    css = _read("vendor/katex.min.css")

    def font(m: re.Match) -> str:
        w = re.search(r"url\(fonts/([^)]+\.woff2)\)", m.group(1))
        if not w:
            return m.group(0)
        data = base64.b64encode((RUNTIME / "vendor" / "fonts" / w.group(1)).read_bytes()).decode()
        return f"src:url(data:font/woff2;base64,{data}) format(\"woff2\")"

    return re.sub(r"src:([^;}]*)", font, css)


@dataclass
class Media:
    """Images referenced by slides: embedded as data URIs, or copied next to the output."""

    embed: bool
    files: dict[str, bytes] = field(default_factory=dict)

    def rewrite(self, fragment: str, base: Path, diags=None) -> str:
        def repl(m: re.Match) -> str:
            src = html.unescape(m.group(2))
            if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", src, re.I):
                return m.group(0)
            path = (base / src.split("?")[0].split("#")[0]).resolve()
            if not path.is_file():
                if diags is not None:
                    diags.warn("LT051", f"image not found: {src}")
                return m.group(0)
            data = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if self.embed:
                uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
            else:
                name = f"media/{hashlib.sha256(data).hexdigest()[:10]}-{_safe(path.stem)}{path.suffix}"
                self.files[name] = data
                uri = f"assets/{name}"
            return m.group(1) + uri + m.group(3)

        return _IMG_RE.sub(repl, fragment)


def deck_json(deck: Deck, *, data_urls: bool = False) -> dict:
    keys = {a: list(k) for a, k in DEFAULT_KEYS.items()}
    for action, k in deck.meta.keys.items():
        keys[action] = [k] if isinstance(k, str) else list(k)
    transitions = {**DEFAULT_TRANSITIONS, **deck.meta.transitions}
    slides = {}
    for s in deck.slides.values():
        branches = []
        for o in (s.branch.options if s.branch else []):
            target = o.target if o.target in deck.slides else deck.detours[o.target].slides[0].id
            label = re.sub(r"<[^>]+>", "", o.label_html) if o.label_html else deck.slides[target].title_text
            branches.append({"target": target, "key": o.key, "label": html.unescape(label)})
        entry = {
            "title": "" if s.untitled else s.title_text,
            "label": s.title_text,
            "scope": s.scope_id,
            "next": {"slide": s.next} if s.next not in (None, "back") else s.next,
            "branches": branches,
            "detours": [d.id for d in s.detours],
            "steps": s.steps,
            "tracks": [{"id": t.id, "kind": t.kind, **({"instance": t.instance} if t.instance else {}),
                        **({"follow": t.follow} if t.follow else {})} for t in s.tracks],
            "positions": s.positions,
            "offpath": s.offpath,
            "source": {"file": str(s.loc.file), "line": s.loc.line},
        }
        if s.transition:
            entry["transition"] = s.transition
        if s.notes_html:
            entry["notes"] = s.notes_html
        slides[s.id] = entry
    detours = {d.id: {"origin": d.origin.id, "entry": d.slides[0].id if d.slides else None, "label": d.label,
                      **({"key": d.key} if d.key else {}), "slides": [x.id for x in d.slides]}
               for d in deck.detours.values()}
    instances = {}
    for k, v in deck.instances.items():
        inst = {"component": v["component"], "slide": v["slide"], "data": None}
        if v["data"] is not None:
            if data_urls:
                inst["url"] = f"data/{_safe(k)}.json"
            else:
                inst["data"] = "lt-data-" + k
        instances[k] = inst
    data = {
        "lattice": 1,
        "version": __version__,
        "meta": {"title": deck.meta.title, "author": deck.meta.author, "date": deck.meta.date,
                 "aspect": deck.meta.aspect, "theme": deck.meta.theme},
        "start": deck.start,
        "keys": keys,
        "transitions": transitions,
        "order": list(deck.slides),
        "slides": slides,
        "detours": detours,
        "instances": instances,
        "tours": deck.tours,
        "mainPath": deck.main_path,
        "overview": overview_layout(deck),
    }
    canon = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    data["hash"] = hashlib.sha256(canon).hexdigest()[:16]
    return data


def slide_section(s, media: Media, diags) -> str:
    classes = " ".join(["lt-slide", f"layout-{s.layout}", *s.attrs.classes])
    if s.scope is not None:
        classes += " lt-in-detour"
    data = "".join(f' data-{k}="{html.escape(v, quote=True)}"' for k, v in s.data.items())
    head = "" if s.untitled else f'<header class="lt-head"><h1 class="lt-title">{s.title_html}</h1></header>'
    body = media.rewrite(s.body_html, s.path.parent, diags)
    return (f'<section class="{html.escape(classes)}" id="s-{html.escape(s.id)}" data-slide="{html.escape(s.id)}"'
            f'{data} hidden>{head}<div class="lt-body">{body}</div></section>')


@dataclass
class Page:
    """The pieces of an output page."""

    css: str
    libs: list[tuple[str, str]]  # (file name, source) of shared libraries
    runtime: str
    deck: dict
    data: dict[str, object]  # instance id -> data
    sections: str
    media: Media


def assemble(deck: Deck, *, embed: bool) -> Page:
    theme = get_theme(deck.meta.theme)
    pyg = HtmlFormatter(style=theme["pygments"]).get_style_defs(".lt-code pre")
    css = [_read("lattice.css"), _read(f"themes/{theme['css']}"), pyg]
    if deck.uses_math:
        css.append(_katex_css())
    seen: set[str] = set()
    for name in sorted(deck.component_names):
        for c in REGISTRY[name].css:
            if c not in seen:
                seen.add(c)
                p = Path(c)
                css.append(p.read_text(encoding="utf-8") if p.is_absolute() else _read(f"components/{c}"))
    requires = set(deck.requires) | ({"katex"} if deck.uses_math else set())
    libs = []
    for lib in sorted(requires):
        for f in SHARED_LIBS.get(lib, []):
            libs.append((f, _read(f"vendor/{f}")))
    js = [_read("lattice.js")]
    done: list[str] = []
    for name in sorted(deck.component_names):
        rt = REGISTRY[name].runtime
        if rt and rt not in done:
            done.append(rt)
            p = Path(rt)
            js.append(p.read_text(encoding="utf-8") if p.is_absolute() else _read(f"components/{rt}"))
    js.append("Lattice.boot();")
    media = Media(embed=embed)
    sections = "\n".join(slide_section(s, media, deck.diagnostics) for s in deck.slides.values())
    data = {k: v["data"] for k, v in deck.instances.items() if v["data"] is not None}
    return Page("".join(css), libs, "\n".join(js), deck_json(deck, data_urls=not embed), data, sections, media)


def _document(deck: Deck, page: Page, *, head: str, tail: str) -> str:
    w, h = DESIGN_SIZES[deck.meta.aspect]
    title = html.escape(deck.meta.title or "Lattice deck")
    return f"""<!doctype html>
<html lang="en" data-lattice="1" data-theme="{html.escape(deck.meta.theme)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="lattice {__version__}">
<title>{title}</title>
<style>:root{{--lt-w:{w}px;--lt-h:{h}px}}</style>
{head}
</head>
<body>
<div id="lt-root">
<main id="lt-stage"><div id="lt-viewport">
{page.sections}
<div id="lt-hud"><div id="lt-crumbs"></div><div id="lt-progress"></div></div>
</div></main>
<aside id="lt-presenter-panel" hidden></aside>
</div>
<div id="lt-overlay" hidden></div>
<script type="application/json" id="lt-deck">{_json_script(page.deck)}</script>
{tail}
</body>
</html>
"""


def emit_html(deck: Deck, *, live_reload: str | None = None) -> str:
    """The deck as one self-contained HTML document."""
    page = assemble(deck, embed=True)
    head = f'<style id="lt-theme">{page.css}</style>\n' + "".join(f"<script>{src}</script>\n" for _, src in page.libs)
    tail = "".join(f'<script type="application/json" id="lt-data-{html.escape(k)}">{_json_script(v)}</script>\n'
                   for k, v in page.data.items())
    tail += f'<script type="module">\n{page.runtime}\n</script>'
    if live_reload:
        tail += (f"\n<script>new EventSource({json.dumps(live_reload)}).onmessage=()=>location.reload();"
                 "</script>")
    return _document(deck, page, head=head, tail=tail)


def emit_dir(deck: Deck, out: Path) -> Path:
    """Write ``index.html``, ``assets/`` and ``data/`` into ``out``. Serve the folder over HTTP."""
    page = assemble(deck, embed=False)
    if out.exists():
        for sub in ("assets", "data"):
            shutil.rmtree(out / sub, ignore_errors=True)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(exist_ok=True)
    (out / "assets" / "lattice.css").write_text(page.css, encoding="utf-8")
    (out / "assets" / "lattice.js").write_text(page.runtime, encoding="utf-8")
    for name, src in page.libs:
        (out / "assets" / name).write_text(src, encoding="utf-8")
    for k, v in page.data.items():
        (out / "data" / f"{_safe(k)}.json").write_text(json.dumps(v, separators=(",", ":")), encoding="utf-8")
    for name, data in page.media.files.items():
        (out / "assets" / name).parent.mkdir(parents=True, exist_ok=True)
        (out / "assets" / name).write_bytes(data)
    head = '<link rel="stylesheet" href="assets/lattice.css">\n' + "".join(
        f'<script src="assets/{name}"></script>\n' for name, _ in page.libs)
    tail = '<script defer src="assets/lattice.js"></script>'
    index = out / "index.html"
    index.write_text(_document(deck, page, head=head, tail=tail), encoding="utf-8")
    return index
