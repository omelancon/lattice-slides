import textwrap

import pytest

from lattice.anim import ArrayTrace, GraphTrace, GridTrace, Trace, TreeTrace, apply_delta, diff
from lattice.build import build_deck, check_deck
from lattice.graphs import tree_layouts

ALGOS = '''
from lattice import GraphTrace, ArrayTrace

def walk(g, start="A"):
    t = GraphTrace(g)
    for n in sorted(g):
        t.frame(nodes={n: "active"}, meta={"line": 1})
    return t

def arr(values):
    t = ArrayTrace(values)
    t.frame(caption="start")
    t.frame(marks={0: "compare"})
    return t
'''


def codes(diags):
    return {d.code for d in diags.items}


def test_single_track_needs_no_timeline(deck):
    root = deck({"talk.md": """
        # A
        ```graph-anim {source="algos.py:walk" edges='["A B", "B C"]'}
        ```
    """, "algos.py": ALGOS})
    # edges given as attribute are a string: use the body instead
    root.write_text('# A\n```graph-anim {source="algos.py:walk"}\nedges: ["A B", "B C"]\n```\n')
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.steps == 3
    assert s.positions == [[0], [1], [2]]


def test_two_tracks_need_a_timeline(deck):
    root = deck({"talk.md": """
        # A
        {.reveal}
        - x
        ```array-anim {#arr source="algos.py:arr"}
        values: [3, 1]
        ```
    """, "algos.py": ALGOS})
    assert "LT023" in codes(check_deck(root, use_cache=False))


def test_timeline_with_follower(deck):
    root = deck({"talk.md": """
        # A
        {.reveal}
        - x
        - y
        ```graph-anim {#g source="algos.py:walk"}
        edges: ["A B", "B C"]
        ```
        ```code {#c lang=python follow=g}
        pass
        ```
        ```timeline
        reveal 2
        g 1..end
        reveal 0, g 0
        ```
    """, "algos.py": ALGOS})
    s = build_deck(root, use_cache=False).slides["a"]
    assert [t.id for t in s.tracks] == ["reveal", "g", "c"]
    assert s.positions == [[0, 0, 0], [2, 0, 0], [2, 1, 1], [2, 2, 2], [0, 0, 0]]


def test_timeline_errors(deck):
    root = deck({"talk.md": """
        # A
        ```array-anim {#arr source="algos.py:arr"}
        values: [3, 1]
        ```
        ```timeline
        arr 5
        nope 1
        ```
    """, "algos.py": ALGOS})
    assert {"LT025", "LT024"} <= codes(check_deck(root, use_cache=False))
    root.write_text("# A\n{.reveal}\n- x\n- y\n- z\n"
                    "```array-anim {#arr source=\"algos.py:arr\"}\nvalues: [3, 1]\n```\n"
                    "```timeline\narr 0..1, reveal 1..3\n```\n")
    assert "LT031" in codes(check_deck(root, use_cache=False))  # ranges of different lengths on one line


def sugar_deck(deck, timeline: str, items: int = 6):
    """A slide with `items` fragments (reveal positions 0..items), a 5-frame walk `g` and its follower `c`."""
    bullets = "\n".join(f"- item {k}" for k in range(1, items + 1))
    body = "\n".join("        " + line for line in timeline.strip().split("\n"))
    return deck({"talk.md": f"""
        # A
        {{.reveal}}
{textwrap.indent(bullets, "        ")}
        ```graph-anim {{#g source="algos.py:walk"}}
        edges: ["A B", "B C", "C D", "D E"]
        ```
        ```code {{#c lang=python follow=g}}
        pass
        ```
        ```timeline
{body}
        ```
    """, "algos.py": ALGOS})


def columns(root, *tracks):
    s = build_deck(root, use_cache=False).slides["a"]
    ids = [t.id for t in s.tracks]
    return [tuple(row[ids.index(t)] for t in tracks) for row in s.positions]


def warnings(root):
    return [(d.code, d.message) for d in check_deck(root, use_cache=False).items]


