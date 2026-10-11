"""Development server with live reload (``lattice serve``), and the sidecar notes it lets the presenter edit."""
from __future__ import annotations

import html
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import notes as sidecar
from .build import build_deck
from .diagnostics import BuildError
from .emit import emit_html
from .markdown import create_markdown

RELOAD_PATH = "/__lattice/reload"
NOTES_PATH = "/__lattice/notes"
MAX_NOTES_BYTES = 1 << 20


class DeckState:
    def __init__(self, root: Path, use_cache: bool):
        self.root = root
        self.use_cache = use_cache
        self.sidecar = sidecar.sidecar_path(root)
        self.md = create_markdown()
        self.lock = threading.Lock()
        self.notes_lock = threading.Lock()  # one write of the sidecar at a time
        self.version = 0        # bumped by every rebuild: the pages reload
        self.notes_version = 0  # bumped when the sidecar changes: the pages refetch the notes
        self.page = ""
        self.deck = None        # the last deck that built, for rendering notes
        self.watched: dict[Path, float] = {}
        self.sidecar_mtime = _mtime(self.sidecar)
        self.rebuild()

    def rebuild(self) -> None:
        started = time.time()
        deps = {self.root}
        deck = None
        try:
            deck = build_deck(self.root, use_cache=self.use_cache, sidecar=False)
            deck.serve_notes = NOTES_PATH
            deck.uses_math = True  # notes typed in the presenter view may hold math
            page = emit_html(deck, live_reload=RELOAD_PATH)
            deps |= set(deck.dependencies)
            for d in deck.diagnostics.warnings:
                print(d.format())
            print(f"lattice: built {len(deck.slides)} slides in {time.time() - started:.2f}s")
        except BuildError as e:
            page = error_page(e.diagnostics.format())
            print(e.diagnostics.format())
            deps |= self.watched.keys()
        except Exception as e:  # noqa: BLE001
            page = error_page(f"{type(e).__name__}: {e}")
            print(f"lattice: build failed: {e}")
            deps |= self.watched.keys()
        # watch every .md/.py file next to the deck as well (new includes)
        deps |= set(self.root.parent.rglob("*.md")) | set(self.root.parent.rglob("*.py"))
        deps.discard(self.sidecar)  # the sidecar never rebuilds: see check_sidecar
        with self.lock:
            self.page = page
            if deck is not None:
                self.deck = deck
            self.version += 1
            self.watched = {p: _mtime(p) for p in deps if ".lattice-cache" not in p.parts}

    def changed(self) -> bool:
        return any(_mtime(p) != m for p, m in list(self.watched.items())) or any(
            p not in self.watched and p != self.sidecar for p in self.root.parent.rglob("*.md"))

    def check_sidecar(self) -> None:
        """An edit of the sidecar made elsewhere (an editor) is sent to the pages as a `notes` event."""
        with self.notes_lock:
            m = _mtime(self.sidecar)
            if m != self.sidecar_mtime:
                self.sidecar_mtime = m
                self.notes_version += 1

    # ---------------------------------------------------------------------------------------- notes
    def render_notes(self, deck, text: str) -> dict:
        from .graph import resolve_target

        r = sidecar.render_section(self.md, text)
        problems = [f"line {line}: {message}" for line, message in r.problems]
        problems += [f"link to unknown id {t!r}" for t in r.links if resolve_target(deck, t) is None]
        return {"md": text, "html": sidecar.substitute_titles(r.html, sidecar.deck_title_of(deck)),
                "problems": problems}

    def all_notes(self) -> dict:
        with self.lock:
            deck = self.deck
        if deck is None:
            return {"slides": {}}
        sc = sidecar.load(self.sidecar)
        slides = {}
        for ident in dict.fromkeys(s.id for s in sc.sections):
            if ident in deck.slides:
                slides[ident] = self.render_notes(deck, sc.text_of(ident))
        return {"slides": slides, "file": self.sidecar.name}

    def save_notes(self, ident: str, text: str) -> dict:
        with self.lock:
            deck = self.deck
        if deck is None or ident not in deck.slides:
            raise KeyError(ident)
        with self.notes_lock:
            sc = sidecar.load(self.sidecar)  # read again: the file may have been edited elsewhere
            sc.set(ident, text, list(deck.slides))
            sidecar.save(self.sidecar, sc)
            self.sidecar_mtime = _mtime(self.sidecar)
            self.notes_version += 1
        return self.render_notes(deck, sc.text_of(ident))


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return -1.0


