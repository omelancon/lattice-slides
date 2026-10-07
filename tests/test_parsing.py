import re
import pytest

from lattice.attrs import AttrError, parse_attr_block, split_trailing_attrs
from lattice.build import build_deck, check_deck
from lattice.ids import slugify


def codes(diags):
    return {d.code for d in diags.items}


def test_attr_block():
    a = parse_attr_block('{#intro .wide .dark next=demo label="Two words" key=\'h\'}')
    assert a.id == "intro"
    assert a.classes == ["wide", "dark"]
    assert a.kv == {"next": "demo", "label": "Two words", "key": "h"}


@pytest.mark.parametrize("bad", ["{#a #b}", "{x=1 x=2}", "{=oops}", "no braces"])
def test_attr_block_errors(bad):
    with pytest.raises(AttrError):
        parse_attr_block(bad)


def test_trailing_attrs():
    assert split_trailing_attrs("Title {#t}") == ("Title", "{#t}")
    assert split_trailing_attrs("Set \\{x}") == ("Set \\{x}", None)
    assert split_trailing_attrs("{#only}") == ("", "{#only}")


def test_slugify():
    assert slugify("Dijkstra's Algorithm") == "dijkstras-algorithm"
    assert slugify("Évaluation: O(n log n)") == "evaluation-o-n-log-n"
    assert slugify("!!!") == ""


def test_h1_boundaries_and_untitled(deck):
    root = deck({"talk.md": """
        # First
        ## Not a slide
        text
        #
        untitled
        # {#named}
        body
    """})
    d = build_deck(root, use_cache=False)
    assert list(d.slides) == ["first", "talk-2", "named"]
    assert d.slides["talk-2"].untitled and d.slides["named"].untitled
    assert "<h2>Not a slide</h2>" in d.slides["first"].body_html


def test_setext_and_leading_content(deck):
    root = deck({"talk.md": """
        stray paragraph

        Title
        =====
    """})
    assert {"LT001", "LT002"} <= codes(check_deck(root, use_cache=False))


def test_duplicate_ids(deck):
    root = deck({"talk.md": """
        # A {#x}
        # B {#x}
        # Same
        # Same
    """})
    diags = check_deck(root, use_cache=False)
    assert "LT007" in codes(diags)


def test_auto_id_collision_warns(deck):
    root = deck({"talk.md": """
        # Same
        # Same
    """})
    d = build_deck(root, use_cache=False)
    assert list(d.slides) == ["same", "same-2"]
    assert "LT008" in codes(d.diagnostics)


def test_includes(deck):
    root = deck({
        "talk.md": """
            ---
            title: T
            ---
            # Intro
            ::include{file="parts/a.md"}
            # End
            ::include{file="backup.md" offpath=true}
        """,
        "parts/a.md": """
            # Part A
            # Part B
        """,
        "backup.md": """
            # Backup
        """,
    })
    d = build_deck(root, use_cache=False)
    assert list(d.slides) == ["intro", "part-a", "part-b", "end", "backup"]
    assert d.main_path == ["intro", "part-a", "part-b", "end"]
    assert d.slides["backup"].offpath and d.slides["backup"].next == "back"


def test_include_errors(deck):
    root = deck({
        "talk.md": """
            # A
            ::include{file="b.md"}
            ::include{file="b.md"}
            ::include{file="missing.md"}
        """,
        "b.md": """
            ---
            x: 1
            ---
            # B
            ::include{file="talk.md"}
        """,
    })
    c = codes(check_deck(root, use_cache=False))
    assert {"LT003", "LT004", "LT005", "LT006"} <= c


def test_wiki_links_and_titles(deck):
    root = deck({"talk.md": """
        # Start
        See [[proof]] and [[proof|the proof]].
        # Proof {offpath=true}
        Done.
    """})
    d = build_deck(root, use_cache=False)
    html = d.slides["start"].body_html
    assert '>Proof</a>' in html and '>the proof</a>' in html
    assert d.slides["start"].links == ["proof"]


def test_unknown_link(deck):
    root = deck({"talk.md": "# A\n[[nowhere]]\n"})
    assert "LT011" in codes(check_deck(root, use_cache=False))


def test_reveal_fragments(deck):
    root = deck({"talk.md": """
        # A
        {.reveal}
        - one
        - two

        {.reveal}
        Last.
    """})
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.reveal_count == 3 and s.steps == 4
    assert s.body_html.count("data-lt-reveal") == 3


