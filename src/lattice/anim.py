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
        frames = self.frames or [dict(self.state)]
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