@pytest.mark.parametrize("timeline, expected", [
    ("reveal 2\nreveal ..end", [0, 2, 3, 4, 5, 6]),        # the remaining fragments, one per step
    ("reveal 2\nreveal ..+2", [0, 2, 3, 4]),               # `..+2` is two steps where `+2` is one
    ("reveal 2\nreveal +2", [0, 2, 4]),
    ("reveal 5\nreveal ..-2", [0, 5, 4, 3]),               # backward, one position per step
    ("reveal 2\nreveal ..4\nreveal ..0", [0, 2, 3, 4, 3, 2, 1, 0]),  # absolute stops, both directions
    ("reveal 3\nreveal 1..end", [0, 3, 1, 2, 3, 4, 5, 6]),  # a closed range still starts at its start
    ("reveal ..end", [0, 1, 2, 3, 4, 5, 6]),                 # from position 0
    ("reveal end-2", [0, 4]),
    ("reveal 1..end-2\nreveal end", [0, 1, 2, 3, 4, 6]),
    ("reveal ..end - 1", [0, 1, 2, 3, 4, 5]),               # spaces are allowed
    ("reveal end..end-2", [0, 6, 5, 4]),
    ("reveal 1..end by 2", [0, 1, 3, 5, 6]),                # the stop is always the last cue
    ("reveal 1..5 by 2", [0, 1, 3, 5]),
    ("reveal 2\nreveal ..end by 2", [0, 2, 4, 6]),         # an open range leaves out the current position
    ("reveal 2\nreveal ..end by 3", [0, 2, 5, 6]),
    ("reveal 6\nreveal ..0 by 4", [0, 6, 2, 0]),
    ("reveal 4..4", [0, 4]),
])
def test_timeline_ranges(deck, timeline, expected):
    """Spec 6.3: open ranges, `end-N` and strides on the reveal track."""
    root = sugar_deck(deck, timeline + "\ng end")
    assert [r for (r,) in columns(root, "reveal")][:-1] == expected
    assert warnings(root) == []


def test_timeline_open_ranges_on_a_component(deck):
    root = sugar_deck(deck, "reveal 1\ng ..+2\nreveal ..end, g end\ng ..0 by 2")
    assert columns(root, "reveal", "g", "c") == [
        (0, 0, 0), (1, 0, 0), (1, 1, 1), (1, 2, 2), (2, 4, 4), (3, 4, 4), (4, 4, 4), (5, 4, 4), (6, 4, 4),
        (6, 2, 2), (6, 0, 0)]  # other assignments go in the first cue; the follower copies its leader


def test_timeline_lockstep_ranges(deck):
    root = sugar_deck(deck, "reveal 2\nreveal ..+4, g ..end\ng ..0 by 2, reveal ..4")
    assert columns(root, "reveal", "g") == [(0, 0), (2, 0), (3, 1), (4, 2), (5, 3), (6, 4), (5, 2), (4, 0)]
    assert warnings(root) == []
    root = sugar_deck(deck, "reveal 1..3, g 1..4")
    assert any(c == "LT031" and "reveal 3, g 4" in m for c, m in warnings(root))


def test_timeline_open_range_after_a_detour_step(deck):
    root = sugar_deck(deck, "reveal 2\ndetour d1\nreveal ..+2\ng end")
    root.write_text(root.read_text() + "::: detour {#d1}\n# Inside\n:::\n")
    s = build_deck(root, use_cache=False).slides["a"]
    assert [row[0] for row in s.positions] == [0, 2, 2, 3, 4, 4] and s.step_detours == {2: {"id": "d1", "blocking": False}}


def test_timeline_empty_open_range(deck):
    """An open range whose track is already at its stop: LT030, and no step unless the line sets other tracks."""
    root = sugar_deck(deck, "reveal end\nreveal ..end\ng end")
    assert columns(root, "reveal") == [(0,), (6,), (6,)]
    assert [c for c, _ in warnings(root)] == ["LT030"]
    root = sugar_deck(deck, "reveal end\nreveal ..end, g 2\ng end")
    assert columns(root, "reveal", "g") == [(0, 0), (6, 0), (6, 2), (6, 4)]
    assert [c for c, _ in warnings(root)] == ["LT030"]


