"""Markdown parser configuration: CommonMark + Lattice extensions (spec section 3)."""
from __future__ import annotations

import html
import re

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

WIKI_RE = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9_-]*)\s*(?:\|(.*))?\Z", re.S)
# Leaf directives (spec 3.2): `::include{...}` and `::detour-badge{...}`, each alone on its line.
DIRECTIVE_RE = re.compile(r"::(include|detour-badge)\s*(\{.*\})\s*\Z")
DIRECTIVE_TOKENS = {"include": "lt_include", "detour-badge": "lt_badge"}
# Container fences (spec 3.2): three or more colons, then a name (an opening fence), nothing (a closing
# fence) or `/NAME` (a closing fence that names the container it closes).
FENCE_RE = re.compile(r":{3,}")
CLOSER_NAME_RE = re.compile(r"[^\s{}/]+\Z")
# The start of a code fence, after any block quote markers and list markers in front of it.
CODE_PREFIX_RE = re.compile(r"(?:[ \t]*(?:>|[-+*]|\d{1,9}[.)])(?=[ \t]|\Z))*[ \t]*")
CODE_FENCE_RE = re.compile(r"(`{3,}|~{3,})(.*)\Z")


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


def _directive_rule(state, start_line: int, end_line: int, silent: bool) -> bool:
    if state.sCount[start_line] - state.blkIndent >= 4:
        return False
    pos = state.bMarks[start_line] + state.tShift[start_line]
    line = state.src[pos : state.eMarks[start_line]]
    m = DIRECTIVE_RE.match(line.rstrip())
    if not m:
        return False
    if silent:
        return True
    tok = state.push(DIRECTIVE_TOKENS[m.group(1)], "", 0)
    tok.info = m.group(2)
    tok.map = [start_line, start_line + 1]
    state.line = start_line + 1
    return True


def _fence_line(state, line: int):
    """Classify a line as a container fence: ("open", name, info, markup), ("close", name, markup) or None.

    ``name`` of a closing fence is None for a bare fence and the written name for `::: /NAME`.
    """
    if state.sCount[line] - state.blkIndent >= 4:
        return None
    start = state.bMarks[line] + state.tShift[line]
    text = state.src[start : state.eMarks[line]]
    m = FENCE_RE.match(text)
    if not m:
        return None
    markup, rest = m.group(0), text[m.end() :].strip()
    if not rest:
        return ("close", None, markup)
    if rest.startswith("/"):
        return ("close", rest[1:].strip(), markup)
    return ("open", _opener_name(rest), text[m.end() :], markup)


def _opener_name(info: str) -> str:
    from .attrs import split_name_and_attrs

    return split_name_and_attrs(info)[0]


def _code_fence(state, line: int):
    """A code fence that starts on this line, behind quote or list markers: (marker, quoted) or None."""
    if state.sCount[line] - state.blkIndent >= 4:
        return None
    text = state.src[state.bMarks[line] + state.tShift[line] : state.eMarks[line]]
    prefix = CODE_PREFIX_RE.match(text).group(0)
    m = CODE_FENCE_RE.match(text[len(prefix) :])
    if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
        return None
    return m.group(1), ">" in prefix


def _ends_code_fence(state, line: int, fence) -> bool:
    """Whether this line closes the code fence, or ends it by leaving the block quote it started in."""
    marker, quoted = fence
    text = state.src[state.bMarks[line] + state.tShift[line] : state.eMarks[line]]
    prefix = CODE_PREFIX_RE.match(text).group(0)
    if quoted and ">" not in prefix:
        return True
    text = text[len(prefix) :].rstrip()
    return len(text) >= len(marker) and text == marker[0] * len(text)


def _problem(state, code: str, line: int, message: str) -> None:
    """Record a fence problem; the loader reports it with the file's location (parser.Loader.parse_file)."""
    problems = state.env.setdefault("fence_problems", {})
    problems.setdefault((code, line), message)