def test_reveal_with_joins_the_previous_fragment(deck):
    """Spec 3.12: `.reveal-with` puts a block on the last fragment numbered so far, without opening one."""
    root = deck({"talk.md": """
        # A
        {.reveal}
        - one
        - two

        {.reveal-with .wide}
        ```python
        x = 1
        ```

        {.reveal-with}
        - a whole list
        - joins too

        :::: columns
        ::: column
        {.reveal}
        Next.
        :::
        ::: column
        {.reveal-with}
        Beside it, in the other column.
        :::
        ::::
    """})
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.reveal_count == 3 and s.steps == 4
    html = s.body_html
    assert 'class="lt-c lt-c-code wide" data-component="code" data-instance="a/c1" data-lt-reveal="2"' in html
    assert '<ul data-lt-reveal="2">' in html  # the list as a whole, not one fragment per item
    assert "<p data-lt-reveal=\"3\">Beside it" in html
    assert html.count('data-lt-reveal="3"') == 2


def test_reveal_inside_list_items(deck):
    """Spec 3.12: an attribute line inside an item applies to the next block of that item; a nested list
    marked reveal shows one item per fragment, numbered in document order."""
    root = deck({"talk.md": """
        # A
        {.reveal}
        - one
        - two
          {.reveal .sub}
          - two a
          - two b
        - three

          {#late .reveal}
          A paragraph of the item, after its text.
        - four
          {.reveal-with}
          - with four
        - five {.reveal} stays text
          - not revealed
    """})
    s = build_deck(root, use_cache=False).slides["a"]
    html = s.body_html
    assert s.reveal_count == 8 and "{.reveal" not in html.replace("five {.reveal} stays text", "")
    assert '<ul class="sub">' in html
    for n, text in [(1, "one"), (2, "two"), (3, "two a"), (4, "two b"), (5, "three"), (7, "four"), (8, "five")]:
        assert re.search(rf'<li data-lt-reveal="{n}">\s*(<p>)?{text}', html), (n, text)
    assert '<p id="late" data-lt-reveal="6">A paragraph' in html
    root.write_text("# A\n{.reveal}\n- one\n\n  {.reveal}\n\n  - one a\n- two\n")  # the line as a paragraph of its own
    s2 = build_deck(root, use_cache=False).slides["a"]
    assert s2.reveal_count == 3 and "{.reveal}" not in s2.body_html
    assert '<ul data-lt-reveal="7">' in html and "<li>with four</li>" in html  # reveal-with: the list joins four
    assert "five {.reveal} stays text" in html and "<li>not revealed</li>" in html
    root.write_text("# A\n- plain\n  {.reveal}\n  - a\n  - b\n")  # the outer list need not be revealed
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.reveal_count == 2 and '<li>plain\n<ul>\n<li data-lt-reveal="1">a</li>' in s.body_html


