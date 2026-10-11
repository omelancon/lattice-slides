"""Sidecar notes (spec 3.14): ``FILE.notes.md`` beside the deck's main file holds speaker notes by slide id.

The sidecar is a list of sections. A line ``# ID`` (outside fenced code) starts the notes of the slide ``ID``;
what precedes the first such line is kept as written and ignored. ``lattice build`` renders each section after
the slide's static notes; ``lattice serve`` leaves them out of the page and serves them for the presenter view
to edit (``server.py``). Both render a section with ``render_section``, so the notes look the same either way.

Writing a section rewrites only that section: everything else in the file (the preamble, the other sections,
sections of unknown ids) is kept byte for byte.
"""
from __future__ import annotations

import html
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it import MarkdownIt

from .attrs import AttrError, parse_attr_block, split_name_and_attrs
from .components.base import REGISTRY
from .markdown import container_name, new_env, token_groups

HEAD_RE = re.compile(r"# +([A-Za-z0-9][A-Za-z0-9_-]*)[ \t]*\Z")
_FENCE_RE = re.compile(r" {0,3}(`{3,}|~{3,})")
_TITLE_RE = re.compile(r"\x00T:([^\x00]*)\x00")
# options of a code block that sidecar notes honour; the others (file, lines, symbol, meta) need a build
CODE_OPTIONS = {"lang", "highlight", "linenos", "title", "markers", "line_base"}


def sidecar_path(root: Path) -> Path:
    """``talk.md`` -> ``talk.notes.md``."""
    return root.with_name(root.stem + ".notes.md")


@dataclass
class Section:
    id: str
    line: int   # 1-based line of the `# ID` heading
    raw: str    # the heading line through the line before the next heading, as written

    @property
    def text(self) -> str:
        """The Markdown of the notes: the lines after the heading, without surrounding blank lines."""
        return self.raw.split("\n", 1)[1].strip("\n").rstrip() if "\n" in self.raw else ""

    @property
    def text_line(self) -> int:
        """The line of the file where ``text`` starts."""
        rest = self.raw.split("\n", 1)[1] if "\n" in self.raw else ""
        return self.line + 1 + (len(rest) - len(rest.lstrip("\n")))


@dataclass
class Sidecar:
    preamble: str = ""
    sections: list[Section] = field(default_factory=list)

    def notes(self) -> dict[str, list[Section]]:
        """Sections by id, in file order (an id may appear more than once)."""
        out: dict[str, list[Section]] = {}
        for s in self.sections:
            out.setdefault(s.id, []).append(s)
        return out

    def text_of(self, ident: str) -> str:
        """The notes of ``ident``; the sections of an id given twice are joined, as the build shows them."""
        return "\n\n".join(t for t in (s.text for s in self.sections if s.id == ident) if t)

    def dump(self) -> str:
        return self.preamble + "".join(s.raw for s in self.sections)

    def set(self, ident: str, text: str, order: list[str]) -> None:
        """Replace the notes of ``ident`` by ``text`` (``""`` removes them). A section that does not exist yet
        goes before the first section of a slide that comes after ``ident`` in ``order``, else at the end.
        The other sections of an id given twice are removed, their text being part of ``text``."""
        text = text.strip("\n").rstrip()
        mine = [i for i, s in enumerate(self.sections) if s.id == ident]
        for i in reversed(mine[1:]):
            del self.sections[i]
        if not text:
            if mine:
                del self.sections[mine[0]]
            self._end()
            return
        new = Section(ident, 0, f"# {ident}\n\n{text}\n")
        if mine:
            at = mine[0]
            self.sections[at] = new
        else:
            later = set(order[order.index(ident) + 1:]) if ident in order else set()
            at = next((i for i, s in enumerate(self.sections) if s.id in later), len(self.sections))
            self.sections.insert(at, new)
        # a blank line between the section and its neighbours
        if at > 0:
            prev = self.sections[at - 1]
            prev.raw = prev.raw.rstrip("\n") + "\n\n"
        elif self.preamble.strip():
            self.preamble = self.preamble.rstrip("\n") + "\n\n"
        else:
            self.preamble = ""
        if at < len(self.sections) - 1:
            new.raw += "\n"
        self._end()

    def _end(self) -> None:
        """The file ends with one newline, whichever section is now last."""
        if self.sections:
            last = self.sections[-1]
            last.raw = last.raw.rstrip("\n") + "\n"


def parse(text: str) -> Sidecar:
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    starts: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    for i, line in enumerate(lines):
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = (m.group(1)[0], len(m.group(1)))
                continue
            h = HEAD_RE.match(line)
            if h:
                starts.append((i, h.group(1)))
        elif m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] and not line.strip()[len(m.group(1)):].strip():
            fence = None
    keep_ends = text.splitlines(keepends=True)
    if not starts:
        return Sidecar(preamble=text)
    sc = Sidecar(preamble="".join(keep_ends[:starts[0][0]]))
    for n, (i, ident) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(keep_ends)
        sc.sections.append(Section(ident, i + 1, "".join(keep_ends[i:end])))
    return sc


def load(path: Path) -> Sidecar:
    try:
        return parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Sidecar()


def save(path: Path, sc: Sidecar) -> None:
    """Write atomically (a temporary file renamed over the sidecar); an empty sidecar removes the file."""
    data = sc.dump()
    if not data.strip():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------------------------- rendering