@pytest.mark.parametrize("timeline, code", [
    ("reveal 5\nreveal ..+3", "LT025"),      # two positions left
    ("reveal 1\nreveal ..-2", "LT025"),
    ("reveal end-7", "LT025"),
    ("reveal ..9", "LT025"),
    ("reveal 2..+3", "LT049"),                # a relative stop after an explicit start is ambiguous
    ("reveal 2..-1", "LT049"),
    ("reveal 1..3 by 0", "LT049"),
    ("reveal 3 by 2", "LT049"),               # a stride needs a range
    ("reveal +1..end", "LT049"),              # no relative starts
    ("reveal ..", "LT049"),
    ("reveal ..end, reveal 1", "LT049"),
    ("reveal ..+2, g ..+3", "LT031"),
])
def test_timeline_range_errors(deck, timeline, code):
    root = sugar_deck(deck, timeline + "\ng end")
    found = [c for c, _ in warnings(root)]
    assert code in found and found.count("LT025") <= 1  # LT025 once per line


def test_delta_roundtrip():
    a = {"nodes": {"A": {"state": "active"}, "B": {"state": "x"}}, "caption": "c"}
    b = {"nodes": {"A": {"state": "visited", "label": 3}}, "panel": {"d": [1, 2]}}
    assert apply_delta(a, diff(a, b)) == b


def test_frame_store_keyframed():
    t = Trace()
    for i in range(40):
        t.frame(step=i, marks={"k": i % 3})
    full = t.frame_store()
    kf = t.frame_store(max_full_bytes=10, keyframe_interval=8)
    assert full["format"] == "full" and kf["format"] == "keyframed"
    state = kf["keyframes"][2]
    for j in range(17, 22):
        state = apply_delta(state, kf["deltas"][j])
    assert state == full["frames"][21]


def test_transient_marks():
    t = ArrayTrace([1, 2])
    t.frame(marks={0: "compare"})
    t.frame()
    assert t.frames[0]["marks"] == {"0": "compare"}
    assert t.frames[1]["marks"] == {}


def test_graph_trace_edge_keys():
    import networkx as nx

    t = GraphTrace(nx.DiGraph([("a", "b")]))
    t.frame(edges={("a", "b"): "tree"})
    assert t.frames[0]["edges"] == {"a->b": {"state": "tree"}}


# ---------------------------------------------------------------- trees and grids (spec 9.1, 9.4)


class _Node:
    def __init__(self, key, left=None, right=None):
        self.key, self.left, self.right = key, left, right


def test_tree_trace_snapshots_objects_and_keeps_the_shape():
    a, c = _Node(1), _Node(3)
    b = _Node(2, a, c)
    t = TreeTrace(b)
    t.frame(nodes={2: "active"}, edges={(2, 1): "tree"})
    a.right, b.left = b, None  # rotate right at 2: 1 becomes the root
    t.frame(root=a, caption="rotated")
    t.frame(caption="same shape")
    assert t.frames[0]["tree"] == {"root": "2", "kids": {"2": ["1", "3"]}}
    assert t.frames[0]["edges"] == {"2->1": {"state": "tree"}}
    assert t.frames[1]["tree"] == {"root": "1", "kids": {"1": [None, "2"], "2": [None, "3"]}}
    assert t.frames[2]["tree"] == t.frames[1]["tree"]  # replaced as a whole, then kept


def test_tree_trace_accepts_tuples_and_callables():
    t = TreeTrace(children="kids", key=lambda n: n["name"])
    t.frame(root={"name": "r", "kids": [{"name": "x", "kids": []}, {"name": "y"}]})
    t.frame(root=("A", ("B",), "C"))
    assert t.frames[0]["tree"] == {"root": "r", "kids": {"r": ["x", "y"]}}
    assert t.frames[1]["tree"] == {"root": "A", "kids": {"A": ["B", "C"]}}


def test_tree_trace_rejects_repeated_nodes():
    n = _Node(1)
    n.left = n
    with pytest.raises(ValueError, match="appears twice"):
        TreeTrace(n)


def test_binary_layout_keeps_x_through_a_rotation():
    before = {"root": "y", "kids": {"y": ["x", "T3"], "x": ["T1", "T2"]}}
    after = {"root": "x", "kids": {"x": ["T1", "y"], "y": ["T2", "T3"]}}
    size, (p0, p1) = tree_layouts([before, after])
    assert size["width"] > 0 and size["height"] > 0
    for n in ("T1", "x", "T2", "y", "T3"):
        assert p0[n][0] == p1[n][0]
    assert p0["y"][1] < p1["y"][1] and p0["x"][1] > p1["x"][1]