def test_reveal_with_errors(deck):
    root = deck({"talk.md": "# A\n{.reveal-with}\nAlone.\n"})
    assert "LT057" in codes(check_deck(root, use_cache=False))  # no fragment before it
    root.write_text("# A\n{.reveal}\n- x\n\n{.reveal .reveal-with}\nBoth.\n")
    assert "LT057" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n{.reveal}\n- x\n\n{.reveal-with}\n::detour-badge{ref=d}\n::: detour {#d}\n# In\n:::\n")
    assert "LT056" in codes(check_deck(root, use_cache=False))  # a badge is never a fragment


def test_attribute_line_before_a_detour_is_reported(deck):
    """Spec 3.9, LT065: a detour's badge is not a fragment, and an attribute line before the container applies to
    nothing; it used to be dropped without a word."""
    root = deck({"talk.md": "# A\n{.reveal}\n- x\n\n{.reveal}\n::: detour {#d}\n# In\n:::\n\n{#e .c}\n\n::: detour\n# In2\n:::\n"})
    d = build_deck(root, use_cache=False)
    items = d.diagnostics.items
    assert [(x.code, x.loc.line) for x in items] == [("LT065", 6), ("LT065", 12)], items
    assert "badge=step or badge=next" in items[0].message and "::detour-badge" in items[1].message
    assert d.slides["a"].reveal_count == 1  # nothing changes otherwise: the badge is shown at every step
    root.write_text("# A\n::: detour {#d}\n# In\n:::\n")
    assert not check_deck(root, use_cache=False).items


def test_container_typo_warning(deck):
    root = deck({"talk.md": "# A\n::: colums\nx\n:::\n"})
    assert "LT019" in codes(build_deck(root, use_cache=False).diagnostics)


def test_detour_badge_directive_is_a_leaf_block_anywhere():
    """Spec 3.2: `::detour-badge{...}` alone on its line is a leaf directive, inside containers and lists too."""
    from lattice.markdown import create_markdown

    md = create_markdown()
    src = ("::: column\n::detour-badge{ref=a}\n:::\n\n- item\n- ::detour-badge{ref=b label=\"B\"}\n\n"
           "> ::detour-badge{ref=c}\n\ntext ::detour-badge{ref=d}\n\n::detour-badge\n")
    badges = [t.info for t in md.parse(src, {}) if t.type == "lt_badge"]
    assert badges == ["{ref=a}", '{ref=b label="B"}', "{ref=c}"]  # not inline, and braces are required
    assert [t.type for t in md.parse("::include{file=x.md}\n", {})] == ["lt_include"]


# ---------------------------------------------------------------- container fences (spec 3.2)


def container_tree(src: str) -> list:
    """The containers of a Markdown source as nested ``(name, [children])`` pairs."""
    from lattice.markdown import container_name, create_markdown

    root: list = []
    stack = [root]
    for t in create_markdown().parse(src, {}):
        if t.type == "container_lt_open":
            node = (container_name(t)[0], [])
            stack[-1].append(node)
            stack.append(node[1])
        elif t.type == "container_lt_close":
            stack.pop()
    return root


def fence_problems(src: str) -> dict:
    from lattice.markdown import create_markdown

    env: dict = {}
    create_markdown().parse(src, env)
    return {line + 1: code for (code, line) in env.get("fence_problems", {})}


COLUMNS_TREE = [("columns", [("column", []), ("column", [("callout", [])])])]


def test_bare_closing_fence_closes_the_innermost_container():
    """A: fences of three colons nest; each bare fence closes the innermost open container."""
    src = ("::: columns\n::: column {width=1fr}\nleft\n:::\n::: column\n::: callout {kind=info}\nnote\n:::\n"
           "right\n:::\n:::\n\nafter\n")
    assert container_tree(src) == COLUMNS_TREE
    assert fence_problems(src) == {}


def test_colon_counts_are_cosmetic():
    """A: any count of three or more colons, in any order; the earlier decreasing style still parses the same."""
    legacy = ("::::: columns\n:::: column\nleft\n::::\n:::: column\n::: callout\nnote\n:::\nright\n::::\n"
              ":::::\n")
    inverted = ("::: columns\n:::: column\nleft\n::::::\n::::: column\n:::::::: callout\nnote\n:::\n"
                "right\n:::\n:::\n")
    assert container_tree(legacy) == container_tree(inverted) == COLUMNS_TREE


def test_closing_fence_ends_a_lazy_paragraph():
    """A: a closing fence right after a paragraph line closes the container, it is not paragraph text."""
    from lattice.markdown import create_markdown

    tokens = create_markdown().parse("::: callout\nsome text\n:::\nafter\n", {})
    inline = [t.content for t in tokens if t.type == "inline"]
    assert inline == ["some text", "after"]
    assert [t.type for t in tokens][-4:] == ["container_lt_close", "paragraph_open", "inline", "paragraph_close"]


@pytest.mark.parametrize("quoted", [
    "```markdown\n::: callout\nquoted\n:::\n```\n",
    "~~~~\n:::\n~~~~\n",
    "````markdown\n```\n:::\n```\n````\n",
    "- item\n\n  ```\n  :::\n  ```\n",
    "> ```\n> :::\n> ```\n",
    "    ::: indented code\n    :::\n",
])
def test_fences_in_code_blocks_are_not_container_fences(quoted):
    """A: the lines of a code block are skipped when looking for the closing fence (the old pitfall)."""
    src = f"::: columns\n::: column\n{quoted}:::\n::: column\nright\n:::\n:::\n"
    assert container_tree(src) == [("columns", [("column", []), ("column", [])])]
    assert fence_problems(src) == {}


def test_containers_in_list_items_and_quotes():
    src = "::: column\n- item\n\n  ::: callout\n  inside\n  :::\n- next\n\n> ::: callout\n> quoted\n> :::\n:::\n"
    assert container_tree(src) == [("column", [("callout", []), ("callout", [])])]
    assert fence_problems(src) == {}
    # a code block in a quote ends with the quote, so the fence after it closes the column
    assert container_tree("::: column\n> ```\n> code\n:::\nafter\n") == [("column", [])]
    # a container opened in a list item ends with the item: the fence at the margin has nothing to close
    assert fence_problems("::: column\n- item\n\n  ::: callout\n  x\n:::\n:::\n") == {4: "LT062", 6: "LT061"}


def test_stray_and_unclosed_fences():
    """A: a closing fence with no open container is LT061; a container never closed is LT062."""
    assert fence_problems("text\n\n:::\n") == {3: "LT061"}
    assert fence_problems("::: callout\nx\n:::\n:::\n") == {4: "LT061"}
    assert fence_problems("::: columns\n::: column\nx\n:::\n") == {1: "LT062"}


def test_named_closing_fences():
    """B: `::: /NAME` closes the innermost container and checks its name, whatever its colons."""
    src = ("::: columns\n::: column\nleft\n::: /column\n::: column\n::: callout\nnote\n::: /callout\n"
           "right\n::::: /column\n:::/columns\n")
    assert container_tree(src) == COLUMNS_TREE
    assert fence_problems(src) == {}


@pytest.mark.parametrize("src, line", [
    ("::: columns\n::: column\nx\n::: /columns\n:::\n", 4),         # names the parent, not the innermost
    ("::: columns\n::: column\nx\n:::\n::: /column\n", 5),           # the column is already closed
    ("::: callout\nx\n::: /callout {kind=info}\n", 3),               # malformed: attributes
    ("::: callout\nx\n::: /\n", 3),                                  # malformed: no name
    ("# A\n\n::: /callout\n", 3),                                    # no open container
])
def test_named_closing_fence_errors(src, line):
    assert fence_problems(src) == {line: "LT061"}


def test_bare_and_named_closing_fences_mix():
    """A and B together: named and bare fences, of any colon count, in one file give one structure."""
    bare = ("::: detour {#d}\n# In\n::: columns\n::: column\nleft\n:::\n::: column\n::: callout\nnote\n:::\n"
            ":::\n:::\n:::\n")
    mixed = ("::: detour {#d}\n# In\n:::: columns\n::: column\nleft\n::: /column\n::: column\n"
             "::: callout\nnote\n:::\n:::::\n::: /columns\n:::::: /detour\n")
    tree = [("detour", COLUMNS_TREE)]
    assert container_tree(bare) == container_tree(mixed) == tree
    assert fence_problems(mixed) == {}
    # a bare fence closes the innermost container: the named fence after it closes the columns (and
    # reports the name), so the last fence has nothing left to close
    wrong = "::: columns\n::: column\nx\n:::\n::: /column\n:::\n"
    assert fence_problems(wrong) == {5: "LT061", 6: "LT061"}


def test_same_count_fences_in_a_deck(deck):
    """A and B in a whole deck: a detour of slides with columns, all with three colons."""
    root = deck({"talk.md": """
        # Origin
        ::: columns
        ::: column {width=2fr}
        ::detour-badge{ref=d}
        :::
        ::: column {width=3fr}
        ::: callout {kind=info}
        Note
        :::
        :::
        :::

        ::: detour {#d label="More"}
        # Inside
        ::: columns
        ::: column
        ```markdown
        ::: callout
        quoted
        :::
        ```
        ::: /column
        ::: column
        right
        ::: /column
        ::: /columns

        # Second inside
        text
        ::: /detour

        # After
        end
    """})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    assert list(d.slides) == ["origin", "inside", "second-inside", "after"]
    assert [s.id for s in d.detours["d"].slides] == ["inside", "second-inside"]
    origin = d.slides["origin"].body_html
    assert origin.count('class="lt-column"') == 2 and "lt-callout-info" in origin and "lt-detour-badge" in origin
    inside = d.slides["inside"].body_html
    assert inside.count('class="lt-column"') == 2 and "lt-callout" not in inside


def test_fence_diagnostics_have_locations(deck):
    root = deck({"talk.md": "# A\n::: columns\n::: column\nx\n::: /columns\n:::\n\n# B\n:::\n"})
    found = [(x.code, x.severity, x.loc.line) for x in check_deck(root, use_cache=False).items
             if x.code in ("LT061", "LT062")]
    assert found == [("LT061", "error", 5), ("LT061", "error", 9)]
    root.write_text("# A\n::: callout\nx\n")
    found = [(x.code, x.severity, x.loc.line) for x in check_deck(root, use_cache=False).items]
    assert ("LT062", "warning", 2) in found
