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


def test_container_typo_warning(deck):
    root = deck({"talk.md": "# A\n::: colums\nx\n:::\n"})
    assert "LT019" in codes(build_deck(root, use_cache=False).diagnostics)
