"""Block bands: positions of versions per frame (spec 9.5).

Every function is a column (``TB``) or a band (``LR``), or with ``rank_wrap`` several of them (bands of
ranks: consecutive ranks cut into groups laid side by side, the cut computed once for the run). Inside it, each origin block has a rank
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


def context_width(lines: list[str]) -> int:
    """Characters of the widest drawn context line: ``;; `` then the names padded to the longest one
    (so that the types line up, as bbv.js draws them), then the longest type."""
    names, types = [], []
    for line in lines:
        name, sep, text = line.partition(": ")
        names.append(len(name) if sep else len(line) - 1)
        types.append(len(text) if sep else 0)
    return 3 + max(names, default=0) + 2 + max(types, default=0) if lines else 0


AFTER_HEAD = ";; after:"  # the line above the exit context of an enlarged block (bbv.js draws the same text)


def node_size(version: dict, show: list[str]) -> tuple[float, float]:
    """Size of a node drawing ``show`` (among ``label``, ``context``, ``code`` and, for an enlarged
    block, ``after``: the exit context under a heading line). The label is always drawn."""
    widths = [len(version["label"]) + 2]
    count = 0
    if "context" in show:
        widths.append(context_width(version["context"]))
        count += len(version["context"])
    if "code" in show:
        code = [c["text"] for c in version["code"]] or ["…"]
        widths += [len(t) for t in code]
        count += len(code)
    after = version.get("after") or []
    if "after" in show and after:
        widths += [len(AFTER_HEAD), context_width(after)]
        count += 1 + len(after)
    width = max(widths) * CHAR_W + 2 * PAD_X
    height = LABEL_H + count * LINE_H + 2 * PAD_Y
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


# ---------------------------------------------------------------- bands of ranks (spec 9.5)
BAND_GAP = 48.0  # least gap between two bands of a function (less than FUNCTION_GAP: they read as one function)
GUTTER_FIRST = 28.0  # first lane of a gutter, from the end of the band before it (its back-edge lane is at LANE)
GUTTER_STEP = 5.0  # between two lanes of a gutter
GUTTER_CLEAR = 14.0  # from the last lane to the band after it
GUTTER_LANES = 5  # most lanes in a gutter; beyond, the targets closest to each other share one (bbv.js)
AUTO_MAX = 6  # `auto` tries 1 to this many bands
AUTO_CAP = 1.4  # the most the runtime enlarges a drawing (bbv.js: max-width of the SVG)
AUTO_TIE = 0.02  # within this fraction of the largest scale, fewer bands win
END_GAP = 0.6  # the gutters past the ends of the ranks, in GAP_RANK from the first and last ranks


def gutter_gap(lanes: int) -> float:
    """Width of the gap between two bands whose gutter has ``lanes`` lanes."""
    return max(BAND_GAP, GUTTER_FIRST + GUTTER_STEP * (max(lanes, 1) - 1) + GUTTER_CLEAR)


def band_length(exts: list[float]) -> float:
    return sum(exts) + GAP_RANK * (len(exts) - 1) if exts else 0.0


def cut_ranks(exts: list[float], n: int) -> list[int]:
    """Cut the ranks (their extents across, in rank order) into ``n`` groups of consecutive ranks: the
    longest group as short as possible, then the lengths as even as possible (least sum of squares).
    Returns the index of the first rank of each group."""
    count = len(exts)
    n = max(1, min(n, count))
    if n == 1:
        return [0]
    pre = [0.0]
    for e in exts:
        pre.append(pre[-1] + e)

    def length(i: int, j: int) -> float:  # ranks i..j-1
        return pre[j] - pre[i] + GAP_RANK * (j - i - 1)

    inf = float("inf")
    # longest[k][i]: the least longest band when ranks i.. are cut into k groups
    longest = [[inf] * (count + 1) for _ in range(n + 1)]
    longest[0][count] = 0.0
    for k in range(1, n + 1):
        for i in range(count - k, -1, -1):
            longest[k][i] = min(max(length(i, j), longest[k - 1][j]) for j in range(i + 1, count - k + 2))
    bound = longest[n][0] + 1e-6
    # then the least sum of squares with every group within that bound
    best = [[inf] * (count + 1) for _ in range(n + 1)]
    nxt = [[0] * (count + 1) for _ in range(n + 1)]
    best[0][count] = 0.0
    for k in range(1, n + 1):
        for i in range(count - k, -1, -1):
            for j in range(i + 1, count - k + 2):
                ln = length(i, j)
                if ln > bound or best[k - 1][j] == inf:
                    continue
                v = ln * ln + best[k - 1][j]
                if v < best[k][i] - 1e-9:
                    best[k][i], nxt[k][i] = v, j
    starts, i = [], 0
    for k in range(n, 0, -1):
        starts.append(i)
        i = nxt[k][i]
    return starts


def _bands_of(starts: list[int], count: int) -> list[int]:
    """The band of each rank index, from the first rank of each band."""
    out = []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else count
        out += [k] * (end - s)
    return out


def _gutter_lanes(crossings: list[set], band: list[int], n: int) -> list[int]:
    """Lanes of each gutter (between bands k and k+1): the most targets it serves in a frame, capped."""
    lanes = [0] * max(n - 1, 0)
    for edges in crossings:
        per: list[set] = [set() for _ in range(n - 1)]
        for a, b, target in edges:
            ba, bb = band[a], band[b]
            if ba == bb:
                continue
            exit_, entry = (ba, bb - 1) if bb > ba else (ba - 1, bb)  # forward edges use the gutter after their band
            per[exit_].add(target)
            per[entry].add(target)
        for g, t in enumerate(per):
            lanes[g] = max(lanes[g], min(len(t), GUTTER_LANES))
    return lanes


def layout_frames(tables: dict, frames: list[dict], show: list[str], layout_fn=None,
                  direction: str = "TB", wrap: int = 4, rank_wrap: int | str = 1, rank_wraps: dict | None = None,
                  rank_flow: str = "restart", fit: tuple[float, float] | None = None, cuts: dict | None = None,
                  call_edges: bool = False, notes: list | None = None) -> tuple[dict, list[dict]]:
    """Positions for every frame. Returns ``(box, positions)``: ``box`` describes the drawing (``width``,
    ``height``, ``direction``, function headers, node sizes) and ``positions[i]`` maps version ids to
    the top left corner ``[x, y]``. Versions marked ``gone`` keep the position of the previous frame.

    Bands of ranks (spec 9.5): ``rank_wrap`` (an int or ``"auto"``) for every function, ``rank_wraps``
    per function; ``rank_flow`` is ``restart`` or ``snake``; ``fit`` is the target box of ``auto``
    (width, height); ``cuts`` maps a function to the first ranks of the bands of a leader, taken when
    the count agrees; ``call_edges`` says whether call edges are drawn (they need gutter lanes);
    ``notes`` receives the warnings (a count clamped)."""
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
    fn_min: dict[str, float] = {fn["name"]: (max(len(fn["name"]) * 9.0, 60.0) if tb else 60.0) for fn in functions}
    rank_ext: dict[str, dict[int, float]] = {fn["name"]: {} for fn in functions}
    rank_along: dict[str, dict[int, float]] = {fn["name"]: {} for fn in functions}
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
                    rank_along[name][rank] = max(rank_along[name].get(rank, 0.0),
                                                 sum(along[i] for i in line) + GAP_ALONG * (len(line) - 1))
                ext = sum(max(across[i] for i in line) for line in lines) + GAP_LINE * (len(lines) - 1)
                rank_ext[name][rank] = max(rank_ext[name][rank], ext)
        rows_per_frame.append(wrapped)
    header = HEADER if tb else 0.0
    names = [fn["name"] for fn in functions]
    fn_ranks = {name: sorted(set(ranks[name].values())) for name in names}
    index = {name: {r: i for i, r in enumerate(fn_ranks[name])} for name in names}
    exts = {name: [rank_ext[name].get(r, LABEL_H) for r in fn_ranks[name]] for name in names}

    # ---- the count of bands of each function
    wanted = {name: (rank_wraps or {}).get(name, rank_wrap) for name in names}
    counts: dict[str, int] = {}
    autos = []
    for name in names:
        w, most = wanted[name], len(fn_ranks[name])
        if w == "auto":
            autos.append(name)
            counts[name] = 1
        else:
            counts[name] = max(1, min(int(w), most))
    if notes is not None:
        if rank_wrap != "auto" and int(rank_wrap) > 1 and names:
            fixed = [n for n in names if n not in (rank_wraps or {})]
            if fixed and all(int(rank_wrap) > len(fn_ranks[n]) for n in fixed):
                most = max(len(fn_ranks[n]) for n in fixed)
                notes.append(f"rank_wrap={rank_wrap} is more than the ranks of every function drawn "
                             f"(at most {most}): clamped")
        for name, w in (rank_wraps or {}).items():
            if name in fn_ranks and w != "auto" and int(w) > len(fn_ranks[name]):
                notes.append(f"rank_wraps: {name} has {len(fn_ranks[name])} rank(s), fewer than {w}: clamped")
    # the edges of a function that may cross bands, per frame (for the lanes of the gutters)
    crossings: dict[str, list[set]] = {name: [] for name in names}
    seen: dict[str, set] = {name: set() for name in names}
    for f in frames:
        nodes = f["nodes"]
        per: dict[str, set] = {name: set() for name in names}
        for key in f.get("edges", {}):
            src, rest = key.split("->", 1)
            dst, kind = rest.split(":", 1)
            if src not in nodes or dst not in nodes or (kind == "call" and not call_edges):
                continue
            a, b = versions[src], versions[dst]
            if a["function"] != b["function"] or a["function"] not in per:
                continue
            name = a["function"]
            per[name].add((index[name][ranks[name][a["name"]]], index[name][ranks[name][b["name"]]], dst))
        for name, edges in per.items():
            frozen = frozenset(edges)
            if frozen and frozen not in seen[name]:
                seen[name].add(frozen)
                crossings[name].append(edges)

    shapes: dict[tuple[str, int], dict] = {}

    def shape(name: str, n: int) -> dict:
        """The bands of a function cut in ``n``: first ranks, extent along and length of each, gaps."""
        key = (name, n)
        if key in shapes:
            return shapes[key]
        count = len(fn_ranks[name])
        starts = None
        lead = (cuts or {}).get(name)
        if lead and len(lead) == n and lead[0] == 0 and all(a < b for a, b in zip(lead, lead[1:])) and lead[-1] < count:
            starts = list(lead)
        if starts is None:
            starts = cut_ranks(exts[name], n)
        band = _bands_of(starts, count)
        n = len(starts)
        widths, lengths = [], []
        for k in range(n):
            members = [i for i in range(count) if band[i] == k]
            w = fn_min[name] if k == 0 else 60.0
            for i in members:
                w = max(w, rank_along[name].get(fn_ranks[name][i], 0.0))
            widths.append(w)
            lengths.append(band_length([exts[name][i] for i in members]))
        if n == 1:  # exactly the arithmetic of the layout without bands
            c = MARGIN + header
            for e in exts[name]:
                c += e + GAP_RANK
            fn_across = c - GAP_RANK + MARGIN + LANE
        else:
            fn_across = MARGIN + header + max(lengths) + MARGIN + LANE
        lanes = _gutter_lanes(crossings[name], band, n) if n > 1 else []
        gaps = [gutter_gap(k) for k in lanes]
        out = {"starts": starts, "band": band, "widths": widths, "lengths": lengths, "lanes": lanes, "gaps": gaps,
               "along": sum(widths) + sum(gaps), "across": fn_across}
        shapes[key] = out
        return out

    def extent(choice: dict[str, int]) -> tuple[float, float]:
        a = MARGIN
        for name in names:
            if not tb:
                a += HEADER
            a += shape(name, choice[name])["along"] + FUNCTION_GAP
        total_along = a - FUNCTION_GAP + MARGIN + LANE + 10
        total_across = max((shape(name, choice[name])["across"] for name in names), default=2 * MARGIN)
        return (total_along, total_across) if tb else (total_across, total_along)

    if autos:
        room_w, room_h = fit or (1136.0, 430.0)

        def scale(choice):
            w, h = extent(choice)
            return min(room_w / w, room_h / h, AUTO_CAP)

        for _ in range(4):  # coordinate descent over the functions with `auto`
            changed = False
            for name in autos:
                options = range(1, min(AUTO_MAX, len(fn_ranks[name])) + 1)
                scores = {n: scale({**counts, name: n}) for n in options}
                top = max(scores.values())
                pick = min(n for n, sc in scores.items() if sc >= top * (1 - AUTO_TIE))
                if pick != counts[name]:
                    counts[name], changed = pick, True
            if not changed:
                break

    chosen = {name: shape(name, counts[name]) for name in names}
    snake = rank_flow == "snake"
    rank_at: dict[str, dict[int, float]] = {}
    band_start: dict[str, list[float]] = {}
    fn_start: dict[str, float] = {}
    a = MARGIN
    for name in names:
        if not tb:
            a += HEADER  # the function name sits above its band
        fn_start[name] = a
        sh = chosen[name]
        starts = []
        p = a
        for k, w in enumerate(sh["widths"]):
            starts.append(p)
            p += w + (sh["gaps"][k] if k < len(sh["gaps"]) else 0.0)
        band_start[name] = starts
        a += sh["along"] + FUNCTION_GAP
    width, height = extent(counts)
    rank_span: dict[str, dict[int, tuple[float, float]]] = {}
    for name in names:
        sh = chosen[name]
        rank_at[name] = {}
        rank_span[name] = {}
        longest = max(sh["lengths"]) if sh["lengths"] else 0.0
        c = MARGIN + header
        prev_band = 0
        for i, rank in enumerate(fn_ranks[name]):
            k = sh["band"][i]
            if k != prev_band:
                c = MARGIN + header
                prev_band = k
            e = exts[name][i]
            q = c
            if snake and k % 2 == 1:  # a band running backwards: its first rank at the far end
                q = MARGIN + header + longest - (c - MARGIN - header) - e
            rank_at[name][rank] = q
            rank_span[name][rank] = (q, q + e)
            c += e + GAP_RANK
    positions: list[dict[str, list[float]]] = []
    prev: dict[str, list[float]] = {}
    for f, rows in zip(frames, rows_per_frame):
        pos: dict[str, list[float]] = {}
        for name, byrank in rows.items():
            sh = chosen[name]
            for rank, lines in byrank.items():
                k = sh["band"][index[name][rank]]
                start, span = band_start[name][k], sh["widths"][k]
                q = rank_at[name][rank]
                for line in lines:
                    row_len = sum(along[i] for i in line) + GAP_ALONG * (len(line) - 1)
                    p = start + (span - row_len) / 2
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
    wrapped_box = {}
    for fn in functions:
        n = fn["name"]
        sh = chosen[n]
        first_w = sh["widths"][0]
        if tb:
            headers[n] = {"x": round(fn_start[n] + first_w / 2, 1), "y": round(MARGIN + HEADER / 2, 1), "anchor": "middle"}
        else:
            headers[n] = {"x": round(MARGIN, 1), "y": round(fn_start[n] - 10, 1), "anchor": "start"}
        # the extent of the function along the packing axis, and the lane where its back edges travel
        bands[n] = {"start": round(fn_start[n], 1), "end": round(fn_start[n] + sh["along"], 1),
                    "lane": round(fn_start[n] + sh["along"] + LANE, 1)}
        if len(sh["widths"]) > 1:
            first = MARGIN + header
            longest = max(sh["lengths"])
            wrapped_box[n] = {
                "cut": sh["starts"],
                "bands": [{"start": round(s, 1), "end": round(s + w, 1), "lane": round(s + w + LANE, 1),
                           "flip": bool(snake and k % 2 == 1)}
                          for k, (s, w) in enumerate(zip(band_start[n], sh["widths"]))],
                "gutters": [{"at": round(band_start[n][k] + sh["widths"][k] + GUTTER_FIRST, 1), "lanes": max(lanes, 1),
                             "step": GUTTER_STEP} for k, lanes in enumerate(sh["lanes"])],
                "top": round(first - END_GAP * GAP_RANK, 1), "bottom": round(first + longest + END_GAP * GAP_RANK, 1),
                "blocks": {b["name"]: [sh["band"][index[n][ranks[n][b["name"]]]], index[n][ranks[n][b["name"]]],
                                       round(rank_span[n][ranks[n][b["name"]]][0], 1),
                                       round(rank_span[n][ranks[n][b["name"]]][1], 1)] for b in fn["blocks"]},
            }
    box = {"width": round(width, 1), "height": round(height, 1),
           "direction": "TB" if tb else "LR", "headers": headers, "bands": bands,
           "sizes": {vid: list(s) for vid, s in sizes.items()}}
    if wrapped_box:
        box["rankWrap"] = wrapped_box
        box["gaps"] = {"rank": GAP_RANK, "line": GAP_LINE}
    return box, positions
