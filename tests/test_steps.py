from lattice.anim import ArrayTrace, GraphTrace, Trace, apply_delta, diff
from lattice.build import build_deck, check_deck

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