def _container_rule(state, start_line: int, end_line: int, silent: bool) -> bool:
    """Containers (spec 3.2). A closing fence closes the innermost open container, whatever its colons.

    The end of a container is found by counting the opening and closing fences that follow it, skipping
    the lines of code fences, so that a quoted `:::` in a code block closes nothing.
    """
    fence = _fence_line(state, start_line)
    if fence is None:
        return False
    if silent:
        return True
    if fence[0] == "close":
        what = f"'::: /{fence[1]}'" if fence[1] else "closing fence"
        _problem(state, "LT061", start_line, f"{what} without an open container")
        state.line = start_line + 1
        return True
    _, name, info, markup = fence
    depth, code, closed = 0, None, None
    line = start_line
    while True:
        line += 1
        if line >= end_line:
            break
        start, end = state.bMarks[line] + state.tShift[line], state.eMarks[line]
        if start < end and state.sCount[line] < state.blkIndent:
            break  # a line outdented out of an enclosing list item ends the container, as it ends a fence
        if code is not None:
            if not _ends_code_fence(state, line, code):
                continue
            quote_left = code[1] and ">" not in CODE_PREFIX_RE.match(state.src[start:end]).group(0)
            code = None
            if not quote_left:
                continue  # the closing fence of the code block; a line that leaves the quote is read below
        code = _code_fence(state, line)
        if code is not None:
            continue
        f = _fence_line(state, line)
        if f is None:
            continue
        if f[0] == "open":
            depth += 1
        elif depth:
            depth -= 1
        else:
            closed = f
            break
    if closed is None:
        _problem(state, "LT062", start_line, f"container {name or markup!r} is never closed")
    elif closed[1] is not None and not CLOSER_NAME_RE.match(closed[1]):
        _problem(state, "LT061", line, f"malformed closing fence '::: /{closed[1]}': expected '::: /NAME'")
    elif closed[1] is not None and closed[1] != name:
        _problem(state, "LT061", line,
                 f"'::: /{closed[1]}' closes the container {name or '(unnamed)'!r} opened at line {start_line + 1}")

    old_parent, old_line_max = state.parentType, state.lineMax
    state.parentType = "container"
    state.lineMax = line  # lazy continuation lines never run past the closing fence
    token = state.push("container_lt_open", "div", 1)
    token.markup = markup
    token.block = True
    token.info = info
    token.map = [start_line, line]
    state.md.block.tokenize(state, start_line + 1, line)
    token = state.push("container_lt_close", "div", -1)
    token.markup = closed[2] if closed else ""
    token.block = True
    if closed:
        token.map = [line, line + 1]
    state.parentType, state.lineMax = old_parent, old_line_max
    state.line = line + (1 if closed else 0)
    return True


def _render_container(self, tokens, idx, options, env):
    if tokens[idx].nesting == 1:
        tokens[idx].attrJoin("class", "lt")
    return self.renderToken(tokens, idx, options, env)


def _render_badge(self, tokens, idx, options, env):
    """A placed detour badge met inside a block rendered as a whole (a list item, a quote)."""
    render = env.get("badge")
    return render(tokens[idx], None) if render else ""


def _render_include(self, tokens, idx, options, env):
    """An `::include` inside a block rendered as a whole: reported by the body builder, rendered as nothing."""
    report = env.get("include")
    return report(tokens[idx], None) if report else ""


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
    md.block.ruler.before(
        "fence", "container_lt", _container_rule, {"alt": ["paragraph", "reference", "blockquote", "list"]}
    )
    md.add_render_rule("container_lt_open", _render_container)
    md.add_render_rule("container_lt_close", _render_container)
    dollarmath_plugin(md, allow_digits=False, allow_space=False)
    md.inline.ruler.before("link", "lt_wikilink", _wikilink_rule)
    md.block.ruler.before(
        "paragraph", "lt_directive", _directive_rule, {"alt": ["paragraph", "reference", "blockquote", "list"]}
    )
    md.add_render_rule("lt_wikilink", _render_wikilink)
    md.add_render_rule("lt_badge", _render_badge)
    md.add_render_rule("lt_include", _render_include)
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