def test_grid_trace_cells_marks_arrows_and_pointers():
    g = GridTrace(["#.", ".."], cols=["a", "b"])
    g.frame(put={(1, 1): 7}, cells={(0, 0): "wall"}, marks={(1, 1): "active"},
            arrows={((1, 1), (0, 1)): "path"}, pointers={"p": (1, 0)})
    g.frame(pointers={"p": None}, arrows={"1,1->0,1": None})
    f0, f1 = g.frames
    assert f0["values"] == [["#", "."], [".", 7]] and f0["cols"] == ["a", "b"]
    assert f0["cells"] == {"0,0": "wall"} and f0["marks"] == {"1,1": "active"}
    assert f0["arrows"] == {"1,1->0,1": "path"} and f0["pointers"] == {"p": [1, 0]}
    assert f1["marks"] == {} and f1["pointers"] == {} and f1["arrows"] == {}
    assert f1["cells"] == {"0,0": "wall"}  # persistent


TREES = '''
from lattice import GridTrace, TreeTrace

def grow(values):
    t = TreeTrace()
    root = None
    for v in values:
        root = (v, root) if root else (v,)
        t.frame(root=root)
    return t

def table(values, fill=0):
    g = GridTrace(values)
    g.frame(put={(0, 0): fill})
    g.frame(cells={(0, 1): "done"})
    return g
'''


def test_tree_and_grid_components(deck):
    root = deck({"talk.md": """
        # A
        ```tree-anim {#t source="algos.py:grow"}
        values: [1, 2, 3]
        ```

        # B
        ```grid-anim {#g source="algos.py:table" fill=5}
        values: [[1, 2], [3, 4]]
        ```
    """, "algos.py": TREES})
    d = build_deck(root, use_cache=False)
    a, b = d.slides["a"], d.slides["b"]
    assert a.steps == 3 and b.steps == 2
    tdata = d.instances["a/t"]["data"]
    frames = tdata["frames"]["frames"]
    assert set(frames[2]["pos"]) == {"1", "2", "3"} and tdata["size"]["r"] > 0
    gdata = d.instances["b/g"]["data"]
    assert gdata["dims"] == {"rows": 2, "cols": 2, "cell": 48, "rowHead": False, "colHead": False}
    assert gdata["frames"]["frames"][0]["values"][0][0] == 5  # extra option passed to the trace function


def test_tree_anim_needs_a_tree_trace(deck):
    root = deck({"talk.md": "# A\n```tree-anim {source=\"algos.py:table\"}\nvalues: [[1]]\n```\n", "algos.py": TREES})
    assert "LT022" in codes(check_deck(root, use_cache=False))


DETOUR_STEPS = """
# A
{.reveal}
- x
- y
- z

::: detour {#d1 at=1 blocking=true}
# Inside one
:::

# B
{.reveal}
- x
- y

```timeline
reveal 1
detour d2
reveal 2
detour d2 blocking
```

::: detour {#d2}
# Inside two
:::
"""


def test_detour_steps(deck):
    """Spec 6.4: `at=N` and `detour ID` insert a step that repeats the previous positions and enters the detour."""
    root = deck({"talk.md": DETOUR_STEPS})
    d = build_deck(root, use_cache=False)
    a, b = d.slides["a"], d.slides["b"]
    assert a.positions == [[0], [1], [1], [2], [3]] and a.step_detours == {2: {"id": "d1", "blocking": True}}
    assert b.positions == [[0], [1], [1], [2], [2]]
    assert b.step_detours == {2: {"id": "d2", "blocking": False}, 4: {"id": "d2", "blocking": True}}
    from lattice.emit import deck_json
    from lattice.pdf import select_steps

    assert deck_json(d)["slides"]["a"]["stepDetours"] == {"2": {"id": "d1", "blocking": True}}
    assert select_steps("all", a.steps, set(a.step_detours)) == [0, 1, 3, 4]
    assert select_steps("last", a.steps, set(a.step_detours)) == [4]


