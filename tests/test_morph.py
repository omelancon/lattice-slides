"""`code-morph` at build time (spec 8.11): units, alignment, both authoring forms, diagnostics, cache."""
import json
import re

import pytest

from lattice.build import build_deck, check_deck
from lattice.components.morph import align, build_morph, expand_tabs, replace_segments, step_versions, tokenize
from lattice.components.segments import parse_markers, plain

BUGGY = "total = 0\nfor i in range(len(xs) - 1):\n    total += xs[i]\nprint(total)"
FIXED = "total = 0\nfor x in xs:\n    total += x\nprint(total)"
GUARD = "total = 0\nfor x in xs:\n    if x > 0:\n        total += x\nprint(total)"
ONE = "total = sum(x for x in xs if x > 0)\nprint(total)"

SCM = """\
(define (sum-to n)
  (let loop (#|@init|# (i 0) #|@end|#
             (acc 0))
    (if #|@bound|# (> i n) #|@end|#
        acc
        (loop (+ i 1) (+ acc i)))))
"""


def morph_of(texts, langs=None):
    langs = langs or ["python"] * len(texts)
    return build_morph([tokenize(t.split("\n") if t else [], lang) for t, lang in zip(texts, langs)], langs)


def rebuild(m, v):
    """The text of version `v` drawn from the morph data alone, as the runtime places it."""
    grid = [[" "] * m.cols for _ in range(m.rows[v])]
    for text, p in zip(m.texts, m.pos):
        if p[v] is not None:
            r, c, _ = p[v]
            for i, ch in enumerate(text):
                assert grid[r][c + i] == " ", f"two units on one cell at version {v}"
                grid[r][c + i] = ch
    return "\n".join("".join(row).rstrip() for row in grid)


def fate(m, v, text):
    """Where the units with this text go from version v to v + 1: 'stay', 'move', 'out' or 'in'."""
    out = []
    for t, p in zip(m.texts, m.pos):
        if t != text:
            continue
        a, b = p[v], p[v + 1]
        out.append("in" if a is None and b else "out" if b is None and a else "stay" if a[:2] == b[:2] else "move"
                   if a and b else "absent")
    return sorted(out)


def data_of(html, instance):
    return json.loads(re.search(rf'id="lt-data-{re.escape(instance)}">(.*?)</script>', html, re.S).group(1))


# ------------------------------------------------------------------ units and alignment


@pytest.mark.parametrize("texts", [
    [BUGGY, FIXED, GUARD, ONE],
    ['def f():\n    """Doc\n    string"""\n    return 1', 'def f():\n    return 1'],   # a token spanning lines
    ["", "x = 1"],                                                                     # an empty version
    ["a = 1\nb = 2\nc = 3", "c = 3\na = 1\nb = 2"],                                     # a moved line
    ['s = "hello world"', 's = "hello there world"'],                                  # words inside a string
])
def test_every_version_is_rebuilt_from_the_data(texts):
    m = morph_of(texts)
    for v, t in enumerate(texts):
        assert rebuild(m, v) == "\n".join(line.rstrip() for line in t.split("\n")) if t else rebuild(m, v) == ""
        assert m.rows[v] == (len(t.split("\n")) if t else 0)
    assert all(any(p) for p in m.pos)  # every unit is shown at some position


def test_the_off_by_one_keeps_what_did_not_change():
    m = morph_of([BUGGY, FIXED])
    assert fate(m, 0, "for") == ["stay"] and fate(m, 0, "in") == ["stay"] and fate(m, 0, "total") == ["stay"] * 3
    assert fate(m, 0, ":") == ["move"] and fate(m, 0, "xs") == ["move", "out"]
    assert fate(m, 0, "range") == ["out"] and fate(m, 0, "len") == ["out"] and fate(m, 0, "x") == ["in", "in"]
    assert m.changed[1] == 1


def test_a_line_becomes_several_and_several_become_one():
    m = morph_of([FIXED, GUARD, ONE])
    assert fate(m, 0, "if") == ["in"] and "move" in fate(m, 0, "total")  # re-indented, one row lower
    assert fate(m, 0, "print") == ["move"]
    # three lines collapse into one: `for x in xs` and `if x > 0` travel to the first row
    rows = {m.texts[i]: (p[1][0], p[2][0]) for i, p in enumerate(m.pos) if p[1] and p[2] and m.texts[i] in ("for", "if")}
    assert rows == {"for": (1, 0), "if": (2, 0)}


def test_moves_need_a_unique_line():
    a = [tokenize(["a = 1", "b = 2", "long_line = 3"], "python")]
    b = [tokenize(["long_line = 3", "a = 1", "b = 2"], "python")]
    pairs = align(a[0], b[0])
    assert ((2, 0), (0, 0)) in pairs  # the moved line keeps its units
    m = morph_of(["}\nx = 1\n}", "x = 1\n}\n}"], ["c", "c"])  # short lines are not moves
    assert rebuild(m, 1) == "x = 1\n}\n}"


