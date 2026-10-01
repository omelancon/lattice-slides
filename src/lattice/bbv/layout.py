"""Block bands: positions of versions per frame (plan section 3.4).

Every function is a column (``TB``) or a band (``LR``). Inside it, each origin block has a rank
(its row in ``TB``, its column in ``LR``), from a Graphviz layout of the source CFG when available;
the versions alive in a frame are packed along the rank, sorted by the block's order and their
creation id, and the rank is centred in the function's column or band. Node sizes come from the
text, so a version never resizes.
"""
from __future__ import annotations

CHAR_W = 7.4  # monospace advance at the code font size used by the runtime (13px)
LINE_H = 16.0
LABEL_H = 22.0
PAD_X = 10.0
PAD_Y = 6.0
GAP_ALONG = 22.0  # between versions of one rank
GAP_RANK = 44.0  # between ranks
GAP_LINE = 14.0  # between the lines of a wrapped rank
FUNCTION_GAP = 64.0  # leaves room for the lane of back edges beside each function
HEADER = 30.0
MARGIN = 30.0  # covers the 22 px by which back edges step out of their nodes (bbv.js), plus the arrowhead
LANE = 18.0  # distance of the back-edge lane from the function's extent


def node_size(version: dict, show: list[str]) -> tuple[float, float]:
    lines = []
    if "context" in show:
        lines += version["context"]
    if "code" in show:
        lines += [c["text"] for c in version["code"]] or ["…"]
    width = max([len(version["label"]) + 2] + [len(t) + (3 if i < len(version["context"]) and "context" in show else 0)
                                              for i, t in enumerate(lines)]) * CHAR_W + 2 * PAD_X
    height = LABEL_H + len(lines) * LINE_H + 2 * PAD_Y
    return round(width, 1), round(height, 1)


def block_ranks(function: dict, layout_fn=None) -> tuple[dict[str, int], dict[str, float]]:
    """Rank and order of every block of a function.

    ``layout_fn(graph) -> {"nodes": {name: {"x", "y"}}}`` is Graphviz through ``ctx.layout`` when the
    caller has it; otherwise ranks are longest paths from the entry over forward edges and the
    order is the declaration order.
    """
    blocks = function["blocks"]
    names = [b["name"] for b in blocks]
    succ = {b["name"]: [e["to"] for e in b["edges"]] for b in blocks}
    if layout_fn is not None:
        try:
            import networkx as nx

            g = nx.DiGraph()
            g.add_nodes_from(names)
            for b in blocks:
                for e in b["edges"]:
                    g.add_edge(b["name"], e["to"])
            lay = layout_fn(g)
            ys = sorted({round(n["y"]) for n in lay["nodes"].values()})
            ranks = {name: ys.index(round(lay["nodes"][name]["y"])) for name in names}
            order = {name: float(lay["nodes"][name]["x"]) for name in names}
            return ranks, order
        except Exception:  # noqa: BLE001 - fall back to the simple layering
            pass
    state: dict[str, int] = {}
    forward: dict[str, list[str]] = {n: [] for n in names}

    def dfs(n: str) -> None:
        state[n] = 1
        for m in succ[n]:
            if state.get(m, 0) == 0:
                forward[n].append(m)
                dfs(m)
            elif state[m] == 2:
                forward[n].append(m)
        state[n] = 2

    dfs(names[0])
    for n in names:
        if state.get(n, 0) == 0:
            dfs(n)
    ranks = {n: 0 for n in names}
    changed = True
    while changed:
        changed = False
        for n in names:
            for m in forward[n]:
                if ranks[m] < ranks[n] + 1:
                    ranks[m] = ranks[n] + 1
                    changed = True
    return ranks, {n: float(i) for i, n in enumerate(names)}


def _lines(ids: list[str], wrap: int, block_of) -> list[list[str]]:
    """Split the versions of a rank into lines of at most ``wrap``; the versions of one block stay
    together when they fit on a line."""
    if wrap <= 0 or len(ids) <= wrap:
        return [ids]
    groups: list[list[str]] = []
    for i in ids:
        if groups and block_of(groups[-1][-1]) == block_of(i):
            groups[-1].append(i)
        else:
            groups.append([i])
    chunks: list[list[str]] = []
    for g in groups:
        chunks += [g[k:k + wrap] for k in range(0, len(g), wrap)]
    lines: list[list[str]] = [[]]
    for c in chunks:
        if lines[-1] and len(lines[-1]) + len(c) > wrap:
            lines.append([])
        lines[-1].extend(c)
    return lines


