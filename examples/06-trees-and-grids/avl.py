"""An AVL tree, as used in the lab, instrumented with an optional `see` callback."""
import inspect

from lattice import TreeTrace


class Node:
    def __init__(self, key):
        self.key = key
        self.left = self.right = None
        self.height = 1


def height(n):
    return n.height if n else 0


def balance(n):
    return height(n.left) - height(n.right) if n else 0


def update(n):
    n.height = 1 + max(height(n.left), height(n.right))


def rotate_right(y):
    x = y.left
    y.left, x.right = x.right, y
    update(y)
    update(x)
    return x


def rotate_left(x):
    y = x.right
    x.right, y.left = y.left, x
    update(x)
    update(y)
    return y


def insert(node, key, see=lambda event, key: None):
    if node is None:
        return Node(key)
    see("visit", node.key)
    if key < node.key:
        node.left = insert(node.left, key, see)
    else:
        node.right = insert(node.right, key, see)
    update(node)
    return rebalance(node, see)


def rebalance(node, see):
    b = balance(node)
    if b > 1:
        if balance(node.left) < 0:
            see("rotate-left", node.left.key)
            node.left = rotate_left(node.left)
        see("rotate-right", node.key)
        return rotate_right(node)
    if b < -1:
        if balance(node.right) > 0:
            see("rotate-right", node.right.key)
            node.right = rotate_right(node.right)
        see("rotate-left", node.key)
        return rotate_left(node)
    return node


# ---------------------------------------------------------------- traces for the slides

def _line(fragment, fn=insert):
    """Line number, within `fn`, of the first line containing `fragment` (for the code follower)."""
    for i, text in enumerate(inspect.getsource(fn).splitlines(), 1):
        if fragment in text:
            return i
    raise ValueError(fragment)


def _walk(n):
    if n:
        yield n
        yield from _walk(n.left)
        yield from _walk(n.right)


def avl_trace(values):
    """Insert `values` one by one; balance factors are shown next to each node."""
    t = TreeTrace()
    root = None

    def states(hot=None):
        hot = hot or {}
        return {n.key: {"state": hot.get(n.key, "default"), "label": f"{balance(n):+d}" if balance(n) else "0"}
                for n in _walk(root)}

    t.frame(root=None, caption="An empty AVL tree", meta={"line": 1})
    for key in values:
        def see(event, k):
            if event == "visit":
                t.frame(root=root, nodes=states({k: "active"}), caption=f"Insert {key}: compare with {k}",
                        meta={"line": _line("if key < node.key")})
            else:
                side = event.split("-")[1]
                t.frame(root=root, nodes=states({k: "error"}),
                        caption=f"Insert {key}: rotate {side} at {k} to restore the balance",
                        meta={"line": _line("return rebalance(node, see)")})
        root = insert(root, key, see)
        t.frame(root=root, nodes=states({key: "path"}), caption=f"{key} inserted, every balance factor in [-1, 1]",
                meta={"line": _line("return Node(key)")})
    t.frame(root=root, nodes=states(), caption="Height stays logarithmic", meta={"line": 1})
    return t


def rotation_trace():
    """A single right rotation on symbolic subtrees: the in-order sequence never changes."""
    t = TreeTrace()
    t.frame(root=("y", ("x", "T1", "T2"), "T3"), nodes={"y": "error"},
            caption="y leans left: its left subtree is two levels taller")
    t.frame(nodes={"x": "active", "y": "default"}, edges={("y", "x"): "active"},
            caption="x will become the root of this subtree")
    t.frame(root=("x", "T1", ("y", "T2", "T3")), nodes={"x": "path", "y": "path"},
            edges={("y", "x"): None, ("x", "y"): "active"},
            caption="T2 changes parent; the in-order sequence T1 x T2 y T3 is unchanged")
    return t