def test_tabs_are_expanded_to_eight_columns():
    marked = expand_tabs(parse_markers("if x:\n\ty = 1  /*@v*/2/*@end*/"))
    assert marked.lines == ["if x:", "        y = 1  2"]
    assert (marked.segments[0].c0, marked.segments[0].c1) == (15, 16)


def test_a_language_change_matches_on_text_and_keeps_classes_per_version():
    py = "def total(xs):\n    return sum(xs)"
    scm = "(define (total xs)\n  (apply + xs))"
    m = morph_of([py, scm], ["python", "scheme"])
    i = m.texts.index("xs")
    a, b = m.pos[i]
    assert a and b and m.classes[a[2]] != m.classes[b[2]]  # survives, changes colour
    assert rebuild(m, 1) == scm
    # the same text in one language matches on class and text: `in` the keyword is not `in` the name
    m = morph_of(["x in y", "x = in_"])
    assert fate(m, 0, "in") == ["out"]


def test_scheme_correction_applies_per_version():
    m = morph_of(["(let ((i 0)) i)", "(let ((j 0)) j)"], ["scheme", "scheme"])
    j = m.texts.index("j")
    assert m.classes[m.pos[j][1][2]] == "nv"


# ------------------------------------------------------------------ the steps form


def test_steps_are_cumulative_and_null_restores():
    base = parse_markers(SCM.rstrip("\n"))
    vs = step_versions(base, [{"bound": "(>= i n)", "label": "fixed"}, {"init": "(i 1)"}, {"bound": None}], "as written")
    assert [lab for _, lab, _ in vs] == ["as written", "fixed", "step 2", "step 3"]
    assert [g for _, _, g in vs] == [True, True, False, False]
    texts = [t.text for t, _, _ in vs]
    assert "(> i n)" in texts[0] and "(>= i n)" in texts[1] and "(i 1)" in texts[2] and "(>= i n)" in texts[2]
    assert "(> i n)" in texts[3] and "(i 1)" in texts[3]
    t, _, _ = vs[1]
    bound = next(g for g in t.segments if g.name == "bound")
    assert t.lines[bound.l0][bound.c0:bound.c1] == "(>= i n)"  # the segment covers its new text


def test_replacement_indentation_and_removed_lines():
    base = parse_markers("def f(xs):\n    # @body\n    return sum(xs)\n    # @end\n    # @tail\n    pass\n    # @end")
    t = replace_segments(base, {"body": "total = 0\nfor x in xs:\n    total += x\nreturn total\n"})
    assert t.lines[1:5] == ["    total = 0", "    for x in xs:", "        total += x", "    return total"]
    body = next(g for g in t.segments if g.name == "body")
    assert (body.l0, body.l1) == (1, 4)
    t = replace_segments(base, {"tail": ""})
    assert t.lines == ["def f(xs):", "    return sum(xs)"]  # whole lines replaced by nothing are removed
    t = replace_segments(base, {"body": ""})
    assert t.lines == ["def f(xs):", "    pass"]


def test_nested_segments_disappear_while_their_parent_is_replaced():
    base = parse_markers("(a /*@outer*/(b /*@inner*/c/*@end*/)/*@end*/)")
    t = replace_segments(base, {"outer": "d"})
    assert t.text == "(a d)" and [g.name for g in t.segments] == ["outer"]
    t = replace_segments(base, {"inner": "e"})
    assert t.text == "(a (b e))" and {g.name for g in t.segments} == {"outer", "inner"}


@pytest.mark.parametrize("steps, message", [
    ([{"nope": "x"}], "no segment named 'nope'"),
    ([{"lang": "python"}], "the language can change only between versions"),
    ([{"outer": "d", "inner": "e"}], "is inside 'outer', set in the same step"),
    ([{"outer": "d"}, {"inner": "e"}], "is inside 'outer', which is replaced"),
    ([{"outer": "d"}, {"inner": None}], "is inside 'outer', which is replaced"),
])
def test_step_errors(deck, steps, message):
    body = "steps:\n" + "".join("  - " + json.dumps(s) + "\n" for s in steps)
    root = deck({"talk.md": "# A\n```code-morph {lang=c file=x.c}\n" + body + "```\n",
                 "x.c": "(a /*@outer*/(b /*@inner*/c/*@end*/)/*@end*/)\n"})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and message in items[0].message


@pytest.mark.parametrize("attrs, body", [
    ("", ""),                                                          # neither form
    ("file=x.c", "versions: [a.c, b.c]\nsteps: [{}]"),                 # both
    ("", "steps: [{}]"),                                               # steps without file
    ("label=x", "versions: [{code: a}, {code: b}]"),                   # label of the steps form
    ("room=wide", "versions: [{code: a}, {code: b}]"),
    ("file=x.c", ""),                                                  # file without steps
])
def test_option_errors(deck, attrs, body):
    root = deck({"talk.md": f"# A\n```code-morph {{{attrs}}}\n{body}\n```\n", "x.c": "x\n"})
    assert [x.code for x in check_deck(root, use_cache=False).items] == ["LT021"]


