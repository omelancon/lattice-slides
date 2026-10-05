"""Named segments in code (spec 8.10) and arrow anchors (spec 8.9), at build time."""
import re
import textwrap

import pytest
from pygments import highlight
from pygments.formatters import HtmlFormatter

from lattice.build import build_deck, check_deck
from lattice.components.scheme import lexer_for
from lattice.components.segments import MarkerError, parse_markers, pieces, wrap_line

SCM = """\
(define (sum-to n)
  (let loop (#|@i-init|# (i 0) #|@end|#
             (acc 0))
    #|@body|#
    (if (> i n)
        acc
        (loop (+ i 1) (+ acc #|@last|#i#|@end|#)))
    #|@end|#))
"""

PY = """\
def f(xs):
    total = 0
    # @loop
    for x in xs:
        total += x
    # @end
    return total
"""


def seg(body_html, name):
    """The pieces of a segment, as (has id, text)."""
    out = []
    for m in re.finditer(rf'<span class="lt-seg[^"]*" data-lt-seg="{name}"( id="{name}")?>(.*?)</span></span>',
                         body_html):
        out.append((bool(m.group(1)), re.sub(r"<[^>]+>", "", m.group(2))))
    return out


def codes(d):
    return [x.code for x in d.diagnostics.items]


def test_markers_are_removed_with_their_spaces():
    m = parse_markers(SCM)
    assert m.lines[1] == "  (let loop ((i 0)"
    assert m.lines[6] == "    ))"  # the indentation before a closing marker stays
    assert m.lines[5].endswith("(+ acc i)))")
    assert m.orig == [1, 2, 3, 5, 6, 7, 8, 9]  # line 4 held only a marker
    assert [(g.name, g.l0, g.c0, g.l1, g.c1) for g in m.segments] == [
        ("i-init", 1, 13, 1, 18), ("body", 3, 0, 6, 4), ("last", 5, 29, 5, 30)]
    assert m.lines[1][13:18] == "(i 0)"
    assert parse_markers("f(/* @a */x/*@end*/, y)").lines == ["f(x, y)"]
    assert parse_markers("  ( #|@a|# (i 0) #|@end|#)").lines == ["  ( (i 0))"]


def test_whole_line_markers():
    m = parse_markers(PY)
    assert m.lines == ["def f(xs):", "    total = 0", "    for x in xs:", "        total += x", "    return total", ""]
    assert m.orig == [1, 2, 4, 5, 7, 8]
    p = pieces(m)
    assert [(a, b, first) for a, b, _, first in p[2] + p[3]] == [(4, 16, True), (8, 18, False)]  # no indentation


@pytest.mark.parametrize("text, message, line", [
    ("a #|@x|# b", "never closed", 1),
    ("a\n#|@end|#", "without an open segment", 2),
    ("#|@x|# a #|@end y|#", "closes segment @x", 1),
    ("#|@x|#a#|@end|#\n#|@x|#b#|@end|#", "already defined at line 1", 2),
    ("a #|@x|##|@end|# b", "is empty", 1),
])
def test_malformed_markers(text, message, line):
    with pytest.raises(MarkerError) as e:
        parse_markers(text)
    assert message in str(e.value) and e.value.line == line


def test_wrapping_keeps_the_tokens():
    """Wrapping splits a token cut by a boundary into two spans of the same class, keeps Pygments'
    escaping, and leaves lines without segments untouched."""
    m = parse_markers('x = "a<#|@s|#b&c" + #|@t|#yy#|@end|##|@end|# + 1')
    raw = highlight(m.text, lexer_for("python"), HtmlFormatter(nowrap=True)).rstrip("\n")
    out = wrap_line(raw, pieces(m)[0], {"t"})
    assert re.sub(r"<[^>]+>", "", out) == re.sub(r"<[^>]+>", "", raw)
    assert re.search(r'<span class="s2">(&quot;|")a&lt;</span><span class="lt-seg" data-lt-seg="s" id="s">'
                     r'<span class="s2">b&amp;c(&quot;|")</span>', out)
    assert '<span class="lt-seg lt-hl" data-lt-seg="t" id="t"><span class="n">yy</span></span></span>' in out