def error_page(text: str) -> str:
    return (f"<!doctype html><meta charset=utf-8><title>Build failed</title>"
            f"<body style='font:15px/1.5 monospace;padding:32px;background:#fff4f4;color:#5a1a22'>"
            f"<h1 style='font:600 22px sans-serif'>The deck did not build</h1><pre>{html.escape(text)}</pre>"
            f"<p>Fix the source and save: this page reloads automatically.</p>"
            f"<script>new EventSource('{RELOAD_PATH}').onmessage=(e)=>{{if(e.data!=='notes')location.reload();}};"
            f"</script>")


def make_handler(state: DeckState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status: int, obj) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path.startswith(RELOAD_PATH):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                seen, seen_notes = state.version, state.notes_version
                try:
                    while True:
                        time.sleep(0.3)
                        if state.version != seen:
                            self.wfile.write(b"data: reload\n\n")
                            self.wfile.flush()
                            return
                        if state.notes_version != seen_notes:
                            seen_notes = state.notes_version
                            self.wfile.write(b"data: notes\n\n")
                        else:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            path = self.path.split("?")[0]
            if path == NOTES_PATH:
                self.send_json(200, state.all_notes())
                return
            if path in ("/", "/index.html"):
                with state.lock:
                    body = state.page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            # static files next to the deck (images referenced by relative paths)
            target = (state.root.parent / path.lstrip("/")).resolve()
            if state.root.parent in target.parents and target.is_file():
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)

        def do_POST(self):  # noqa: N802
            if self.path.split("?")[0] != NOTES_PATH:
                self.send_error(404)
                return
            # only the deck's own pages write: a JSON body (other sites cannot send one without a preflight
            # this server never answers) and, when the browser names it, the same origin
            origin = self.headers.get("Origin")
            if origin and origin.split("://", 1)[-1] != self.headers.get("Host", ""):
                self.send_json(403, {"error": "cross-origin request"})
                return
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                self.send_json(415, {"error": "expected application/json"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_NOTES_BYTES:
                self.send_json(413, {"error": "notes too long"})
                return
            try:
                req = json.loads(self.rfile.read(length).decode("utf-8"))
                ident, text = req["slide"], req["md"]
                if not isinstance(ident, str) or not isinstance(text, str):
                    raise TypeError
            except (ValueError, KeyError, TypeError):
                self.send_json(400, {"error": "expected {\"slide\": ID, \"md\": TEXT}"})
                return
            try:
                result = state.save_notes(ident, text)
            except KeyError:
                self.send_json(404, {"error": f"no slide {ident!r} in the deck"})
                return
            except OSError as e:
                self.send_json(500, {"error": f"cannot write {state.sidecar.name}: {e}"})
                return
            self.send_json(200, result)

    return Handler


def serve(root: Path, host: str = "127.0.0.1", port: int = 8000, use_cache: bool = True) -> None:
    state = DeckState(root.resolve(), use_cache)

    def watcher():
        while True:
            time.sleep(0.5)
            if state.changed():
                state.rebuild()
            state.check_sidecar()

    threading.Thread(target=watcher, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"lattice: serving {root} at http://{host}:{port}/  (Ctrl+C to stop)")
    print(f"lattice: notes edited in the presenter view (p) are saved to {state.sidecar.name}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
