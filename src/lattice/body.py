"""Building slide bodies: blocks, containers, reveal, branches, notes, components (spec 3.8 to 3.15)."""
from __future__ import annotations

import html
import re

from markdown_it import MarkdownIt
from pygments.lexers import find_lexer_class_by_name
from pygments.util import ClassNotFound

from .attrs import AttrError, Attrs, parse_attr_block, split_name_and_attrs
from .components.base import REGISTRY
from .diagnostics import Diagnostics, SourceLoc
from .markdown import container_name, new_env, title_placeholder, token_groups
from .model import Branch, BranchOption, ComponentBlock, Detour, Slide
from .timeline import parse_timeline

BUILTIN_CONTAINERS = {"detour", "branch", "notes", "columns", "column", "callout"}
_ATTR_LINE_RE = re.compile(r"\{[^{}]*\}\Z")
_BRANCH_ITEM_RE = re.compile(
    r"\s*\[\[\s*([A-Za-z0-9][A-Za-z0-9_-]*)\s*(?:\|([^\]]*))?\]\]\s*(\{[^{}]*\})?\s*(.*)\Z", re.S
)
_CSS_LEN_RE = re.compile(r"\d+(\.\d+)?(px|em|rem|%|vw|vh)\Z")


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _is_lexer(name: str) -> bool:
    try:
        find_lexer_class_by_name(name)
        return True
    except ClassNotFound:
        return False


