"""Command line interface: build, check, serve, graph, new."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .diagnostics import BuildError, Diagnostics

TEMPLATE = """---
title: {title}
author: Your Name
---

# {title} {{layout=title}}

A Lattice deck.

# First idea

{{.reveal}}
- Press the right arrow to reveal each point
- Press `o` for the overview, `g` to jump to a slide

::: detour {{label="A side note" key=s}}
# A side note

Detours are nested slides. The last one returns to where you came from.
:::

# Some code

```python {{highlight=2}}
def greet(name):
    return f"Hello, {{name}}!"
```

# Thanks {{.center}}

Questions?
"""


def _print_diags(diags: Diagnostics, strict: bool = False) -> int:
    for d in diags.items:
        print(d.format(), file=sys.stderr)
    errors = len(diags.errors)
    warnings = len(diags.warnings)
    if errors or warnings:
        print(f"{errors} error(s), {warnings} warning(s)", file=sys.stderr)
    return 1 if errors or (strict and warnings) else 0


def cmd_build(args) -> int:
    from .build import build_deck
    from .emit import emit_dir, emit_html

    src = Path(args.deck)
    try:
        deck = build_deck(src, use_cache=not args.no_cache)
    except BuildError as e:
        return _print_diags(e.diagnostics) or 1
    except FileNotFoundError:
        print(f"lattice: no such file: {src}", file=sys.stderr)
        return 2
    if args.dir or (deck.meta.build.output == "dir" and not args.output):
        out_dir = Path(args.dir) if args.dir else src.with_suffix("")
        index = emit_dir(deck, out_dir)
        _print_diags(deck.diagnostics)
        print(f"lattice: wrote {index} ({len(deck.slides)} slides); serve the folder over HTTP, "
              f"for example: python -m http.server -d {out_dir}")
        return 0
    out = Path(args.output) if args.output else src.with_suffix(".html")
    page = emit_html(deck)
    if len(page.encode("utf-8")) > 50 * 1024 * 1024:
        deck.diagnostics.warn("LT032", "single-file output is larger than 50 MB; consider --dir")
    out.write_text(page, encoding="utf-8")
    _print_diags(deck.diagnostics)
    size = out.stat().st_size / 1024
    print(f"lattice: wrote {out} ({len(deck.slides)} slides, {size:.0f} KB)")
    return 0


def cmd_check(args) -> int:
    from .build import check_deck

    try:
        diags = check_deck(args.deck, use_cache=not args.no_cache)
    except FileNotFoundError:
        print(f"lattice: no such file: {args.deck}", file=sys.stderr)
        return 2
    code = _print_diags(diags, strict=args.strict)
    if code == 0:
        print("lattice: no problems found" if not diags.items else "lattice: ok", file=sys.stderr)
    return code


def cmd_serve(args) -> int:
    from .server import serve

    serve(Path(args.deck), host=args.host, port=args.port, use_cache=not args.no_cache)
    return 0


def cmd_graph(args) -> int:
    from .build import build_deck

    try:
        deck = build_deck(args.deck, use_cache=not args.no_cache)
    except BuildError as e:
        return _print_diags(e.diagnostics) or 1
    if args.dot:
        style = {"next": "", "branch": ' [color="#0b6e7f"]', "detour": ' [style=dashed, color="#8b7bc4"]',
                 "link": ' [style=dotted, color="#98a2b3"]'}
        print("digraph deck {\n  rankdir=LR; node [shape=box, style=rounded, fontname=Helvetica];")
        for s in deck.slides.values():
            extra = ", style=\"rounded,dashed\"" if s.offpath else ""
            print(f'  "{s.id}" [label="{s.title_text.replace(chr(34), "")}"{extra}];')
        for e in deck.edges:
            print(f'  "{e.source}" -> "{e.target}"{style[e.kind]};')
        print("}")
        return 0
    print(f"start: {deck.start}")
    print("main path: " + " -> ".join(deck.main_path))
    for s in deck.slides.values():
        nxt = s.next if s.next is not None else "(end)"
        flags = [f"scope={s.scope_id}"] if s.scope else []
        if s.offpath:
            flags.append("offpath")
        if s.steps > 1:
            flags.append(f"steps={s.steps}")
        print(f"  {s.id:<28} next={nxt:<22} {' '.join(flags)}")
        for e in deck.edges:
            if e.source == s.id and e.kind != "next":
                key = f" [{e.key}]" if e.key else ""
                print(f"      {e.kind}{key} -> {e.target}")
    return 0


def cmd_new(args) -> int:
    target = Path(args.path)
    if target.suffix != ".md":
        target.mkdir(parents=True, exist_ok=True)
        target = target / "talk.md"
    if target.exists():
        print(f"lattice: {target} already exists", file=sys.stderr)
        return 1
    title = target.parent.name.replace("-", " ").replace("_", " ").title() if target.name == "talk.md" else target.stem
    target.write_text(TEMPLATE.format(title=title or "My Talk"), encoding="utf-8")
    print(f"lattice: created {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lattice", description="Compile Markdown into non-linear slide decks.")
    p.add_argument("--version", action="version", version=f"lattice {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compile a deck to a single HTML file")
    b.add_argument("deck")
    b.add_argument("-o", "--output", help="output HTML file (single-file mode)")
    b.add_argument("--dir", help="write a directory (index.html, assets/, data/) instead of one file")
    b.add_argument("--no-cache", action="store_true")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("check", help="validate a deck")
    c.add_argument("deck")
    c.add_argument("--strict", action="store_true", help="fail on warnings too")
    c.add_argument("--no-cache", action="store_true")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("serve", help="serve a deck with live reload")
    s.add_argument("deck")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(func=cmd_serve)

    g = sub.add_parser("graph", help="print the slide graph")
    g.add_argument("deck")
    g.add_argument("--dot", action="store_true", help="output Graphviz DOT")
    g.add_argument("--no-cache", action="store_true")
    g.set_defaults(func=cmd_graph)

    n = sub.add_parser("new", help="scaffold a new deck")
    n.add_argument("path")
    n.set_defaults(func=cmd_new)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
