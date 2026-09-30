"""Markdown parser configuration: CommonMark + Lattice extensions (spec section 3)."""
from __future__ import annotations

import html
import re

from markdown_it import MarkdownIt
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

WIKI_RE = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9_-]*)\s*(?:\|(.*))?\Z", re.S)
INCLUDE_RE = re.compile(r"::include\s*(\{.*\})\s*\Z")


def title_placeholder(target: str) -> str:
    """Placeholder replaced by the target's title once all titles are known."""
    return f"\x00T:{target}\x00"


def _wikilink_rule(state, silent: bool) -> bool:
    src, pos = state.src, state.pos
    if not src.startswith("[[", pos):
        return False
    end = src.find("]]", pos + 2)
    if end < 0:
        return False
    m = WIKI_RE.match(src[pos + 2 : end])
    if not m:
        return False
    if not silent:
        tok = state.push("lt_wikilink", "a", 0)
        tok.meta = {"target": m.group(1), "label": m.group(2)}
    state.pos = end + 2
    return True


def _render_wikilink(self, tokens, idx, options, env):
    meta = tokens[idx].meta
    target = meta["target"]
    env.setdefault("links", []).append(target)
    label = meta["label"]
    if label is not None and label.strip():
        label_html = self_md(env).renderInline(label.strip(), env)
    else:
        label_html = title_placeholder(target)
    t = html.escape(target, quote=True)
    return f'<a class="lt-link" href="#/{t}/0" data-lt-link="{t}">{label_html}</a>'


def self_md(env):
    return env["__md__"]


def _include_rule(state, start_line: int, end_line: int, silent: bool) -> bool:
    if state.sCount[start_line] - state.blkIndent >= 4:
        return False
    pos = state.bMarks[start_line] + state.tShift[start_line]
    line = state.src[pos : state.eMarks[start_line]]
    m = INCLUDE_RE.match(line.rstrip())
    if not m:
        return False
    if silent:
        return True
    tok = state.push("lt_include", "", 0)
    tok.info = m.group(1)
    tok.map = [start_line, start_line + 1]
    state.line = start_line + 1
    return True


def _render_math_inline(self, tokens, idx, options, env):
    env["math"] = True
    tex = html.escape(tokens[idx].content)
    return f'<span class="lt-math" data-display="0">{tex}</span>'


def _render_math_block(self, tokens, idx, options, env):
    env["math"] = True
    tex = html.escape(tokens[idx].content.strip())
    return f'<div class="lt-math lt-math-block" data-display="1">{tex}</div>\n'


def create_markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable("table").enable("strikethrough")
    front_matter_plugin(md)
    container_plugin(md, "lt", validate=lambda *args: True)
    dollarmath_plugin(md, allow_digits=False, allow_space=False)
    md.inline.ruler.before("link", "lt_wikilink", _wikilink_rule)
    md.block.ruler.before(
        "paragraph", "lt_include", _include_rule, {"alt": ["paragraph", "reference", "blockquote", "list"]}
    )
    md.add_render_rule("lt_wikilink", _render_wikilink)
    md.add_render_rule("math_inline", _render_math_inline)
    md.add_render_rule("math_inline_double", _render_math_block)
    md.add_render_rule("math_block", _render_math_block)
    md.add_render_rule("math_block_label", _render_math_block)
    return md


def new_env(md: MarkdownIt) -> dict:
    return {"__md__": md, "links": [], "math": False}


def token_groups(tokens) -> list[list]:
    """Split a flat token list into top-level groups (one block each)."""
    groups, cur, depth = [], [], 0
    for tok in tokens:
        cur.append(tok)
        depth += tok.nesting
        if depth == 0:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def container_name(tok) -> tuple[str, str | None]:
    from .attrs import split_name_and_attrs

    return split_name_and_attrs(tok.info or "")
