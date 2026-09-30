"""Development server with live reload (``lattice serve``)."""
from __future__ import annotations

import html
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .build import build_deck
from .diagnostics import BuildError
from .emit import emit_html

RELOAD_PATH = "/__lattice/reload"


class DeckState:
    def __init__(self, root: Path, use_cache: bool):
        self.root = root
        self.use_cache = use_cache
        self.lock = threading.Lock()
        self.version = 0
        self.page = ""
        self.watched: dict[Path, float] = {}
        self.rebuild()

    def rebuild(self) -> None:
        started = time.time()
        deps = {self.root}
        try:
            deck = build_deck(self.root, use_cache=self.use_cache)
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
        with self.lock:
            self.page = page
            self.version += 1
            self.watched = {p: _mtime(p) for p in deps if ".lattice-cache" not in p.parts}

    def changed(self) -> bool:
        return any(_mtime(p) != m for p, m in list(self.watched.items())) or any(
            p not in self.watched for p in self.root.parent.rglob("*.md"))


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
            f"<script>new EventSource('{RELOAD_PATH}').onmessage=()=>location.reload();</script>")


def serve(root: Path, host: str = "127.0.0.1", port: int = 8000, use_cache: bool = True) -> None:
    state = DeckState(root.resolve(), use_cache)

    def watcher():
        while True:
            time.sleep(0.5)
            if state.changed():
                state.rebuild()

    threading.Thread(target=watcher, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):  # noqa: N802
            if self.path.startswith(RELOAD_PATH):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                seen = state.version
                try:
                    while True:
                        time.sleep(0.3)
                        if state.version != seen:
                            self.wfile.write(b"data: reload\n\n")
                            self.wfile.flush()
                            return
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            path = self.path.split("?")[0]
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

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"lattice: serving {root} at http://{host}:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