class BodyBuilder:
    def __init__(self, md: MarkdownIt, diags: Diagnostics, rel):
        self.md = md
        self.d = diags
        self.rel = rel  # Path -> relative Path for locations

    def loc(self, slide: Slide, tok) -> SourceLoc:
        line = tok.map[0] + 1 if getattr(tok, "map", None) else slide.loc.line
        return SourceLoc(slide.loc.file, line, 1)

    # ------------------------------------------------------------------ entry
    def build(self, slide: Slide) -> None:
        self.slide = slide
        self.env = new_env(self.md)
        self.env["badge"] = self.placed_badge
        self.env["include"] = self.nested_include
        self.in_notes = False
        slide.body_html = self.render_groups(slide.groups, container=None)
        self.default_badges(slide)
        links = slide.links + self.env["links"]
        slide.links = list(dict.fromkeys(links))
        slide.uses_math = slide.uses_math or self.env["math"]
        self.assign_branch_keys(slide)

    # ------------------------------------------------------------------ walker
    def render_groups(self, groups, container: str | None) -> str:
        out: list[str] = []
        pending: Attrs | None = None
        for g in groups:
            if isinstance(g, tuple):
                # the default badge, kept only if no ::detour-badge places this detour (default_badges)
                out.append(f"\x00BADGE:{g[1].id}\x00")
                pending = None
                continue
            t = g[0]
            if t.type == "paragraph_open" and len(g) == 3:
                content = g[1].content.strip()
                if _ATTR_LINE_RE.match(content):
                    try:
                        pending = parse_attr_block(content)
                        continue
                    except AttrError:
                        pass
                first, sep, rest = content.partition("\n")
                if sep and _ATTR_LINE_RE.match(first.strip()):
                    # "{.reveal}" directly followed by text: the attributes apply to the rest
                    try:
                        pending = parse_attr_block(first.strip())
                        g[1].content = rest
                        g[1].children = self.md.parseInline(rest, self.env)[0].children
                    except AttrError:
                        pass
            self.group_loc = self.loc(self.slide, t)
            if t.type == "lt_include":
                self.d.error("LT034", "::include is only allowed at the top level of a file or of a detour",
                             self.loc(self.slide, t))
                continue
            if t.type == "heading_open" and t.tag == "h1" and container is not None:
                self.d.warn("LT041", "level-1 heading inside a container is not a slide boundary",
                            self.loc(self.slide, t))
            if t.type == "lt_badge":
                out.append(self.placed_badge(t, pending))
            elif t.type == "fence":
                out.append(self.fence(t, pending))
            elif t.type == "container_lt_open":
                out.append(self.container(g, pending))
            else:
                out.append(self.plain(g, pending))
            pending = None
        return "".join(out)

    def next_fragment(self) -> int:
        self.slide.reveal_count += 1
        return self.slide.reveal_count

    def wrapper_attrs(self, attrs: Attrs | None) -> tuple[dict[str, str], bool]:
        """HTML attributes from an attribute line, and whether it asks for reveal."""
        if attrs is None:
            return {}, False
        classes = [c for c in attrs.classes if c not in ("reveal", "reveal-with")]
        reveal = "reveal" in attrs.classes
        out: dict[str, str] = {}
        if attrs.id:
            out["id"] = attrs.id
        if classes:
            out["class"] = " ".join(classes)
        out.update(attrs.kv)
        if "reveal-with" in attrs.classes:
            # `.reveal-with`: the block joins the last fragment numbered so far instead of opening one (spec 3.12)
            loc = getattr(self, "group_loc", self.slide.loc)
            if reveal:
                self.d.error("LT057", "a block is either .reveal or .reveal-with, not both", loc)
            elif self.slide.reveal_count == 0:
                self.d.error("LT057", ".reveal-with needs a fragment before it on this slide", loc)
            else:
                out["data-lt-reveal"] = str(self.slide.reveal_count)
        return out, reveal

    @staticmethod
    def attrs_html(attrs: dict[str, str]) -> str:
        return "".join(f' {k}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())

    def plain(self, g, pending: Attrs | None) -> str:
        attrs, reveal = self.wrapper_attrs(pending)
        first = g[0]
        if reveal and first.type in ("bullet_list_open", "ordered_list_open"):
            for tok in g:
                if tok.type == "list_item_open" and tok.level == first.level + 1:
                    tok.attrSet("data-lt-reveal", str(self.next_fragment()))
            reveal = False
        if reveal:
            attrs["data-lt-reveal"] = str(self.next_fragment())
        if attrs and first.nesting == 1:
            for k, v in attrs.items():
                if k == "class":
                    first.attrJoin("class", v)
                else:
                    first.attrSet(k, v)
            attrs = {}
        rendered = self.md.renderer.render(g, self.md.options, self.env)
        if attrs:
            return f"<div{self.attrs_html(attrs)}>{rendered}</div>"
        return rendered

    # ------------------------------------------------------------------ fences
    def fence(self, tok, pending: Attrs | None) -> str:
        slide = self.slide
        loc = self.loc(slide, tok)
        name, attr_text = split_name_and_attrs(tok.info or "")
        try:
            attrs = parse_attr_block(attr_text) if attr_text else Attrs()
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
            attrs = Attrs()
        if name == "timeline":
            if slide.timeline is not None:
                self.d.error("LT029", "more than one timeline on this slide", loc)
                return ""
            slide.timeline = parse_timeline(tok.content, loc.line + 1, slide.loc.file, self.d)
            slide.timeline_loc = loc
            return ""
        if name in REGISTRY:
            comp_name = name
        else:
            comp_name = "code"
            lang = name or "text"
            if name and not _is_lexer(name):
                self.d.warn("LT020", f"unknown block {name!r}, rendered as plain text", loc)
                lang = "text"
            attrs.kv.setdefault("lang", lang)
        follow = attrs.kv.pop("follow", None)
        block = ComponentBlock(name=comp_name, attrs=attrs, body=tok.content, loc=loc,
                               file_dir=slide.path.parent, index=len(slide.components) + 1,
                               id=attrs.id, follow=follow)
        if block.id and any(c.id == block.id for c in slide.components):
            self.d.error("LT007", f"duplicate component id {block.id!r} on this slide", loc)
        wattrs, reveal = self.wrapper_attrs(pending)
        if attrs.classes:
            wattrs["class"] = " ".join(filter(None, [wattrs.get("class"), *attrs.classes]))
        if reveal:
            wattrs["data-lt-reveal"] = str(self.next_fragment())
        block.wrapper_attrs = wattrs
        slide.components.append(block)
        return block.placeholder

    # ------------------------------------------------------------------ containers
    def container(self, g, pending: Attrs | None) -> str:
        slide = self.slide
        open_tok = g[0]
        loc = self.loc(slide, open_tok)
        name, attr_text = container_name(open_tok)
        try:
            cattrs = parse_attr_block(attr_text) if attr_text else Attrs()
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
            cattrs = Attrs()
        inner = token_groups(g[1:-1])
        wattrs, reveal = self.wrapper_attrs(pending)
        if reveal:
            wattrs["data-lt-reveal"] = str(self.next_fragment())
        classes = [wattrs.pop("class", "")] + cattrs.classes
        if cattrs.id:
            wattrs.setdefault("id", cattrs.id)

        def cls(*extra: str) -> str:
            return " ".join(c for c in [*extra, *classes] if c)

        if name == "detour":
            self.d.error("LT034", "a detour must be at the top level of a slide body", loc)
            return ""
        if name == "branch":
            return self.branch(inner, cattrs, loc)
        if name == "notes":
            outer, self.in_notes = self.in_notes, True
            notes = self.render_groups(inner, container="notes")
            self.in_notes = outer
            slide.notes_html = (slide.notes_html or "") + notes
            return ""
        body = self.render_groups(inner, container=name)
        if name == "columns":
            style = f"gap:{cattrs.get('gap')}" if cattrs.get("gap") else ""
            if style:
                wattrs["style"] = style
            return f'<div class="{cls("lt-columns")}"{self.attrs_html(wattrs)}>{body}</div>'
        if name == "column":
            width = cattrs.get("width")
            if width:
                if width.endswith("fr"):
                    wattrs["style"] = f"flex:{width[:-2]} 1 0"
                elif _CSS_LEN_RE.match(width):
                    wattrs["style"] = f"flex:0 0 {width}"
            return f'<div class="{cls("lt-column")}"{self.attrs_html(wattrs)}>{body}</div>'
        if name == "callout":
            kind = cattrs.get("kind", "info")
            return f'<aside class="{cls("lt-callout", "lt-callout-" + kind)}"{self.attrs_html(wattrs)}>{body}</aside>'
        if name and name not in BUILTIN_CONTAINERS:
            near = [b for b in BUILTIN_CONTAINERS if _edit_distance(name, b) <= 2]
            if near:
                self.d.warn("LT019", f"unknown container {name!r}; did you mean {near[0]!r}?", loc)
        return f'<div class="{cls(name)}"{self.attrs_html(wattrs)}>{body}</div>'

    # ------------------------------------------------------------------ branch
    def branch(self, inner, cattrs: Attrs, loc: SourceLoc) -> str:
        slide = self.slide
        if slide.branch is not None:
            self.d.error("LT017", "a slide can contain only one branch", loc)
            return ""
        if any(t.type == "lt_badge" for grp in inner for t in grp):
            self.d.error("LT056", "a detour badge cannot be placed in a branch", loc)
            return ""
        if len(inner) != 1 or inner[0][0].type != "bullet_list_open":
            self.d.error("LT017", "a branch must contain exactly one bullet list", loc)
            return ""
        options: list[BranchOption] = []
        lst = inner[0]
        for tok_i, tok in enumerate(lst):
            if tok.type != "list_item_open" or tok.level != lst[0].level + 1:
                continue
            inline = next((t for t in lst[tok_i:] if t.type == "inline"), None)
            iloc = self.loc(slide, tok)
            m = _BRANCH_ITEM_RE.match(inline.content if inline else "")
            if not m:
                self.d.error("LT017", "each branch item must start with a [[link]]", iloc)
                continue
            target, label, attr_text, desc = m.groups()
            key = None
            if attr_text:
                try:
                    a = parse_attr_block(attr_text)
                    extra = set(a.kv) - {"key"}
                    if a.id or a.classes or extra:
                        raise AttrError("only 'key' is allowed on a branch item")
                    key = a.get("key")
                except AttrError as e:
                    self.d.error("LT017", str(e), iloc)
            label_html = self.md.renderInline(label.strip(), self.env) if label and label.strip() else None
            desc_html = self.md.renderInline(desc.strip(), self.env) if desc and desc.strip() else None
            options.append(BranchOption(target, label_html, desc_html, key, iloc))
        layout = cattrs.get("layout", "menu")
        slide.branch = Branch(options, layout, loc)
        return "\x00BRANCH\x00"

    def assign_branch_keys(self, slide: Slide) -> None:
        if slide.branch is None:
            return
        used = {o.key for o in slide.branch.options if o.key} | {d.key for d in slide.detours if d.key}
        free = (str(i) for i in range(1, 10) if str(i) not in used)
        for o in slide.branch.options:
            if o.key is None:
                o.key = next(free, None)
                if o.key is None:
                    self.d.error("LT018", "more than 9 branch options without explicit keys", o.loc)
        items = []
        for o in slide.branch.options:
            label = o.label_html if o.label_html is not None else title_placeholder(o.target)
            desc = f'<span class="lt-branch-desc">{o.description_html}</span>' if o.description_html else ""
            items.append(
                f'<button class="lt-branch-opt" type="button" data-lt-choose="{html.escape(o.key or "")}">'
                f'<kbd>{html.escape(o.key or "")}</kbd><span class="lt-branch-label">{label}</span>{desc}</button>'
            )
        menu = f'<div class="lt-branch lt-branch-{html.escape(slide.branch.layout)}">{"".join(items)}</div>'
        slide.body_html = slide.body_html.replace("\x00BRANCH\x00", menu)

    # ------------------------------------------------------------------ detours
    def detour_badge(self, d: Detour, mode: str | None, label: str, extra: dict[str, str] | None = None) -> str:
        key = f"<kbd>{html.escape(d.key)}</kbd>" if d.key else ""
        attrs = dict(extra or {})
        cls = " ".join(filter(None, ["lt-detour-badge", attrs.pop("class", None)]))
        # badge=step|next: the runtime shows it according to the step of the detour (spec 3.9, 10.4)
        if mode:
            attrs["data-lt-badge"] = mode
        return (f'<button class="{cls}" type="button" data-lt-detour="{html.escape(d.id)}"{self.attrs_html(attrs)}>'
                f'{key}<span>{html.escape(label)}</span></button>')

    def default_badges(self, slide: Slide) -> None:
        """Badges at the detour containers' positions, unless the detour has none or is placed elsewhere."""
        for d in slide.detours:
            html_ = ""
            if d.badge and not d.badges:
                html_ = self.detour_badge(d, d.badge_mode, d.label)
                d.badges.append((d.badge_mode, d.loc))
            slide.body_html = slide.body_html.replace(f"\x00BADGE:{d.id}\x00", html_)

    def nested_include(self, tok, pending) -> str:
        """`::include` met inside a list item or a quote (the walker reports the other places)."""
        self.d.error("LT034", "::include is only allowed at the top level of a file or of a detour",
                     self.loc(self.slide, tok))
        return ""

    def placed_badge(self, tok, pending: Attrs | None) -> str:
        """`::detour-badge{ref=ID label=... badge=...}`: a badge of a detour of this slide, anywhere (spec 3.9)."""
        slide = self.slide
        loc = self.loc(slide, tok)
        try:
            attrs = parse_attr_block(tok.info)
        except AttrError as e:
            self.d.error("LT009", str(e), loc)
            return ""
        problems = []
        extra = sorted(set(attrs.kv) - {"ref", "label", "badge"})
        if extra:
            problems.append(f"unknown attribute {extra[0]!r} (allowed: ref, label, badge, #id, classes)")
        if pending is not None and {"reveal", "reveal-with"} & set(pending.classes):
            problems.append("a detour badge cannot be a reveal fragment; use badge=step or badge=next")
        if pending is not None and pending.kv:
            problems.append("an attribute line before a detour badge may only give an #id and classes")
        if self.in_notes:
            problems.append("a detour badge cannot be placed in speaker notes")
        ref = attrs.get("ref")
        d = next((x for x in slide.detours if x.id == ref), None) if ref else None
        if not ref:
            problems.append("::detour-badge needs ref=ID, the id of a detour of this slide")
        elif d is None:
            problems.append(f"{ref!r} is not a detour of this slide")
        elif d.attrs.id is None:
            problems.append(f"give the detour an explicit id to place its badge (#{ref} is generated)")
        elif not d.badge:
            problems.append(f"detour {ref!r} has badge=false; remove it or the ::detour-badge")
        mode = d.badge_mode if d is not None else None
        if "badge" in attrs.kv:
            value = attrs.kv["badge"].strip().lower()
            if value in ("step", "next"):
                mode = value
            elif value in ("true", "yes", "1", "on"):
                mode = None
            else:
                problems.append(f"badge={attrs.kv['badge']!r} on a placed badge must be true, step or next")
        if problems:
            for p in problems:
                self.d.error("LT056", p, loc)
            return ""
        out: dict[str, str] = {}
        if attrs.id:
            out["id"] = attrs.id
        if attrs.classes:
            out["class"] = " ".join(attrs.classes)
        if pending is not None:
            if pending.id:
                out.setdefault("id", pending.id)
            classes = [c for c in pending.classes if c not in ("reveal", "reveal-with")]
            if classes:
                out["class"] = " ".join(filter(None, [*classes, out.get("class")]))
        d.badges.append((mode, loc))
        return self.detour_badge(d, mode, attrs.get("label") or d.label, out)
