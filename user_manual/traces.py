"""Trace functions for the animations of the user manual. Every function receives the block's
``source`` argument first (a graph or ``values``) and the block's other options as keywords, and
returns a trace whose frames the deck replays; ``meta`` lines let a ``code`` block follow along."""
from collections import deque

from lattice import ArrayTrace, GraphTrace, GridTrace, TreeTrace


# ------------------------------------------------------------------ graph-anim

def bfs_trace(g, start="A"):
    """Breadth-first search: nodes are labelled with their layer, tree edges stay highlighted."""
    t = GraphTrace(g)
    level = {start: 0}
    queue = deque([start])
    t.frame(nodes={start: {"state": "frontier", "label": 0}}, panel={"queue": list(queue)},
            caption=f"Start at {start}", meta={"line": 2})
    while queue:
        u = queue.popleft()
        t.frame(nodes={u: "active"}, panel={"queue": list(queue)}, caption=f"Visit {u}", meta={"line": 4})
        for v in sorted(g[u]):
            if v not in level:
                level[v] = level[u] + 1
                queue.append(v)
                t.frame(nodes={v: {"state": "frontier", "label": level[v]}}, edges={(u, v): "tree"},
                        panel={"queue": list(queue)}, caption=f"Discover {v} in layer {level[v]}",
                        meta={"lines": [6, 7, 8]})
        t.frame(nodes={u: "visited"}, panel={"queue": list(queue)}, caption=f"{u} is done", meta={"line": 4})
    t.frame(caption="Every node carries its distance in edges from " + start, meta={"line": 9})
    return t


# ------------------------------------------------------------------ array-anim

def bubble_trace(values):
    """One pass of bubble sort per outer iteration; marks are per frame, cells persist."""
    a = list(values)
    t = ArrayTrace(a)
    t.frame(caption="Unsorted input")
    for end in range(len(a) - 1, 0, -1):
        for i in range(end):
            t.frame(marks={i: "compare", i + 1: "compare"}, pointers={"i": i}, caption=f"Compare {a[i]} and {a[i + 1]}")
            if a[i] > a[i + 1]:
                a[i], a[i + 1] = a[i + 1], a[i]
                t.frame(values=a, marks={i: "swap", i + 1: "swap"}, pointers={"i": i}, caption="Swap")
        t.frame(cells={end: "sorted"}, pointers={"i": None}, caption=f"{a[end]} is in its final place")
    t.frame(cells={k: "sorted" for k in range(len(a))}, caption="Sorted")
    return t


# ------------------------------------------------------------------ tree-anim

class Node:
    def __init__(self, key):
        self.key, self.left, self.right = key, None, None


def insert(node, key, see=lambda k: None):
    if node is None:
        return Node(key)
    see(node.key)
    if key < node.key:
        node.left = insert(node.left, key, see)
    else:
        node.right = insert(node.right, key, see)
    return node


def bst_trace(values):
    """Insertions into a plain binary search tree, traced from the tree's own ``Node`` objects."""
    t = TreeTrace()  # key="key", children=("left", "right") are the defaults
    root = None
    t.frame(root=None, caption="An empty tree")
    for key in values:
        visited = []

        def see(k):
            visited.append(k)
            t.frame(root=root, nodes={k: "active"}, caption=f"Insert {key}: compare with {k}")

        root = insert(root, key, see)
        t.frame(root=root, nodes={**{k: "default" for k in visited}, key: "path"}, caption=f"{key} inserted")
    t.frame(root=root, nodes={}, caption="In-order traversal gives the keys sorted")
    return t


def rotation_trace():
    """A right rotation on symbolic subtrees, written as tuples: no node objects needed."""
    t = TreeTrace()
    t.frame(root=("y", ("x", "T1", "T2"), "T3"), nodes={"y": "error"}, caption="y leans left")
    t.frame(root=("x", "T1", ("y", "T2", "T3")), nodes={"x": "path", "y": "path"},
            caption="x is the new root of the subtree; the in-order sequence is unchanged")
    return t


# ------------------------------------------------------------------ grid-anim

def lcs_trace(a="ABCB", b="BDCAB"):
    """Fills the longest-common-subsequence table; arrows remember where each value came from."""
    n, m = len(a), len(b)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    grid = [[0 if i == 0 or j == 0 else None for j in range(m + 1)] for i in range(n + 1)]
    t = GridTrace(grid, rows=["", *a], cols=["", *b])
    t.frame(caption="Row 0 and column 0 are 0")
    back = {}
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                L[i][j], src, why = L[i - 1][j - 1] + 1, (i - 1, j - 1), f"{a[i - 1]} = {b[j - 1]}: diagonal + 1"
            elif L[i - 1][j] >= L[i][j - 1]:
                L[i][j], src, why = L[i - 1][j], (i - 1, j), "max comes from above"
            else:
                L[i][j], src, why = L[i][j - 1], (i, j - 1), "max comes from the left"
            back[(i, j)] = src
            t.frame(put={(i, j): L[i][j]}, cells={(i, j): "visited"}, marks={(i, j): "active", src: "compare"},
                    arrows={((i, j), src): "active"}, caption=why)
    i, j, path = n, m, []
    while i and j:
        path.append((i, j))
        i, j = back[(i, j)]
    t.frame(arrows={(p, back[p]): "path" for p in path}, cells={p: "path" for p in path},
            caption=f"Follow the arrows back from the corner: length {L[n][m]}")
    return t


# ------------------------------------------------------------------ plot

def running_times(ax):
    """A matplotlib plot source: draws on the axes Lattice provides (a `data` argument would receive
    the CSV columns of the block's `data` option)."""
    sizes = [2 ** k for k in range(1, 11)]
    ax.plot(sizes, [s * s.bit_length() for s in sizes], marker="o", label="n log n")
    ax.plot(sizes, [s * s for s in sizes], marker="s", label="n squared")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("n")
    ax.set_ylabel("operations")
    ax.legend()