def test_code_block_from_a_file(deck):
    root = deck({"talk.md": """
        # A
        ```code {#src lang=scheme file="sum.scm" linenos=true line_base=file}
        ```
    """, "sum.scm": SCM})
    d = build_deck(root, use_cache=False)
    assert codes(d) == []
    body = d.slides["a"].body_html
    assert "#|" not in body and "@end" not in body
    assert seg(body, "i-init") == [(True, "(i 0)")]
    assert seg(body, "last") == [(True, "i")]
    assert [n for n in re.findall(r'data-line="(\d+)"', body)] == ["1", "2", "3", "5", "6", "7", "8"]
    assert re.findall(r'<span class="lt-ln">(\d+)</span>', body)[3] == "5"  # the gutter counts the file's lines


def test_multi_line_segment_pieces(deck):
    root = deck({"talk.md": "# A\n```code {lang=scheme file=\"sum.scm\"}\n```\n", "sum.scm": SCM})
    body = build_deck(root, use_cache=False).slides["a"].body_html
    parts = re.findall(r'data-lt-seg="body"( id="body")?', body)
    assert parts == [' id="body"', "", ""]  # one piece per line, the first carries the id


def test_lines_and_symbol_count_the_file_as_written(deck):
    root = deck({"talk.md": """
        # A
        ```code {#a lang=python file="f.py" lines=4-5 line_base=file}
        ```

        # B
        ```code {#b lang=python file="f.py" symbol=f highlight=loop}
        ```
    """, "f.py": PY})
    d = build_deck(root, use_cache=False)
    assert codes(d) == []
    a = d.slides["a"].body_html
    assert re.findall(r'data-line="(\d+)"', a) == ["4", "5"] and seg(a, "loop")[0][0]
    b = d.slides["b"].body_html
    assert "# @loop" not in b and 'class="lt-code lt-has-hl"' in b
    assert b.count("lt-hl-in") == 2 and 'class="lt-seg lt-hl"' in b


def test_inline_body_and_markers_false(deck):
    root = deck({"talk.md": """
        # A
        ```scheme
        (f #|@arg|# x #|@end|#)
        ```

        # B
        ```scheme {markers=false}
        (f #|@arg|# x #|@end|#)
        ```
    """})
    d = build_deck(root, use_cache=False)
    assert seg(d.slides["a"].body_html, "arg") == [(True, "x")]
    assert "@arg" in d.slides["b"].body_html and "lt-seg" not in d.slides["b"].body_html


def test_segment_highlights_in_steps(deck):
    root = deck({"talk.md": """
        # A
        ```code-steps {#cs lang=scheme file="sum.scm"}
        steps: [i-init, "2-3", [1, body]]
        ```
    """, "sum.scm": SCM})
    d = build_deck(root, use_cache=False)
    assert codes(d) == []
    data = d.instances["a/cs"]["data"]
    assert data["steps"] == [[], [], [2, 3], [1]]
    assert data["segs"] == [[], ["i-init"], [], ["body"]]


def test_line_steps_keep_their_data(deck):
    """Without segment highlights the runtime data is unchanged (no `segs`)."""
    root = deck({"talk.md": "# A\n```code-steps {#cs lang=scheme file=\"sum.scm\"}\nsteps: [\"2-3\"]\n```\n",
                 "sum.scm": SCM})
    assert build_deck(root, use_cache=False).instances["a/cs"]["data"] == {"steps": [[], [2, 3]]}


def test_unknown_segment_and_bad_marker_are_lt022(deck):
    root = deck({"talk.md": "# A\n```code {lang=scheme file=\"sum.scm\" highlight=nope}\n```\n", "sum.scm": SCM})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and "no segment named 'nope'" in items[0].message
    root = deck({"talk.md": "# A\n```code {lang=scheme file=\"bad.scm\"}\n```\n", "bad.scm": "(a)\n(b #|@x|# c)\n"})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and "bad.scm:2: segment @x is never closed" in items[0].message