def layout_frames(tables: dict, frames: list[dict], show: list[str], layout_fn=None,
                  direction: str = "TB", wrap: int = 4) -> tuple[dict, list[dict]]:
    """Positions for every frame. Returns ``(box, positions)``: ``box`` describes the drawing (``width``,
    ``height``, ``direction``, function headers, node sizes) and ``positions[i]`` maps version ids to
    the top left corner ``[x, y]``. Versions marked ``gone`` keep the position of the previous frame."""
    tb = direction != "LR"
    versions = tables["versions"]
    sizes = {vid: node_size(v, show) for vid, v in versions.items()}
    # ``along`` is the extent along a rank (x in TB), ``across`` the extent between ranks (y in TB)
    along = {vid: (s[0] if tb else s[1]) for vid, s in sizes.items()}
    across = {vid: (s[1] if tb else s[0]) for vid, s in sizes.items()}
    functions = tables["program"]["functions"]
    ranks: dict[str, dict[str, int]] = {}
    order: dict[str, dict[str, float]] = {}
    for fn in functions:
        r, o = block_ranks(fn, layout_fn)
        ranks[fn["name"]] = r
        order[fn["name"]] = o
    # rows per frame: the live versions of each rank, in lines of at most ``wrap`` versions
    rows_per_frame: list[dict[str, dict[int, list[list[str]]]]] = []
    fn_along: dict[str, float] = {fn["name"]: (max(len(fn["name"]) * 9.0, 60.0) if tb else 60.0) for fn in functions}
    rank_ext: dict[str, dict[int, float]] = {fn["name"]: {} for fn in functions}
    for vid, v in versions.items():  # a version alone on its rank sets the minimum extent
        re_ = rank_ext[v["function"]]
        rank = ranks[v["function"]][v["name"]]
        re_[rank] = max(re_.get(rank, 0.0), across[vid])
    for f in frames:
        rows: dict[str, dict[int, list[str]]] = {fn["name"]: {} for fn in functions}
        for vid, n in f["nodes"].items():
            if n.get("mark") == "gone":
                continue
            v = versions[vid]
            rows[v["function"]].setdefault(ranks[v["function"]][v["name"]], []).append(vid)
        wrapped: dict[str, dict[int, list[list[str]]]] = {}
        for name, byrank in rows.items():
            wrapped[name] = {}
            for rank, ids in byrank.items():
                ids.sort(key=lambda i: (order[name][versions[i]["name"]], int(i)))
                lines = _lines(ids, wrap, lambda i: versions[i]["name"])
                wrapped[name][rank] = lines
                for line in lines:
                    fn_along[name] = max(fn_along[name], sum(along[i] for i in line) + GAP_ALONG * (len(line) - 1))
                ext = sum(max(across[i] for i in line) for line in lines) + GAP_LINE * (len(lines) - 1)
                rank_ext[name][rank] = max(rank_ext[name][rank], ext)
        rows_per_frame.append(wrapped)
    rank_at: dict[str, dict[int, float]] = {}
    fn_across: dict[str, float] = {}
    header = HEADER if tb else 0.0
    for fn in functions:
        c = MARGIN + header
        rank_at[fn["name"]] = {}
        for rank in sorted(set(ranks[fn["name"]].values())):
            rank_at[fn["name"]][rank] = c
            c += rank_ext[fn["name"]].get(rank, LABEL_H) + GAP_RANK
        fn_across[fn["name"]] = c - GAP_RANK + MARGIN + LANE  # back edges leave below the last rank
    fn_start: dict[str, float] = {}
    a = MARGIN
    for fn in functions:
        if not tb:
            a += HEADER  # the function name sits above its band
        fn_start[fn["name"]] = a
        a += fn_along[fn["name"]] + FUNCTION_GAP
    total_along = a - FUNCTION_GAP + MARGIN + LANE + 10
    total_across = max(fn_across.values()) if fn_across else 2 * MARGIN
    positions: list[dict[str, list[float]]] = []
    prev: dict[str, list[float]] = {}
    for f, rows in zip(frames, rows_per_frame):
        pos: dict[str, list[float]] = {}
        for name, byrank in rows.items():
            for rank, lines in byrank.items():
                q = rank_at[name][rank]
                for line in lines:
                    row_len = sum(along[i] for i in line) + GAP_ALONG * (len(line) - 1)
                    p = fn_start[name] + (fn_along[name] - row_len) / 2
                    for i in line:
                        pos[i] = [round(p, 1), round(q, 1)] if tb else [round(q, 1), round(p, 1)]
                        p += along[i] + GAP_ALONG
                    q += max(across[i] for i in line) + GAP_LINE
        for vid, n in f["nodes"].items():
            if n.get("mark") == "gone" and vid in prev:
                pos[vid] = prev[vid]
        positions.append(pos)
        prev = {k: v for k, v in pos.items() if f["nodes"].get(k, {}).get("mark") != "gone"}
    headers = {}
    bands = {}
    for fn in functions:
        n = fn["name"]
        if tb:
            headers[n] = {"x": round(fn_start[n] + fn_along[n] / 2, 1), "y": round(MARGIN + HEADER / 2, 1), "anchor": "middle"}
        else:
            headers[n] = {"x": round(MARGIN, 1), "y": round(fn_start[n] - 10, 1), "anchor": "start"}
        # the extent of the function along the packing axis, and the lane where its back edges travel
        bands[n] = {"start": round(fn_start[n], 1), "end": round(fn_start[n] + fn_along[n], 1),
                    "lane": round(fn_start[n] + fn_along[n] + LANE, 1)}
    box = {"width": round(total_along if tb else total_across, 1), "height": round(total_across if tb else total_along, 1),
           "direction": "TB" if tb else "LR", "headers": headers, "bands": bands,
           "sizes": {vid: list(s) for vid, s in sizes.items()}}
    return box, positions
