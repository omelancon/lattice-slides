"""Graph loading and stable layout (spec 8.3 load_graph / layout, 9.4)."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import networkx as nx

from .components.base import ComponentError

_INTERNAL = {"_draw_", "_ldraw_", "_hdraw_", "_tdraw_", "_hldraw_", "_tldraw_", "pos", "width", "height",
             "_gvid", "lp", "head", "tail", "bb", "xlp", "nodes", "edges", "objects", "subgraphs",
             "directed", "strict", "name"}


def has_graphviz() -> bool:
    return shutil.which("dot") is not None


def _num(v):
    if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v.strip()):
        return float(v) if "." in v else int(v)
    return v


def _run_graphviz(source: str, engine: str, fmt: str) -> str:
    if not has_graphviz():
        raise ComponentError("Graphviz is required (the 'dot' program was not found on PATH)")
    proc = subprocess.run([engine if engine != "dot" else "dot", f"-T{fmt}"], input=source,
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise ComponentError(f"graphviz failed: {proc.stderr.strip()}")
    return proc.stdout


def load_graph(path: Path) -> nx.Graph:
    suffix = path.suffix.lower()
    if suffix in (".dot", ".gv"):
        data = json.loads(_run_graphviz(path.read_text(encoding="utf-8"), "dot", "json"))
        g = nx.DiGraph() if data.get("directed") else nx.Graph()
        names = {}
        for obj in data.get("objects", []):
            if "nodes" in obj or "subgraphs" in obj and "pos" not in obj:
                continue
            names[obj["_gvid"]] = obj["name"]
            g.add_node(obj["name"], **{k: _num(v) for k, v in obj.items() if k not in _INTERNAL})
        for e in data.get("edges", []):
            attrs = {k: _num(v) for k, v in e.items() if k not in _INTERNAL}
            if "weight" not in attrs and isinstance(attrs.get("label"), (int, float)):
                attrs["weight"] = attrs["label"]
            g.add_edge(names[e["tail"]], names[e["head"]], **attrs)
        return g
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return nx.node_link_graph(data, edges="links" if "links" in data else "edges")
    if suffix == ".gml":
        return nx.read_gml(path)
    raise ComponentError(f"unsupported graph format: {path.name}")


def graph_from_edges(edges: list, directed: bool) -> nx.Graph:
    """Build a graph from lines like ``"A B 4"`` (weight optional) or ``"A"`` (lone node)."""
    g = nx.DiGraph() if directed else nx.Graph()
    for item in edges:
        parts = str(item).split()
        if len(parts) == 1:
            g.add_node(parts[0])
        elif len(parts) in (2, 3):
            attrs = {"weight": _num(parts[2])} if len(parts) == 3 else {}
            g.add_edge(parts[0], parts[1], **attrs)
        else:
            raise ComponentError(f"cannot parse edge {item!r}; expected 'u v [weight]'")
    return g


def edge_key(u, v, directed: bool) -> str:
    return f"{u}->{v}" if directed else f"{u}--{v}"


def _q(x) -> str:
    return '"' + str(x).replace('"', '\\"') + '"'


def _parse_points(pos: str):
    pos = pos.split(";")[0]
    start = end = None
    pts = []
    for tok in pos.split():
        if tok.startswith("e,"):
            x, y = tok[2:].split(",")
            end = (float(x), float(y))
        elif tok.startswith("s,"):
            x, y = tok[2:].split(",")
            start = (float(x), float(y))
        else:
            x, y = tok.split(",")
            pts.append((float(x), float(y)))
    return start, pts, end


def layout(g: nx.Graph, engine: str = "auto", seed: int = 0, rankdir: str = "LR",
           edge_labels: bool | None = None, node_size: float = 0.55) -> dict:
    """Compute a stable layout. Coordinates are in points, y pointing down."""
    directed = g.is_directed()
    if engine == "auto":
        engine = "dot"
    if edge_labels is None:
        edge_labels = any("weight" in d for _, _, d in g.edges(data=True))
    if has_graphviz():
        return _graphviz_layout(g, engine, rankdir, edge_labels, node_size)
    return _fallback_layout(g, seed, edge_labels, node_size)


def _graphviz_layout(g, engine, rankdir, edge_labels, node_size) -> dict:
    directed = g.is_directed()
    arrow = "->" if directed else "--"
    lines = ["digraph G {" if directed else "graph G {",
             f"graph [rankdir={rankdir}, nodesep=0.45, ranksep=0.7, overlap=false, splines=true, sep=\"+12\"];",
             f"node [shape=circle, fixedsize=true, width={node_size}, fontsize=14];",
             "edge [fontsize=13];"]
    for n in g.nodes:
        lines.append(f"{_q(n)};")
    for u, v, d in g.edges(data=True):
        lab = f' [label={_q(d["weight"])}]' if edge_labels and "weight" in d else ""
        lines.append(f"{_q(u)} {arrow} {_q(v)}{lab};")
    lines.append("}")
    data = json.loads(_run_graphviz("\n".join(lines), engine, "json"))
    x0, y0, x1, y1 = (float(v) for v in data["bb"].split(","))
    pad = 26.0
    width, height = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad

    def tr(p):
        return round(p[0] - x0 + pad, 2), round(y1 - p[1] + pad, 2)

    nodes, names = {}, {}
    for obj in data.get("objects", []):
        if "pos" not in obj:
            continue
        names[obj["_gvid"]] = obj["name"]
        x, y = tr(tuple(float(v) for v in obj["pos"].split(",")))
        nodes[obj["name"]] = {"x": x, "y": y, "r": round(float(obj.get("width", node_size)) * 36, 2)}
    edges = {}
    for e in data.get("edges", []):
        u, v = names[e["tail"]], names[e["head"]]
        start, pts, end = _parse_points(e["pos"])
        pts = [tr(p) for p in pts]
        d = f"M{pts[0][0]},{pts[0][1]}"
        for i in range(1, len(pts) - 2, 3):
            d += f" C{pts[i][0]},{pts[i][1]} {pts[i+1][0]},{pts[i+1][1]} {pts[i+2][0]},{pts[i+2][1]}"
        if end is not None:
            ex, ey = tr(end)
            d += f" L{ex},{ey}"
        entry = {"u": u, "v": v, "path": d}
        if "lp" in e:
            lx, ly = tr(tuple(float(t) for t in e["lp"].split(",")))
            entry.update(label=str(e.get("label", "")), lx=lx, ly=ly)
        edges[edge_key(u, v, directed)] = entry
    return {"width": round(width, 2), "height": round(height, 2), "directed": directed,
            "nodes": nodes, "edges": edges}


def _fallback_layout(g, seed, edge_labels, node_size) -> dict:
    directed = g.is_directed()
    pos = nx.spring_layout(g, seed=seed % (2**32)) if len(g) else {}
    r = node_size * 36
    scale, pad = 260.0, r + 12
    xs = [p[0] for p in pos.values()] or [0]
    ys = [p[1] for p in pos.values()] or [0]
    minx, miny = min(xs), min(ys)
    nodes = {n: {"x": round((p[0] - minx) * scale + pad, 2), "y": round((p[1] - miny) * scale + pad, 2),
                 "r": r} for n, p in pos.items()}
    edges = {}
    for u, v, d in g.edges(data=True):
        a, b = nodes[u], nodes[v]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        dist = math.hypot(dx, dy) or 1.0
        sx, sy = a["x"] + dx / dist * r, a["y"] + dy / dist * r
        ex, ey = b["x"] - dx / dist * r, b["y"] - dy / dist * r
        entry = {"u": u, "v": v, "path": f"M{sx:.2f},{sy:.2f} L{ex:.2f},{ey:.2f}"}
        if edge_labels and "weight" in d:
            entry.update(label=str(d["weight"]), lx=round((a["x"] + b["x"]) / 2, 2),
                         ly=round((a["y"] + b["y"]) / 2 - 6, 2))
        edges[edge_key(u, v, directed)] = entry
    width = (max(xs) - minx) * scale + 2 * pad
    height = (max(ys) - miny) * scale + 2 * pad
    return {"width": round(width, 2), "height": round(height, 2), "directed": directed,
            "nodes": nodes, "edges": edges}


def dot_to_svg(source: str, engine: str = "dot") -> str:
    svg = _run_graphviz(source, engine, "svg")
    svg = svg[svg.find("<svg"):]
    svg = re.sub(r'\swidth="[^"]*"', "", svg, count=1)
    svg = re.sub(r'\sheight="[^"]*"', "", svg, count=1)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r"<title>.*?</title>", "", svg, flags=re.S)
    svg = re.sub(r'(<g id="graph0"[^>]*>\s*<polygon )fill="white"', r'\1fill="none"', svg, count=1)
    svg = svg.replace('stroke="black"', 'stroke="currentColor"').replace('fill="black"', 'fill="currentColor"')
    svg = svg.replace('font-family="Times,serif"', 'font-family="inherit"')
    return svg


def overview_layout(deck) -> dict:
    """Layout of the slide graph for the overview map. Empty when Graphviz is missing."""
    if not has_graphviz() or not deck.slides:
        return {"nodes": {}, "edges": [], "width": 0, "height": 0}
    main = set(deck.main_path)
    lines = ["digraph deck {",
             'graph [rankdir=LR, nodesep=0.22, ranksep=0.42, splines=true];',
             'node [shape=box, style=rounded, fontsize=11, height=0.36, margin="0.12,0.05"];',
             "edge [arrowsize=0.6];"]
    for s in deck.slides.values():
        label = s.title_text if len(s.title_text) <= 26 else s.title_text[:25] + "\u2026"
        group = ', group="main"' if s.id in main else ""
        lines.append(f"{_q(s.id)} [label={_q(label)}{group}];")
    attrs = {"next": "[weight=6]", "branch": "[weight=2]", "detour": "[weight=1]",
             "link": "[constraint=false, weight=0]"}
    for e in deck.edges:
        lines.append(f"{_q(e.source)} -> {_q(e.target)} {attrs[e.kind]};")
    # off-path slides sit after the end of the main path instead of drifting to the left
    if deck.main_path:
        anchor = deck.main_path[-1]
        for s in deck.slides.values():
            if s.offpath and s.scope is None:
                lines.append(f"{_q(anchor)} -> {_q(s.id)} [style=invis, weight=0];")
    lines.append("}")
    data = json.loads(_run_graphviz("\n".join(lines), "dot", "json"))
    x0, y0, x1, y1 = (float(v) for v in data["bb"].split(","))
    pad = 8.0

    def tr(p):
        return round(p[0] - x0 + pad, 1), round(y1 - p[1] + pad, 1)

    nodes, names = {}, {}
    for obj in data.get("objects", []):
        if "pos" not in obj:
            continue
        names[obj["_gvid"]] = obj["name"]
        x, y = tr(tuple(float(v) for v in obj["pos"].split(",")))
        nodes[obj["name"]] = {"x": x, "y": y, "w": round(float(obj["width"]) * 72, 1),
                              "h": round(float(obj["height"]) * 72, 1), "label": obj.get("label", obj["name"])}
    edges = []
    kinds: dict[tuple[str, str], list[str]] = {}
    for e in deck.edges:
        kinds.setdefault((e.source, e.target), []).append(e.kind)
    for e in data.get("edges", []):
        if e.get("style") == "invis":
            continue
        _, pts, end = _parse_points(e["pos"])
        pts = [tr(p) for p in pts]
        d = f"M{pts[0][0]},{pts[0][1]}"
        for k in range(1, len(pts) - 2, 3):
            d += f" C{pts[k][0]},{pts[k][1]} {pts[k+1][0]},{pts[k+1][1]} {pts[k+2][0]},{pts[k+2][1]}"
        if end is not None:
            ex, ey = tr(end)
            d += f" L{ex},{ey}"
        pair = (names[e["tail"]], names[e["head"]])
        kind = kinds[pair].pop(0) if kinds.get(pair) else "next"
        edges.append({"from": pair[0], "to": pair[1], "kind": kind, "path": d})
    return {"nodes": nodes, "edges": edges, "width": round(x1 - x0 + 2 * pad, 1),
            "height": round(y1 - y0 + 2 * pad, 1)}


def tree_positions(tree: dict, binary: bool) -> dict[str, tuple[float, int]]:
    """Abstract positions ``name -> (x, depth)`` of one tree shape, x in node slots.

    ``binary``: in-order rank, so a rotation keeps every node's x and only changes depths. Otherwise a
    tidy layout: leaves take consecutive slots and a parent is centered over its children.
    """
    kids = tree.get("kids", {})
    root = tree.get("root")
    out: dict[str, tuple[float, int]] = {}
    if root is None:
        return out
    counter = [0]

    def inorder(n: str, depth: int) -> None:
        ch = kids.get(n, [])
        left, right = (ch[0] if ch else None), [c for c in ch[1:] if c is not None]
        if left is not None:
            inorder(left, depth + 1)
        out[n] = (counter[0], depth)
        counter[0] += 1
        for c in right:
            inorder(c, depth + 1)

    def tidy(n: str, depth: int) -> float:
        ch = [c for c in kids.get(n, []) if c is not None]
        if not ch:
            x = counter[0]
            counter[0] += 1
        else:
            xs = [tidy(c, depth + 1) for c in ch]
            x = (xs[0] + xs[-1]) / 2
        out[n] = (x, depth)
        return x

    (inorder if binary else tidy)(root, 0)
    return out


def tree_layouts(trees: list[dict], mode: str = "auto", dx: float = 64, dy: float = 78,
                 r: float = 21) -> tuple[dict, list[dict]]:
    """Positions for every frame, in points, in one shared box (spec 9.4).

    Returns ``(size, positions)``: ``size`` is ``{"width", "height", "r"}``; ``positions[i]`` maps each
    node of frame ``i`` to ``[x, y]``. Each frame is centered horizontally in the box.
    """
    binary = mode == "binary" or (mode == "auto" and all(
        len(k) in (0, 2) for t in trees for k in t.get("kids", {}).values()))
    abstract = [tree_positions(t, binary) for t in trees]
    span = max((max(x for x, _ in p.values()) for p in abstract if p), default=0)
    depth = max((max(d for _, d in p.values()) for p in abstract if p), default=0)
    pad = r + 16
    width, height = span * dx + 2 * pad, depth * dy + 2 * pad
    positions = []
    for p in abstract:
        if not p:
            positions.append({})
            continue
        lo, hi = min(x for x, _ in p.values()), max(x for x, _ in p.values())
        off = pad + ((span - (hi - lo)) * dx) / 2 - lo * dx
        positions.append({n: [round(off + x * dx, 1), round(pad + d * dy, 1)] for n, (x, d) in p.items()})
    return {"width": round(width, 1), "height": round(height, 1), "r": r}, positions
