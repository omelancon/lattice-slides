"""Animation traces and frame stores (spec section 9).

Authors describe each frame as a delta (only what changed). The build materializes
full states; above a size threshold it emits keyframes plus deltas instead.
"""
from __future__ import annotations

import copy
import json
from typing import Any

_MISSING = object()


def apply_delta(state: dict, delta: dict) -> dict:
    """Merge ``delta`` into a copy of ``state``: null removes, objects merge, the rest replaces."""
    out = dict(state)
    for key, val in delta.items():
        key = str(key)
        if val is None:
            out.pop(key, None)
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = apply_delta(out[key], val)
        else:
            out[key] = _normalize(val)
    return out


def _normalize(val):
    """JSON-friendly copy: dict keys become strings, tuples become lists."""
    if isinstance(val, dict):
        return {str(k): _normalize(v) for k, v in val.items() if v is not None}
    if isinstance(val, (list, tuple)):
        return [_normalize(v) for v in val]
    if isinstance(val, float) and val == float("inf"):
        return "\u221e"
    return val


def diff(old: dict, new: dict) -> dict:
    """The delta that turns ``old`` into ``new`` (inverse of :func:`apply_delta`)."""
    out: dict[str, Any] = {}
    for key in old.keys() - new.keys():
        out[key] = None
    for key, val in new.items():
        prev = old.get(key, _MISSING)
        if prev == val:
            continue
        if isinstance(val, dict) and isinstance(prev, dict):
            out[key] = diff(prev, val)
        else:
            out[key] = val
    return out


class Trace:
    """A generic trace. Each :meth:`frame` call appends one frame (one position).

    ``delta`` and keyword parts are merged into the persistent state. ``transient``
    values apply to this frame only (useful for highlights such as comparisons).
    """

    def __init__(self, base: dict | None = None):
        self.state: dict = _normalize(base or {})
        self.frames: list[dict] = []
        self.meta: list[dict] = []

    def frame(self, delta: dict | None = None, *, meta: dict | None = None,
              transient: dict | None = None, **parts) -> "Trace":
        d = dict(delta or {})
        d.update(parts)
        self.state = apply_delta(self.state, d)
        shown = apply_delta(self.state, transient) if transient else self.state
        self.frames.append(copy.deepcopy(shown))
        self.meta.append(dict(meta or {}))
        return self

    def __len__(self) -> int:
        return len(self.frames)

    def frame_store(self, max_full_bytes: int = 2 * 1024 * 1024, keyframe_interval: int = 16) -> dict:
        return frame_store(self.frames or [dict(self.state)], max_full_bytes, keyframe_interval)


def frame_store(frames: list[dict], max_full_bytes: int = 2 * 1024 * 1024, keyframe_interval: int = 16) -> dict:
    """Serialize materialized frames (spec 9.3): full states, or keyframes plus deltas above the threshold."""
    full = {"format": "full", "count": len(frames), "frames": frames}
    if len(json.dumps(full, separators=(",", ":"))) <= max_full_bytes:
        return full
    keyframes, deltas = [], []
    for i, f in enumerate(frames):
        if i % keyframe_interval == 0:
            keyframes.append(f)
            deltas.append(None)
        else:
            deltas.append(diff(frames[i - 1], f))
    return {"format": "keyframed", "count": len(frames), "interval": keyframe_interval,
            "keyframes": keyframes, "deltas": deltas}