def test_detour_step_errors(deck):
    root = deck({"talk.md": """
        # A
        {.reveal}
        - x
        ::: detour {#d1 at=7}
        # Inside
        :::
    """})
    assert "LT054" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n```timeline\ndetour nope\n```\n::: detour {#d1}\n# Inside\n:::\n")
    assert "LT054" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n{.reveal}\n- x\n```timeline\nreveal 1\n```\n::: detour {#d1 at=0}\n# Inside\n:::\n")
    assert "LT054" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n```timeline\ndetour d1, reveal 1\n```\n::: detour {#d1}\n# Inside\n:::\n")
    assert "LT054" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n::: detour {#d1 at=x}\n# Inside\n:::\n")
    assert "LT009" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n::: detour {#d1 blocking=maybe}\n# Inside\n:::\n")
    assert "LT009" in codes(check_deck(root, use_cache=False))


BADGE_STEPS = """
# A
{.reveal}
```python
x = 1
```

::: detour {#d1 at=1 badge=next key=a}
# Inside one
:::

::: detour {#d2 at=1 badge=step key=b}
# Inside two
:::

::: detour {#d3 key=c}
# Inside three
:::

# B
{.reveal}
- x

```timeline
reveal 1
detour d4
```

::: detour {#d4 badge=next}
# Inside four
:::
"""


def test_badge_step_modes(deck):
    """Spec 3.9: `badge=step|next` is display only; the step table is the one `at=` gives."""
    root = deck({"talk.md": BADGE_STEPS})
    d = build_deck(root, use_cache=False)
    a = d.slides["a"]
    assert [x.badge_mode for x in a.detours] == ["next", "step", None]
    assert all(x.badge for x in a.detours)
    assert a.positions == [[0], [1], [1], [1]]
    assert a.step_detours == {2: {"id": "d1", "blocking": False}, 3: {"id": "d2", "blocking": False}}
    assert 'data-lt-detour="d1" data-lt-badge="next"' in a.body_html
    assert 'data-lt-detour="d2" data-lt-badge="step"' in a.body_html
    assert 'data-lt-detour="d3">' in a.body_html  # a plain badge carries no mode
    assert 'data-lt-badge="next"' in d.slides["b"].body_html  # a timeline detour step works too


def test_badge_step_errors(deck):
    root = deck({"talk.md": "# A\n::: detour {#d1 badge=next}\n# Inside\n:::\n"})
    assert "LT055" in codes(check_deck(root, use_cache=False))  # no detour step to tie the badge to
    root.write_text("# A\n{.reveal}\n- x\n```timeline\nreveal 1\n```\n::: detour {#d1 badge=step}\n# Inside\n:::\n")
    assert "LT055" in codes(check_deck(root, use_cache=False))  # a timeline that does not name it
    root.write_text("# A\n{.reveal}\n- x\n::: detour {#d1 at=5 badge=step}\n# Inside\n:::\n")
    assert codes(check_deck(root, use_cache=False)) & {"LT054", "LT055"} == {"LT054"}  # one mistake, one error
    root.write_text("# A\n::: detour {#d1 badge=later}\n# Inside\n:::\n")
    assert "LT009" in codes(check_deck(root, use_cache=False))
    root.write_text("# A\n{.reveal}\n- x\n::: detour {#d1 at=0 badge=Next}\n# Inside\n:::\n")
    assert not check_deck(root, use_cache=False).errors  # values are case-insensitive, like booleans


PLACED_BADGES = """
# A
:::: columns
::: column
{.reveal}
- x

::detour-badge{ref=d1}
:::
::: column
- see ::detour-badge{ref=d1} inline is text
- ::detour-badge{ref=d2 label="Short" badge=next #b2 .wide}

{.loud}
::detour-badge{ref=d2 badge=true}
:::
::::

::: detour {#d1 at=1 badge=step key=a}
# Inside one
:::

::: detour {#d2 at=1 badge=step key=b}
# Inside two
:::

::: detour {#d3 key=c}
# Inside three
:::
"""


def test_placed_badges(deck):
    """Spec 3.9: a placed badge replaces the default one, inherits the detour's mode and label, and may override them."""
    root = deck({"talk.md": PLACED_BADGES})
    d = build_deck(root, use_cache=False)
    a = d.slides["a"]
    body = a.body_html
    assert a.step_detours == {2: {"id": "d1", "blocking": False}, 3: {"id": "d2", "blocking": False}}
    assert body.count('data-lt-detour="d1"') == 1 and body.count('data-lt-detour="d2"') == 2
    assert 'class="lt-detour-badge" type="button" data-lt-detour="d1" data-lt-badge="step"><kbd>a</kbd>' in body
    assert ('class="lt-detour-badge wide" type="button" data-lt-detour="d2" id="b2" data-lt-badge="next">'
            '<kbd>b</kbd><span>Short</span>') in body
    assert 'class="lt-detour-badge loud" type="button" data-lt-detour="d2"><kbd>b</kbd><span>Inside two</span>' in body
    assert 'data-lt-detour="d3">' in body  # an unplaced detour keeps its default badge
    first, second = body.split('<div class="lt-column"')[1:]
    assert 'data-lt-detour="d1"' in first and 'data-lt-detour="d2"' not in first  # each badge in its column
    assert second.count('data-lt-detour="d2"') == 2
    assert "\x00" not in body
    assert [m for m, _ in d.detours["d2"].badges] == ["next", None]


def test_placed_badge_errors(deck):
    def check(src):
        return codes(check_deck(root, use_cache=False)) if root.write_text(src) is not None else None

    root = deck({"talk.md": "# A\n"})
    det = "::: detour {#d1 at=0 key=a}\n# Inside\n:::\n"
    assert "LT056" in check("# A\n::detour-badge{label=x}\n" + det)  # no ref
    assert "LT056" in check("# A\n::detour-badge{ref=nope}\n" + det)  # unknown
    assert "LT056" in check("# A\n::detour-badge{ref=d1}\n# B\n" + det)  # a detour of another slide
    assert "LT056" in check("# A\n::detour-badge{ref=a-detour-1}\n::: detour\n# Inside\n:::\n")  # generated id
    assert "LT056" in check("# A\n::detour-badge{ref=d1}\n::: detour {#d1 badge=false}\n# Inside\n:::\n")
    assert "LT056" in check("# A\n::detour-badge{ref=d1 key=z}\n" + det)  # key belongs to the detour
    assert "LT056" in check("# A\n::detour-badge{ref=d1 at=2}\n" + det)  # so does at
    assert "LT056" in check("# A\n::detour-badge{ref=d1 badge=false}\n" + det)
    assert "LT056" in check("# A\n{.reveal}\n::detour-badge{ref=d1}\n" + det)
    assert "LT056" in check("# A\n::: notes\n::detour-badge{ref=d1}\n:::\n" + det)
    assert not check("# A\n::detour-badge{ref=d1 badge=next}\n" + det)
    # LT055 for each badge that waits for a detour step the detour does not have
    nostep = "::: detour {#d1 key=a}\n# Inside\n:::\n"
    assert "LT055" in check("# A\n::detour-badge{ref=d1 badge=step}\n" + nostep)
    lt055 = [x for x in check_deck(root, use_cache=False).items if x.code == "LT055"]
    assert [x.loc.line for x in lt055] == [2]  # reported at the badge, not at the detour
    assert "LT055" in check("# A\n::detour-badge{ref=d1}\n::: detour {#d1 badge=next}\n# Inside\n:::\n")
    # the detour's own mode is checked even when its placed badges override it
    assert "LT055" in check("# A\n::detour-badge{ref=d1 badge=true}\n::: detour {#d1 badge=next}\n# Inside\n:::\n")
    assert not check("# A\n::detour-badge{ref=d1 badge=true}\n::: detour {#d1}\n# Inside\n:::\n")
    # an attribute line gives only an #id and classes; a branch cannot hold a badge
    assert "LT056" in check("# A\n{.wide type=submit}\n::detour-badge{ref=d1}\n" + det)
    assert "LT056" in check("# A\n::: branch\n- [[b]] go\n  ::detour-badge{ref=d1}\n:::\n" + det + "# B\n")
    assert "LT034" in check("# A\n- item\n  ::include{file=x.md}\n")  # an include in a list item


# ---------------------------------------------------------------- columns that change width (spec 3.8, 3.15, 6.1)

def width_deck(deck, timeline: str, cols: str = "", extra: str = ""):
    """Two columns `l` and `r` (the second `2fr`), three fragments in `l`, a 5-frame walk `g` in `r`."""
    body = "\n".join("        " + line for line in timeline.strip().split("\n"))
    return deck({"talk.md": f"""
        # A
        ::: columns {cols}
        ::: column {{#l}}
        {{.reveal}}
        - one
        - two
        - three
        :::
        ::: column {{#r width=2fr}}
        ```graph-anim {{#g source="algos.py:walk"}}
        edges: ["A B", "B C", "C D", "D E"]
        ```
        :::
        :::
        {extra}
        ```timeline
{body}
        ```
    """, "algos.py": ALGOS})


def test_width_cues_make_the_columns_track(deck):
    root = width_deck(deck, "reveal 1\nwidth l=0\ng ..end\nwidth l=1fr r=1fr, reveal end\nwidth l=1fr r=2fr")
    s = build_deck(root, use_cache=False).slides["a"]
    assert [(t.id, t.kind, t.positions) for t in s.tracks] == [
        ("reveal", "reveal", 4), ("g", "component", 5), ("@columns", "columns", 3)]
    assert s.column_states == [{"l": "1 1 0", "r": "2 1 0"}, {"l": "0 0 0px", "r": "2 1 0"},
                               {"l": "1 1 0", "r": "1 1 0"}]
    # a width cue is one step alone, or part of the step of its line; a state seen before keeps its position
    assert columns(root, "reveal", "g", "@columns") == [
        (0, 0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 2, 1), (1, 3, 1), (1, 4, 1), (3, 4, 2), (3, 4, 0)]
    assert warnings(root) == []


def test_width_cues_in_lockstep_and_detour_steps(deck):
    root = width_deck(deck, "width r=300px, g ..+2\ndetour d\nwidth l=0px r=1fr\ng end, reveal end",
                      extra="::: detour {#d}\n        # Inside\n        :::")
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.column_states == [{"l": "1 1 0", "r": "2 1 0"}, {"l": "1 1 0", "r": "0 0 300px"},
                               {"l": "0 0 0px", "r": "1 1 0"}]
    # the width applies in the first cue of the line; a detour step copies the row before it
    assert columns(root, "g", "@columns") == [(0, 0), (1, 1), (2, 1), (2, 1), (2, 2), (4, 2)]
    assert s.step_detours == {3: {"id": "d", "blocking": False}}


def test_width_cue_that_changes_nothing(deck):
    root = width_deck(deck, "width r=2fr\ng end, reveal end")
    assert [c for c, _ in warnings(root)] == ["LT030"]
    root = width_deck(deck, "width l=0\nwidth l=0px\ng end, reveal end")  # every zero is the collapsed width
    assert [c for c, _ in warnings(root)] == ["LT030"]


@pytest.mark.parametrize("timeline", [
    "width",                      # names no column
    "width l",                    # no width
    "width l=wide",               # not a width
    "width l=1x",
    "width l=-1fr",
    "width l=0 l=1fr",            # twice in one cue
    "width l=0, width r=1fr",     # two width cues on one line
    "width nope=0",               # not a column
    "width g=0",                  # a component, not a column
    "width 2",                    # `width` is not a track name
])
def test_width_cue_errors(deck, timeline):
    root = width_deck(deck, timeline + "\ng end, reveal end")
    assert "LT064" in [c for c, _ in warnings(root)]


def test_width_errors_on_the_containers(deck):
    def check(src):
        root.write_text(src)
        return [c for c, _ in warnings(root)]

    root = deck({"talk.md": "# A\n"})
    assert check("# A\n::: columns\n::: column {width=auto}\nx\n:::\n:::\n") == ["LT064"]  # was silently ignored
    assert check("# A\n::: columns\n::: column {width=12}\nx\n:::\n:::\n") == ["LT064"]
    assert check("# A\n::: columns {duration=fast}\n::: column\nx\n:::\n:::\n") == ["LT064"]
    assert check("# A\n::: columns {duration=0}\n::: column {width=1.5fr}\nx\n:::\n::: column {width=0}\ny\n:::\n:::\n") == []
    # a column outside a `columns`, or in speaker notes, cannot be named by a width cue
    assert "LT064" in check("# A\n::: column {#x}\nx\n:::\n```timeline\nwidth x=0\n```\n")
    assert "LT064" in check("# A\n::: notes\n::: columns\n::: column {#x}\nx\n:::\n:::\n:::\n"
                            "```timeline\nwidth x=0\n```\n")
