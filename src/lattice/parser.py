"""Loading source files: includes, slide segmentation, detours and ids (spec sections 2, 3, 5)."""
from __future__ import annotations

import html as htmllib
import itertools
import re
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from pydantic import ValidationError

from .attrs import AttrError, Attrs, parse_attr_block, split_name_and_attrs, split_trailing_attrs, to_bool
from .diagnostics import Diagnostics, SourceLoc
from .ids import slugify
from .markdown import container_name, new_env, token_groups
from .model import Detour, FrontMatter, Slide

_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\x00T:([^\x00]*)\x00")
SLIDE_ATTRS = {"next", "offpath", "layout", "transition", "pdf"}


def html_to_text(fragment: str) -> str:
    text = _PLACEHOLDER_RE.sub(lambda m: m.group(1), fragment)
    return htmllib.unescape(_TAG_RE.sub("", text)).strip()


class Loader:
    def __init__(self, root_file: Path, md: MarkdownIt, diags: Diagnostics):
        self.root_file = root_file.resolve()
        self.base = self.root_file.parent
        self.md = md
        self.d = diags
        self.order: list[Slide] = []
        self.detours: list[Detour] = []
        self.files: list[Path] = []
        self.meta = FrontMatter()
        self._counter = itertools.count(1)

    # ------------------------------------------------------------------ utils
    def rel(self, path: Path) -> Path:
        try:
            return path.relative_to(self.base)
        except ValueError:
            return path

    def loc(self, file: Path, tok=None, line: int | None = None) -> SourceLoc:
        if line is None:
            line = (tok.map[0] + 1) if tok is not None and tok.map else 1
        return SourceLoc(self.rel(file), line, 1)

    def attrs_or_empty(self, text: str | None, loc: SourceLoc) -> Attrs:
        if not text:
            return Attrs()
        try:
            return parse_attr_block(text)
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
            return Attrs()

    # ------------------------------------------------------------------ load
    def load(self) -> list[Slide]:
        roots = self.parse_file(self.root_file, None, False, [], is_root=True)
        self.assign_ids()
        self.apply_slide_attrs()
        return roots

    def parse_file(self, path: Path, scope, offpath: bool, stack: list[Path], is_root=False) -> list[Slide]:
        self.files.append(path)
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        tokens = self.md.parse(text, new_env(self.md))
        if tokens and tokens[0].type == "front_matter":
            loc = self.loc(path, line=1)
            if not is_root:
                self.d.error("LT003", "front matter is only allowed in the root file", loc)
            else:
                self.read_front_matter(tokens[0].content, loc)
        counter = itertools.count(1)
        return self.segment(tokens, path, scope, offpath, stack + [path], counter)

    def read_front_matter(self, content: str, loc: SourceLoc) -> None:
        try:
            data = yaml.safe_load(content) or {}
            if not isinstance(data, dict):
                raise ValueError("front matter must be a mapping")
        except (yaml.YAMLError, ValueError) as e:
            self.d.error("LT048", f"invalid front matter: {e}", loc)
            return
        try:
            self.meta = FrontMatter(**data)
        except ValidationError as e:
            for err in e.errors():
                where = ".".join(str(p) for p in err["loc"])
                self.d.error("LT048", f"invalid front matter value for {where!r}: {err['msg']}", loc)
            return
        for key in (self.meta.model_extra or {}):
            self.d.warn("LT040", f"unknown front matter key {key!r}", loc)

    def segment(self, tokens, file: Path, scope, offpath: bool, stack, counter) -> list[Slide]:
        out: list[Slide] = []
        current: Slide | None = None
        reported = False
        for g in token_groups(tokens):
            t = g[0]
            if t.type == "front_matter":
                continue
            if t.type == "heading_open" and t.tag == "h1":
                loc = self.loc(file, t)
                if t.markup and t.markup[0] == "=":
                    self.d.error("LT001", "setext level-1 headings are not allowed; use '# Title'", loc)
                raw, attr_text = split_trailing_attrs(g[1].content)
                attrs = self.attrs_or_empty(attr_text, loc)
                current = Slide(raw_title=raw.strip(), attrs=attrs, loc=loc, file_index=next(counter),
                                scope=scope, offpath=offpath, path=file)
                out.append(current)
                self.order.append(current)
                continue
            if t.type == "lt_include":
                current = None
                out.extend(self.include(t, file, scope, offpath, stack))
                continue
            if current is None:
                if not reported:
                    where = "detour" if scope is not None else "file"
                    self.d.error("LT002", f"content before the first slide heading of this {where}",
                                 self.loc(file, t))
                    reported = True
                continue
            if t.type == "container_lt_open" and container_name(t)[0] == "detour":
                current.groups.append(("detour", self.detour(g, current, file, stack, counter)))
                continue
            current.groups.append(g)
        return out

    def include(self, tok, file: Path, scope, offpath: bool, stack) -> list[Slide]:
        loc = self.loc(file, tok)
        attrs = self.attrs_or_empty(tok.info, loc)
        name = attrs.get("file")
        if not name:
            self.d.error("LT009", "::include needs a file attribute", loc)
            return []
        path = (file.parent / name).resolve()
        if not path.is_file():
            self.d.error("LT006", f"included file not found: {name}", loc)
            return []
        if path in stack:
            self.d.error("LT004", f"include cycle: {name}", loc)
            return []
        if path in self.files:
            self.d.error("LT005", f"file included more than once: {name}", loc)
            return []
        try:
            inc_off = to_bool(attrs.get("offpath", "false"))
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
            inc_off = False
        return self.parse_file(path, scope, offpath or inc_off, stack)

    def detour(self, g, origin: Slide, file: Path, stack, counter) -> Detour:
        loc = self.loc(file, g[0])
        attrs = self.attrs_or_empty(container_name(g[0])[1], loc)
        d = Detour(key_obj=next(self._counter), origin=origin, attrs=attrs, loc=loc,
                   index_in_origin=len(origin.detours) + 1)
        origin.detours.append(d)
        self.detours.append(d)
        # Detour slides never inherit offpath: their chain must end with `back`.
        d.slides = self.segment(g[1:-1], file, d, False, stack, counter)
        if not d.slides:
            self.d.error("LT016", "detour contains no slides", loc)
        d.key = attrs.get("key")
        try:
            d.badge = to_bool(attrs.get("badge", "true"))
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
        try:
            d.blocking = to_bool(attrs.get("blocking", "false"))
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
        if "at" in attrs.kv:
            if attrs.kv["at"].isdigit():
                d.at = int(attrs.kv["at"])
            else:
                self.d.error("LT009", f"detour attribute at={attrs.kv['at']!r} must be a step number", loc)
        return d

    # ------------------------------------------------------------------ ids
    def assign_ids(self) -> None:
        taken: dict[str, object] = {}
        for s in self.order:
            env = new_env(self.md)
            s.title_html = self.md.renderInline(s.raw_title, env) if s.raw_title else ""
            s.untitled = not s.raw_title
            s.title_text = html_to_text(s.title_html)
            s.links.extend(env["links"])
            s.uses_math = s.uses_math or env["math"]
        for obj in [*self.order, *self.detours]:
            if obj.attrs.id:
                if obj.attrs.id in taken:
                    self.d.error("LT007", f"duplicate id {obj.attrs.id!r}", obj.loc)
                else:
                    taken[obj.attrs.id] = obj
                obj.id = obj.attrs.id

        def unique(base: str, obj) -> str:
            cand, n = base, 1
            while cand in taken:
                n += 1
                cand = f"{base}-{n}"
            if cand != base:
                self.d.warn("LT008", f"auto id {base!r} already used, renamed to {cand!r}", obj.loc)
            taken[cand] = obj
            return cand

        for s in self.order:
            if not s.id:
                base = slugify(s.title_text)
                if not base:
                    base = f"{slugify(s.loc.file.stem) or 'slide'}-{s.file_index}"
                s.id = unique(base, s)
        for d in self.detours:
            if not d.id:
                d.id = unique(f"{d.origin.id}-detour-{d.index_in_origin}", d)
        for s in self.order:
            if s.untitled:
                s.title_text = s.id
        for d in self.detours:
            d.label = d.attrs.get("label") or (d.slides[0].title_text if d.slides else d.id)

    def apply_slide_attrs(self) -> None:
        for s in self.order:
            for key, val in s.attrs.kv.items():
                if key == "next":
                    s.next_spec = val
                elif key == "offpath":
                    try:
                        s.offpath = s.offpath or to_bool(val)
                    except AttrError as e:
                        self.d.error("LT009", str(e), s.loc)
                elif key == "layout":
                    s.layout = val
                elif key == "transition":
                    s.transition = val
                elif key == "pdf":
                    from .pdf import parse_steps

                    try:
                        s.pdf_steps = parse_steps(val)
                    except ValueError as e:
                        self.d.error("LT053", str(e), s.loc)
                else:
                    self.d.warn("LT010", f"unknown slide attribute {key!r}", s.loc)
                    s.data[key] = val