def frames_of(store: dict) -> list[dict]:
    """The frames of a frame store (spec 9.3), full or keyframed, as full states."""
    if store.get("format") != "keyframed":
        return list(store.get("frames", []))
    out: list[dict] = []
    interval = store["interval"]
    for i in range(store["count"]):
        out.append(store["keyframes"][i // interval] if i % interval == 0 else apply_delta(out[-1], store["deltas"][i]))
    return out


class GraphTrace(Trace):
    """Trace over a graph. State: ``nodes``, ``edges``, ``panel``, ``caption``.

    ``nodes`` maps a node name to ``{"state": ..., "label": ...}``; ``edges`` maps
    ``"u->v"`` (directed) or ``"u--v"`` (undirected) to ``{"state": ..., "label": ...}``.
    """

    def __init__(self, graph=None, base: dict | None = None):
        super().__init__(base)
        self.graph = graph
        self.directed = bool(graph is not None and graph.is_directed())

    def edge(self, u, v) -> str:
        return f"{u}->{v}" if self.directed else f"{u}--{v}"

    def frame(self, delta: dict | None = None, *, nodes: dict | None = None, edges: dict | None = None,
              panel: dict | None = None, caption: str | None = None, meta: dict | None = None,
              transient: dict | None = None) -> "GraphTrace":
        d = dict(delta or {})
        if nodes:
            d["nodes"] = {str(k): (v if isinstance(v, dict) or v is None else {"state": v})
                          for k, v in nodes.items()}
        if edges:
            conv = {}
            for k, v in edges.items():
                key = self.edge(*k) if isinstance(k, tuple) else str(k)
                conv[key] = v if isinstance(v, dict) or v is None else {"state": v}
            d["edges"] = conv
        if panel is not None:
            d["panel"] = panel
        if caption is not None:
            d["caption"] = caption
        super().frame(d, meta=meta, transient=transient)
        return self

    def elements(self) -> tuple[set[str], set[str]]:
        """Node and edge keys appearing in any frame (for layout stability)."""
        ns, es = set(), set()
        for f in self.frames:
            ns.update(f.get("nodes", {}).keys())
            es.update(f.get("edges", {}).keys())
        return ns, es


class ArrayTrace(Trace):
    """Trace over an array. State: ``values``, ``cells``, ``marks``, ``pointers``, ``caption``, ``panel``.

    ``cells`` holds persistent per-index states (for example ``sorted``); ``marks``
    are transient per-frame highlights (for example ``compare`` or ``swap``).
    """

    def __init__(self, values: list | None = None):
        super().__init__({"values": list(values or [])})

    def frame(self, delta: dict | None = None, *, values: list | None = None, cells: dict | None = None,
              marks: dict | None = None, pointers: dict | None = None, caption: str | None = None,
              panel: dict | None = None, meta: dict | None = None) -> "ArrayTrace":
        d = dict(delta or {})
        if values is not None:
            d["values"] = list(values)
        if cells:
            d["cells"] = {str(k): v for k, v in cells.items()}
        if pointers is not None:
            d["pointers"] = pointers
        if caption is not None:
            d["caption"] = caption
        if panel is not None:
            d["panel"] = panel
        transient = {"marks": {str(k): v for k, v in (marks or {}).items()}}
        super().frame(d, meta=meta, transient=transient)
        return self


_KEEP = object()


def _get(obj, name):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _edge_key(k) -> str:
    return f"{k[0]}->{k[1]}" if isinstance(k, tuple) else str(k)


def _state(v):
    return v if isinstance(v, dict) or v is None else {"state": v}


class TreeTrace(Trace):
    """Trace over a rooted tree whose shape changes (insertions, deletions, rotations).

    State: ``tree`` (``{"root": id, "kids": {id: [child id or None, ...]}}``), ``nodes``, ``edges``,
    ``panel``, ``caption``. ``frame(root=...)`` takes a snapshot of the author's own node objects,
    read through ``key`` and ``children``:

    - ``key``: attribute or mapping key holding the node's name (or a callable ``node -> name``);
    - ``children``: a tuple of attributes read as fixed slots (``("left", "right")``, ``None`` allowed),
      one attribute holding a list of children (``"children"``), or a callable ``node -> children``.

    Tuples ``(name, child, child, ...)`` and bare scalars (leaves) are accepted as nodes too. Node names
    must be unique within a frame. Edge keys are ``"parent->child"``.
    """

    def __init__(self, root=None, *, key="key", children=("left", "right")):
        super().__init__({"tree": {"root": None, "kids": {}}})
        self.key = key
        self.children = children
        if root is not None:
            self.state["tree"] = self.snapshot(root)

    # -- reading the author's nodes
    def _name(self, node) -> str:
        if isinstance(node, (tuple, list)):
            return str(node[0])
        if isinstance(node, (str, int, float)):
            return str(node)
        name = self.key(node) if callable(self.key) else _get(node, self.key)
        if name is None:
            raise ValueError(f"TreeTrace: node {node!r} has no {self.key!r}")
        return str(name)

    def _kids(self, node) -> list:
        if isinstance(node, (tuple, list)):
            return list(node[1:])
        if isinstance(node, (str, int, float)):
            return []
        ch = self.children
        if callable(ch):
            return list(ch(node) or [])
        if isinstance(ch, str):
            return list(_get(node, ch) or [])
        return [_get(node, c) for c in ch]

    def snapshot(self, root) -> dict:
        """The shape of the tree rooted at ``root``, as stored in the ``tree`` part of a frame."""
        if root is None:
            return {"root": None, "kids": {}}
        kids: dict[str, list] = {}
        seen: set[str] = set()
        stack = [root]
        while stack:
            node = stack.pop()
            name = self._name(node)
            if name in seen:
                raise ValueError(f"TreeTrace: node {name!r} appears twice (duplicate name or cycle)")
            seen.add(name)
            children = self._kids(node)
            if any(c is not None for c in children):
                kids[name] = [None if c is None else self._name(c) for c in children]
                stack.extend(c for c in reversed(children) if c is not None)
        return {"root": self._name(root), "kids": kids}

    def frame(self, delta: dict | None = None, *, root=_KEEP, nodes: dict | None = None,
              edges: dict | None = None, panel: dict | None = None, caption: str | None = None,
              meta: dict | None = None, transient: dict | None = None) -> "TreeTrace":
        if root is not _KEEP:  # the shape is replaced as a whole, never merged
            self.state = {**self.state, "tree": self.snapshot(root)}
        d = dict(delta or {})
        if nodes:
            d["nodes"] = {str(k): _state(v) for k, v in nodes.items()}
        if edges:
            d["edges"] = {_edge_key(k): _state(v) for k, v in edges.items()}
        if panel is not None:
            d["panel"] = panel
        if caption is not None:
            d["caption"] = caption
        super().frame(d, meta=meta, transient=transient)
        return self


def _cell_key(k) -> str:
    if isinstance(k, (tuple, list)):
        return f"{int(k[0])},{int(k[1])}"
    return str(k)


class GridTrace(Trace):
    """Trace over a 2D grid (mazes, dynamic programming tables).

    State: ``values`` (list of rows), ``rows`` and ``cols`` (optional header labels), ``cells``
    (persistent per-cell states), ``marks`` (transient per-frame states), ``pointers`` (name to
    ``[row, col]``, ``None`` removes), ``arrows`` (``"r,c->r,c"`` to a state, for example DP
    backpointers), ``caption`` and ``panel``. Cell keys are ``(row, col)`` tuples or ``"r,c"`` strings.
    A string row is split into one cell per character.
    """

    def __init__(self, values: list | None = None, *, rows: list | None = None, cols: list | None = None):
        base: dict = {"values": [list(r) if isinstance(r, str) else list(r) for r in (values or [])]}
        if rows is not None:
            base["rows"] = list(rows)
        if cols is not None:
            base["cols"] = list(cols)
        super().__init__(base)

    def frame(self, delta: dict | None = None, *, values: list | None = None, put: dict | None = None,
              cells: dict | None = None, marks: dict | None = None, pointers: dict | None = None,
              arrows: dict | None = None, rows: list | None = None, cols: list | None = None,
              caption: str | None = None, panel: dict | None = None, meta: dict | None = None) -> "GridTrace":
        d = dict(delta or {})
        grid = [list(r) for r in (values if values is not None else self.state.get("values", []))]
        if put:
            for k, v in put.items():
                r, c = (int(x) for x in _cell_key(k).split(","))
                while len(grid) <= r:
                    grid.append([])
                while len(grid[r]) <= c:
                    grid[r].append(None)
                grid[r][c] = v
        if values is not None or put:
            d["values"] = grid
        if rows is not None:
            d["rows"] = list(rows)
        if cols is not None:
            d["cols"] = list(cols)
        if cells:
            d["cells"] = {_cell_key(k): v for k, v in cells.items()}
        if pointers:
            d["pointers"] = {str(k): (None if v is None else [int(v[0]), int(v[1])]) for k, v in pointers.items()}
        if arrows:
            d["arrows"] = {(f"{_cell_key(k[0])}->{_cell_key(k[1])}" if isinstance(k, tuple) else str(k)): v
                           for k, v in arrows.items()}
        if caption is not None:
            d["caption"] = caption
        if panel is not None:
            d["panel"] = panel
        transient = {"marks": {_cell_key(k): v for k, v in (marks or {}).items()}}
        super().frame(d, meta=meta, transient=transient)
        return self