def test_diff_steps_strip_markers(deck):
    root = deck({"talk.md": """
        # A
        ```diff-steps {#d lang=scheme}
        versions: [v1.scm, v2.scm]
        ```
    """, "v1.scm": "(f #|@a|# x #|@end|#)\n", "v2.scm": "(f #|@a|# y #|@end|#)\n"})
    body = build_deck(root, use_cache=False).slides["a"].body_html
    assert "@a" not in body and "lt-seg" not in body and 'id="a"' not in body


@pytest.mark.parametrize("other", [
    "{#i-init}\nA paragraph.",
    "```scheme {#i-init}\n(x)\n```",
    "{#i-init}\n```scheme\n(x)\n```",
    "<span id=\"i-init\">raw</span>",
    "```code {lang=scheme file=\"sum.scm\"}\n```",
])
def test_duplicate_ids_on_a_slide_are_lt058(deck, other):
    root = deck({"talk.md": f"# A\n```code {{lang=scheme file=\"sum.scm\"}}\n```\n\n{other}\n\n# B\n{other}\n",
                 "sum.scm": SCM})
    items = check_deck(root, use_cache=False).items
    assert {x.code for x in items} == {"LT058"} and any("'i-init'" in x.message for x in items)
    assert len(items) == (3 if other.startswith("```code") else 1)  # three segments twice, or one id


def test_duplicate_author_ids_without_segments(deck):
    root = deck({"talk.md": "# A\n{#x}\nOne.\n\n{#x}\nTwo.\n"})
    assert [x.code for x in check_deck(root, use_cache=False).items] == ["LT058"]


def test_arrow_targets_a_segment(deck):
    root = deck({"talk.md": """
        # A
        ```code {lang=scheme file="sum.scm" lines=1-3}
        ```

        ```arrow {to=i-init}
        ```

        ```arrow {to=body}
        ```
    """, "sum.scm": SCM})
    d = build_deck(root, use_cache=False)
    # `lines=1-3` cuts `body` away: the arrow at it warns, the one at `i-init` does not
    assert codes(d) == ["LT046"] and "'body'" in d.diagnostics.items[0].message


def test_arrow_anchors(deck):
    root = deck({"talk.md": """
        # A
        {#p}
        Text.

        {#q}
        More.

        ```arrow {#w from=p from_anchor=left to_anchor=bottom}
        steps:
          - q
          - to: q
            to_anchor: 45
            from_anchor: center
          - to: q
            from: ""
            to_anchor: left
          - to: q
            from: ""
            to_anchor: -90
            angle: 300
        ```
    """})
    d = build_deck(root, use_cache=False)
    assert codes(d) == []
    steps = d.instances["a/w"]["data"]["steps"]
    assert steps[0]["from_anchor"] == 180.0 and steps[0]["to_anchor"] == 270.0
    assert steps[1]["from_anchor"] == "center" and steps[1]["to_anchor"] == 45.0
    # without `from`: the block's from_anchor does not apply, and a side gives the direction
    assert "from_anchor" not in steps[2] and steps[2]["to_anchor"] == 180.0 and steps[2]["angle"] == 180.0
    assert steps[3]["to_anchor"] == 270.0 and steps[3]["angle"] == 300.0


@pytest.mark.parametrize("arrow, message", [
    ("```arrow {to=p from_anchor=left}\n```", "`from_anchor` needs `from`"),
    ("```arrow\nsteps:\n  - to: p\n    from_anchor: top\n```", "step 1 has `from_anchor` but no `from`"),
])
def test_from_anchor_needs_from(deck, arrow, message):
    root = deck({"talk.md": f"# A\n{{#p}}\nText.\n\n{arrow}\n"})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and message in items[0].message


