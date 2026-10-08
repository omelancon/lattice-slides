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


def test_page_keys_are_free_and_backspace_is_global(deck):
    """Spec 7.6: PageUp and PageDown are not bound since 0.29, so a slide may use them; Backspace is `undo`."""
    for key, collides in (("PageDown", False), ("PageUp", False), ("Backspace", True)):
        root = deck({"talk.md": f"""
            # A
            ::: detour {{key={key}}}
            # D
            :::
        """})
        assert ("LT018" in codes(check_deck(root, use_cache=False))) == collides, key


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


def test_old_skip_names_bind_the_checkpoint_keys(deck):
    """Spec 7.6: `skip-forward` and `skip-back` in `keys:` are aliases of the checkpoint actions since 0.30."""
    from lattice.model import key_bindings

    keys = key_bindings({"skip-forward": "n", "skip-back": ["N", "b"]})
    assert keys["next-checkpoint"] == ["n"] and keys["prev-checkpoint"] == ["N", "b"]
    assert "skip-forward" not in keys and "skip-back" not in keys
    root = deck({"talk.md": """
        ---
        keys: {skip-forward: n}
        ---
        # A
        ::: detour {key=n}
        # D
        :::
    """})
    assert "LT018" in codes(check_deck(root, use_cache=False))