@dataclass
class Rendered:
    html: str
    links: list[str]                                       # wiki link targets, in order
    math: bool
    problems: list[tuple[int, str]] = field(default_factory=list)  # (line within the text, 1-based; message)


def code_html(lang: str, body: str, kv: dict[str, str] | None = None) -> str:
    """A code block as the ``code`` component draws it at rest, without a runtime instance."""
    from .components.code import CodeOptions, _render, load_source

    opts = CodeOptions(lang=lang, **(kv or {}))
    html_, _ = _render(opts, load_source(opts, body, None))
    return f'<div class="lt-c lt-c-code">{html_}</div>'


def fence_html(tok, problems: list[tuple[int, str]], line: int, where: str = "sidecar notes") -> str:
    """A fenced block in notes: a code block, drawn at once (notes have no component instances)."""
    from .body import _is_lexer

    name, attr_text = split_name_and_attrs(tok.info or "")
    kv: dict[str, str] = {}
    if attr_text:
        try:
            kv = dict(parse_attr_block(attr_text).kv)
        except AttrError as e:
            problems.append((line, f"code block: {e}"))
    if name in REGISTRY and name != "code":
        problems.append((line, f"component {name!r} is not supported in {where}; shown as code"))
        name, kv = "text", {}
    lang = kv.pop("lang", None) or name or "text"
    if lang != "text" and not _is_lexer(lang):
        problems.append((line, f"unknown language {lang!r}, shown as plain text"))
        lang = "text"
    dropped = sorted(set(kv) - CODE_OPTIONS)
    if dropped:
        problems.append((line, f"code block option(s) {', '.join(dropped)} not supported in {where}"))
    kv = {k: v for k, v in kv.items() if k in CODE_OPTIONS}
    try:
        return code_html(lang, tok.content, kv)
    except Exception as e:  # noqa: BLE001  (a bad option value, such as a range: show the text)
        problems.append((line, f"code block: {e}".split("\n")[0]))
        return code_html("text", tok.content)


def render_section(md: MarkdownIt, text: str) -> Rendered:
    """Render sidecar notes: Markdown, math, wiki links and code blocks, as static notes show them. Wiki link
    labels are title placeholders (``substitute_titles``); containers and directives are reported and left
    out (their content is kept), components are shown as code."""
    env = new_env(md)
    problems: list[tuple[int, str]] = []
    tokens = md.parse(text, env)
    out: list[str] = []

    def walk(groups) -> None:
        for g in groups:
            t = g[0]
            line = t.map[0] + 1 if t.map else 1
            if t.type == "fence":
                out.append(fence_html(t, problems, line))
            elif t.type == "container_lt_open":
                name, _ = container_name(t)
                problems.append((line, f"container {name or '(unnamed)'!r} is not supported in sidecar notes; "
                                       "its content is shown without it"))
                walk(token_groups(g[1:-1]))
            elif t.type in ("lt_include", "lt_badge"):
                problems.append((line, f"{t.type[3:]} directive is not supported in sidecar notes"))
            else:
                out.append(md.renderer.render(g, md.options, env))

    walk(token_groups(tokens))
    for (_, line), message in env.get("fence_problems", {}).items():
        problems.append((line + 1, message))
    problems.sort(key=lambda p: p[0])
    return Rendered("".join(out), list(dict.fromkeys(env["links"])), bool(env["math"]), problems)


def substitute_titles(text: str, title_of) -> str:
    """Replace the label placeholders of wiki links (``title_of(id)`` gives the escaped label)."""
    return _TITLE_RE.sub(lambda m: title_of(m.group(1)), text)


def deck_title_of(deck):
    from .graph import resolve_target

    def title(ident: str) -> str:
        t = resolve_target(deck, ident)
        return html.escape(deck.slides[t].title_text) if t else html.escape(ident)

    return title


def merge_into(deck, md: MarkdownIt) -> None:
    """``lattice build``: append each section of the sidecar to the static notes of its slide (spec 3.14).
    Unknown ids and ids given twice are warnings (LT067), and so is what notes cannot show (LT068); a wiki
    link to an unknown id is LT011, as in static notes."""
    from .diagnostics import SourceLoc
    from .graph import resolve_target

    path = sidecar_path(deck.root)
    if not path.is_file():
        return
    deck.dependencies.add(path)
    sc = load(path)
    where = Path(path.name)
    seen: set[str] = set()
    for sec in sc.sections:
        loc = SourceLoc(where, sec.line, 1)
        slide = deck.slides.get(sec.id)
        if slide is None:
            deck.diagnostics.warn("LT067", f"notes for unknown slide id {sec.id!r} (kept in the sidecar, not shown)",
                                  loc)
            continue
        if sec.id in seen:
            deck.diagnostics.warn("LT067", f"notes for {sec.id!r} given twice in the sidecar; both are shown", loc)
        seen.add(sec.id)
        r = render_section(md, sec.text)
        for line, message in r.problems:
            deck.diagnostics.warn("LT068", message, SourceLoc(where, sec.text_line + line - 1, 1))
        for target in r.links:
            if resolve_target(deck, target) is None:
                deck.diagnostics.error("LT011", f"link to unknown id {target!r}", loc)
            elif target not in slide.links:
                slide.links.append(target)
        if r.html:
            slide.notes_html = (slide.notes_html or "") + r.html