def test_bad_anchor_is_lt021(deck):
    root = deck({"talk.md": "# A\n{#p}\nText.\n\n```arrow {to=p to_anchor=middle}\n```\n"})
    assert [x.code for x in check_deck(root, use_cache=False).items] == ["LT021"]


# ---------------------------------------------------------------- arrows at list items (spec 8.9)
LISTS = """\
# A
{#p}
Text.

{#facts}
- one
- two
  1. two.one
  2. two.two
- three

"""


def test_arrow_at_list_items(deck):
    root = deck({"talk.md": LISTS + textwrap.dedent("""\
        ```arrow {#w from_anchor=bullet to_anchor=right}
        steps:
          - from: facts[1]
            to: p
          - from: facts[-1]
            to: facts[2][2]
          - facts[2][-2]
          - to: facts[3]
            to_anchor: bullet
        ```

        ```arrow {to=facts[2] from=p}
        ```
    """)})
    d = build_deck(root, use_cache=False)
    assert codes(d) == []
    steps = d.instances["a/w"]["data"]["steps"]
    # an item path is a list id and a path; the anchor `bullet` is kept for the runtime
    assert steps[0]["from"] == "facts" and steps[0]["from_item"] == [1] and steps[0]["from_anchor"] == "bullet"
    assert steps[0]["to"] == "p" and "to_item" not in steps[0] and steps[0]["to_anchor"] == 0.0
    assert steps[1]["from_item"] == [-1] and steps[1]["to"] == "facts" and steps[1]["to_item"] == [2, 2]
    assert steps[2]["to_item"] == [2, -2] and steps[2]["from"] is None
    # without `from`, a bullet end gives the direction of `left`
    assert steps[3]["to_anchor"] == "bullet" and steps[3]["angle"] == 180.0
    other = next(v for k, v in d.instances.items() if k != "a/w")  # an item in the attribute block
    one = other["data"]["steps"][0]
    assert (one["to"], one["to_item"], one["from"]) == ("facts", [2], "p")


@pytest.mark.parametrize("arrow, message", [
    ("to: facts[4]", "'facts[4]': the list 'facts' has 3 items"),
    ("to: facts[-4]", "'facts[-4]': the list 'facts' has 3 items"),
    ("to: facts[2][3]", "'facts[2][3]': the list nested in 'facts[2]' has 2 items"),
    ("to: facts[1][1]", "'facts[1][1]': item 'facts[1]' has no nested list"),
    ("to: p[1]", "'p[1]': 'p' is a <p>, not a list"),
    ("to: nope[1]", "'nope[1]': no list with the id 'nope' on this slide"),
    ("to: facts\n    to_anchor: bullet", "needs one item of the list 'facts': write facts[N]"),
    ("to: p\n    to_anchor: bullet", "needs a list item, and 'p' is a <p>"),
    ("to: '#facts > li'\n    to_anchor: bullet", "written LIST[N], not the selector '#facts > li'"),
    ("to: p\n    from: '#facts li'\n    from_anchor: bullet", "step 1, `from`: a `bullet` anchor needs a list item"),
])
def test_lt063(deck, arrow, message):
    root = deck({"talk.md": LISTS + f"```arrow\nsteps:\n  - {arrow}\n```\n"})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT063"] and message in items[0].message, items


def test_item_index_zero_is_lt022(deck):
    root = deck({"talk.md": LISTS + "```arrow {to=facts[0]}\n```\n"})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and "counted from 1" in items[0].message


def test_bullet_on_an_li_id_and_in_component_html(deck):
    """A bare id of an <li> (raw HTML) takes a bullet anchor; lists in the HTML of a component count."""
    root = deck({"talk.md": """
        # A
        <ul><li id="raw">raw item</li></ul>

        ```arrow {to=raw to_anchor=bullet}
        ```
    """})
    assert codes(build_deck(root, use_cache=False)) == []


def test_unknown_item_list_is_not_lt046(deck):
    root = deck({"talk.md": LISTS + "```arrow {to=nope[1]}\n```\n"})
    assert [x.code for x in check_deck(root, use_cache=False).items] == ["LT063"]
