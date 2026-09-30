from lattice.build import build_deck, check_deck


def codes(diags):
    return {d.code for d in diags.items}


def test_detours_and_back(deck):
    root = deck({"talk.md": """
        # Origin
        ::: detour {#d label="Side" key=h}
        # Side one
        # Side two
        :::
        # After
    """})
    d = build_deck(root, use_cache=False)
    assert d.main_path == ["origin", "after"]
    assert d.slides["side-one"].next == "side-two"
    assert d.slides["side-two"].next == "back"
    assert d.detours["d"].origin.id == "origin"
    kinds = {(e.source, e.target, e.kind) for e in d.edges}
    assert ("origin", "side-one", "detour") in kinds


def test_branch_has_no_implicit_next(deck):
    root = deck({"talk.md": """
        # Choose
        ::: branch
        - [[x|X]]
        - [[y]] {key=7}
        :::
        # X {next=end}
        # Y {next=end}
        # End
    """})
    d = build_deck(root, use_cache=False)
    s = d.slides["choose"]
    assert s.next is None
    assert [(o.target, o.key) for o in s.branch.options] == [("x", "1"), ("y", "7")]
    assert "LT015" not in codes(d.diagnostics)


def test_next_leaving_detour_is_an_error(deck):
    root = deck({"talk.md": """
        # A
        ::: detour
        # Inside {next=b}
        :::
        # B
    """})
    assert "LT013" in codes(check_deck(root, use_cache=False))


def test_main_path_cycle(deck):
    root = deck({"talk.md": "# A {next=b}\n# B {next=a}\n"})
    assert "LT014" in codes(check_deck(root, use_cache=False))


def test_key_collisions(deck):
    root = deck({"talk.md": """
        # A
        ::: detour {key=o}
        # D
        :::
    """})
    assert "LT018" in codes(check_deck(root, use_cache=False))


def test_unreachable_warning(deck):
    root = deck({"talk.md": "# A {next=none}\n# B\n"})
    d = build_deck(root, use_cache=False)
    assert "LT015" in codes(d.diagnostics)


def test_tours(deck):
    root = deck({"talk.md": """
        ---
        tours:
          short: [a, d, c]
          all: main
        ---
        # A
        ::: detour {#d}
        # D1
        # D2
        :::
        # C
    """})
    d = build_deck(root, use_cache=False)
    assert d.tours["short"] == ["a", "d1", "d2", "c"]
    assert d.tours["all"] == ["a", "c"]
