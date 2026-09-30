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
    root.write_text("# A\n```timeline\narr 0..1, b 0..1\n```\n")
    assert "LT031" in codes(check_deck(root, use_cache=False))


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