def test_one_version_or_no_step_is_an_error(deck):
    root = deck({"talk.md": "# A\n```code-morph\nversions: [{code: a}]\n```\n"})
    assert [x.code for x in check_deck(root, use_cache=False).items] == ["LT022"]


# ------------------------------------------------------------------ the component in a deck


def test_component_html_data_and_track(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#fix lang=python title="fix" linenos=true}
        versions:
          - code: |
              for i in range(len(xs) - 1):
                  total += xs[i]
            label: buggy
          - {file: fixed.py, label: fixed}
        ```
    """, "fixed.py": "for x in xs:\n    total += x\n"})
    d = build_deck(root, use_cache=False)
    s = d.slides["a"]
    assert s.steps == 2 and not d.diagnostics.items
    assert 'class="lt-code lt-morph"' in s.body_html and "lt-morph-ln-on" in s.body_html
    assert '<span class="lt-morph-label">buggy</span>' in s.body_html and ">fix<" in s.body_html
    from lattice.emit import emit_html

    data = data_of(emit_html(d), "a/fix")
    assert data["labels"] == ["buggy", "fixed"] and data["rows"] == [2, 2] and data["duration"] == 600
    assert data["room"] == "max" and data["mark"] is False and len(data["layers"]) == 2
    assert d.instances["a/fix"]["positions"] == 2


def test_default_labels_name_the_languages(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#tr lang=python}
        versions:
          - {code: "def f(x): return x"}
          - {code: "(define (f x) x)", lang: scheme}
        ```
    """})
    d = build_deck(root, use_cache=False)
    assert "lt-morph-label-solo\">Python<" in d.slides["a"].body_html
    assert 'data-lang="python"' in d.slides["a"].body_html


def test_steps_form_segments_are_anchors_and_arrow_targets(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#loop lang=scheme file="sum.scm" label="as written"}
        steps:
          - bound: "(>= i n)"
            label: fixed
          - init: "(i 1)"
        ```

        ```arrow
        to: bound
        ```
    """, "sum.scm": SCM})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    s = d.slides["a"]
    assert s.steps == 3 and '<span class="lt-seg" data-lt-seg="bound" id="bound">(&gt; i n)</span>' in s.body_html


def test_segments_of_later_versions_are_known_to_arrows_and_ids(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#m lang=c}
        versions:
          - {code: "x = 1;"}
          - {code: "x = /*@two*/2/*@end*/;"}
        ```

        ```arrow
        to: two
        ```

        {#two}
        Text with the same id.
    """})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT058"]  # not LT046: the segment exists at position 1


def test_identical_versions_and_odd_characters_warn(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#m}
        versions:
          - {code: "a = 1"}
          - {code: "a = 1"}
          - {code: "a = '\u4e2d'"}
        ```
    """})
    items = check_deck(root, use_cache=False).items
    assert sorted(x.code for x in items) == ["LT059", "LT060"]
    assert all(x.severity == "warning" for x in items)


def test_cache_follows_version_files_and_keeps_warnings_and_anchors(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {#m lang=c}
        versions: [a.c, b.c, b.c]
        ```

        {#s}
        Paragraph.
    """, "a.c": "x = 1;\n", "b.c": "x = /*@s*/2/*@end*/;\n"})
    first = check_deck(root, use_cache=True).items
    assert sorted(x.code for x in first) == ["LT058", "LT059"]
    again = check_deck(root, use_cache=True).items  # from the cache: same diagnostics
    assert sorted(x.code for x in again) == ["LT058", "LT059"]
    (root.parent / "b.c").write_text("x = 3;\n")
    d = build_deck(root, use_cache=True)
    assert "3" in d.slides["a"].body_html and sorted(x.code for x in d.diagnostics.items) == ["LT059"]


def test_room_fit_starts_at_the_first_version(deck):
    root = deck({"talk.md": """
        # A
        ```code-morph {room=fit}
        versions: [{code: "a"}, {code: "a\\nb\\nc"}]
        ```
    """})
    html = build_deck(root, use_cache=False).slides["a"].body_html
    assert "--h:1;" in html
    root = deck({"talk.md": "# A\n```code-morph\nversions: [{code: \"a\"}, {code: \"a\\nb\\nc\"}]\n```\n"})
    assert "--h:3;" in build_deck(root, use_cache=False).slides["a"].body_html


def test_diff_steps_still_reads_versions_alike(deck):
    root = deck({"talk.md": """
        # A
        ```diff-steps {#d lang=python}
        versions:
          - x.py
          - {code: "x = 2", label: two, lang: scheme}
        ```
    """, "x.py": "x = 1\n"})
    s = build_deck(root, use_cache=False).slides["a"]
    assert ">x.py<" in s.body_html and "two" in s.body_html and 'data-lang="python"' in s.body_html


def test_plain_text_without_markers(deck):
    m = morph_of(["a /*@x*/b/*@end*/", "a b"], ["c", "c"])
    assert rebuild(m, 0) == "a /*@x*/b/*@end*/"
    assert plain("a").lines == ["a"]
