"""Block bands: positions of versions per frame (spec 9.5).

Every function is a column (``TB``) or a band (``LR``), or with ``rank_wrap`` several of them (bands of
ranks: consecutive ranks cut into groups laid side by side, the cut computed once for the run). Inside it, each origin block has a rank
(its row in ``TB``, its column in ``LR``), from a Graphviz layout of the source CFG when available;
the versions alive in a frame are packed along the rank, sorted by the block's order and their
creation id, and the rank is centred in the function's column or band. Node sizes come from the
text, so a version never resizes.

Back edges inside a band (*loops*) travel in a gutter beside it: the gutter before the band or the one after it,
chosen per frame by ``_loop_sides`` (the shorter runs along the rank gaps, then the fewer edges crossed), with a
hysteresis so that a loop keeps its side while the costs stay close. Every function has a head gutter (before
its first band) and a tail gutter (after its last band), which take room only when a loop uses them.
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
FUNCTION_GAP = 64.0  # leaves room for the lane of back edges between functions beside each function
HEADER = 30.0
MARGIN = 40.0  # covers the runs of edges in the gap before a first rank (up to 0.62 of GAP_RANK, bbv.js) and the
#                runs past the ends of the ranks (END_GAP), or after a last rank, plus the arrowhead
LANE = 18.0  # distance of the first lane of a gutter from the band it borders


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
GUTTER_FIRST = LANE  # first lane of a gutter, from the end of the band before it
GUTTER_STEP = 5.0  # between two lanes of a gutter
GUTTER_CLEAR = LANE  # from the last lane to the band after it
GUTTER_LANES = 5  # most lanes of the edges between bands in a gutter; beyond, the targets closest to each other
#                   share one (bbv.js). Loops do not count toward it: each of their targets has a lane
HEAD_CLEAR = 10.0  # from the last lane of a head gutter to what lies before it (the function's name in LR)
SIDE_CROSS = 60.0  # the cost of a curved edge that a loop's run would cross, as a length
SIDE_KEEP = 40.0  # the bonus of the side a loop had in the frame before (hysteresis)
HEAD_GAIN = 50.0  # the head gutter opens when its loops save at least this much per frame of the run, on average
AUTO_MAX = 6  # `auto` tries 1 to this many bands
AUTO_CAP = 1.4  # the most the runtime enlarges a drawing (bbv.js: max-width of the SVG)
AUTO_TIE = 0.02  # within this fraction of the largest scale, fewer bands win
END_GAP = 0.75  # the runs past the ends of the ranks, in GAP_RANK from the first and last ranks: beyond the runs into a
#                 first rank (SLOT_IN in bbv.js reaches 0.62)


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


def _loop_sides(frames: list[dict], drawn: list[list[tuple]], places: list[dict], versions: dict, name: str,
                widths: list[float], flips: list[bool], along: dict, across: dict, head_open: bool = True) -> dict:
    """The side of every loop of function ``name`` in every frame, and the lanes of its gutters (spec 9.5).

    ``places[i]`` maps the versions of the function to ``(band, across, along)``, the along position counted
    from the start of the band. A loop is an edge between two versions of one band whose target is not after its
    source (the test of ``bbv.js``). Its side costs the two runs along the rank gaps (from the centres of its
    ends to the edge of the band on that side), ``SIDE_CROSS`` for each curved edge attached to a node those
    runs pass (the out-edges of the source's line, the in-edges of the target's line; edges routed through
    gutters take nested slots and are not counted), less ``SIDE_KEEP`` for the side of the frame before. Ties
    go ``after``; without ``head_open``, the loops of the first band never go before it. Returns ``sides`` (per frame, ``{key: "before"}``), ``head`` and ``tail`` (the most targets of
    loops in the head and tail gutters in a frame) and ``mid`` (per gutter between bands, the most lanes in a
    frame: its loops on each side plus the targets of the edges between bands, those capped) and ``gain`` (the
    cost the loops in the head gutter save, over the run)."""
    n = len(widths)
    sides: list[dict] = []
    head = tail = 0
    mid = [0] * max(n - 1, 0)
    previous: dict[str, str] = {}
    gain = 0.0
    for f, edges, pos in zip(frames, drawn, places):
        nodes = f["nodes"]
        out_ports: dict[str, int] = {}
        in_ports: dict[str, int] = {}
        loops = []
        cross: list[set] = [set() for _ in range(n - 1)]
        for src, dst, key in edges:
            fs, fd = versions[src]["function"], versions[dst]["function"]
            if name not in (fs, fd):
                continue
            if fs != fd:  # between two functions: a curve at its end in this function
                if fs == name:
                    out_ports[src] = out_ports.get(src, 0) + 1
                else:
                    in_ports[dst] = in_ports.get(dst, 0) + 1
                continue
            if src not in pos or dst not in pos:
                continue
            ks, as_, _ = pos[src]
            kd, ad, _ = pos[dst]
            if ks != kd:  # between bands: forward edges use the gutter after their band, the others the one before
                exit_, entry = (ks, kd - 1) if kd > ks else (ks - 1, kd)
                cross[exit_].add(dst)
                cross[entry].add(dst)
                continue
            back = (ad + across[dst] > as_ + across[src] / 2) if flips[ks] else (ad < as_ + across[src] / 2)
            if back:
                loops.append((key, src, dst, ks))
            else:
                out_ports[src] = out_ports.get(src, 0) + 1
                in_ports[dst] = in_ports.get(dst, 0) + 1
        lines: dict[tuple, list] = {}
        for vid, (k, a, l) in pos.items():
            if nodes.get(vid, {}).get("mark") != "gone":
                lines.setdefault((k, round(a, 1)), []).append((l + along[vid] / 2, vid))
        chosen: dict[str, str] = {}
        for key, src, dst, k in sorted(loops):
            _, as_, ls = pos[src]
            _, ad, ld = pos[dst]
            la, lb = ls + along[src] / 2, ld + along[dst] / 2
            best = None
            after = 0.0
            for side, edge in (("after", widths[k]), ("before", 0.0)):
                if side == "before" and k == 0 and not head_open:
                    continue
                crossed = sum(out_ports.get(u, 0) for c, u in lines.get((k, round(as_, 1)), ())
                              if u != src and min(la, edge) < c < max(la, edge))
                crossed += sum(in_ports.get(u, 0) for c, u in lines.get((k, round(ad, 1)), ())
                               if u != dst and min(lb, edge) < c < max(lb, edge))
                cost = abs(la - edge) + abs(lb - edge) + SIDE_CROSS * crossed
                if previous.get(key) == side:
                    cost -= SIDE_KEEP
                if side == "after":
                    after = cost
                if best is None or cost < best[0] - 1e-9:
                    best = (cost, side)
            chosen[key] = best[1]
            if best[1] == "before" and k == 0:
                gain += after - best[0]
        previous = chosen
        sides.append({key: side for key, side in chosen.items() if side == "before"})
        hd: set = set()
        tl: set = set()
        near: list[set] = [set() for _ in range(n - 1)]
        far: list[set] = [set() for _ in range(n - 1)]
        for key, _src, dst, k in loops:
            if chosen[key] == "before":
                (hd if k == 0 else far[k - 1]).add(dst)
            else:
                (tl if k == n - 1 else near[k]).add(dst)
        head, tail = max(head, len(hd)), max(tail, len(tl))
        for g in range(n - 1):
            mid[g] = max(mid[g], len(near[g]) + len(far[g]) + min(len(cross[g]), GUTTER_LANES))
    return {"sides": sides, "head": head, "tail": tail, "mid": mid, "gain": gain}


def layout_frames(tables: dict, frames: list[dict], show: list[str], layout_fn=None,
                  direction: str = "TB", wrap: int = 4, rank_wrap: int | str = 1, rank_wraps: dict | None = None,
                  rank_flow: str = "restart", fit: tuple[float, float] | None = None, cuts: dict | None = None,
                  call_edges: bool = False, notes: list | None = None,
                  sides: list | None = None) -> tuple[dict, list[dict]]:
    """Positions for every frame. Returns ``(box, positions)``: ``box`` describes the drawing (``width``,
    ``height``, ``direction``, function headers, node sizes) and ``positions[i]`` maps version ids to
    the top left corner ``[x, y]``. Versions marked ``gone`` keep the position of the previous frame.

    Bands of ranks (spec 9.5): ``rank_wrap`` (an int or ``"auto"``) for every function, ``rank_wraps``
    per function; ``rank_flow`` is ``restart`` or ``snake``; ``fit`` is the target box of ``auto``
    (width, height); ``cuts`` maps a function to the first ranks of the bands of a leader, taken when
    the count agrees; ``call_edges`` says whether call edges are drawn (they need gutter lanes);
    ``notes`` receives the warnings (a count clamped); ``sides`` receives, per frame, the loops that travel
    in the gutter before their band (``{edge key: "before"}``)."""
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
    # the edges drawn in each frame (call edges only with ``call_edges``), for the gutters and the sides of loops
    drawn: list[list[tuple]] = []
    for f in frames:
        nodes = f["nodes"]
        out = []
        for key in f.get("edges", {}):
            src, rest = key.split("->", 1)
            dst, kind = rest.split(":", 1)
            if src not in nodes or dst not in nodes or (kind == "call" and not call_edges):
                continue
            out.append((src, dst, key))
        drawn.append(out)
    # the functions with an edge to another function: their back edges between functions take a lane past the tail
    outward = {versions[src]["function"] for edges in drawn for src, dst, _ in edges
               if versions[src]["function"] != versions[dst]["function"]}
    snake = rank_flow == "snake"

    def places(name: str, sh: dict, starts: list[float]) -> list[dict]:
        """Per frame, the versions of a function: ``(band, across, along)``, the bands starting at ``starts``
        along the packing axis; a version marked ``gone`` keeps its place of the frame before."""
        out, prev = [], {}
        for f, rows in zip(frames, rows_per_frame):
            pos: dict[str, tuple] = {}
            for rank, lines in rows[name].items():
                k = sh["band"][index[name][rank]]
                start, span = starts[k], sh["widths"][k]
                q = sh["rank_at"][rank]
                for line in lines:
                    row_len = sum(along[i] for i in line) + GAP_ALONG * (len(line) - 1)
                    p = start + (span - row_len) / 2
                    for i in line:
                        pos[i] = (k, q, p)
                        p += along[i] + GAP_ALONG
                    q += max(across[i] for i in line) + GAP_LINE
            for vid, nd in f["nodes"].items():
                if nd.get("mark") == "gone" and vid in prev:
                    pos[vid] = prev[vid]
            out.append(pos)
            prev = {k: v for k, v in pos.items() if f["nodes"].get(k, {}).get("mark") != "gone"}
        return out

    shapes: dict[tuple[str, int], dict] = {}

    def shape(name: str, n: int) -> dict:
        """The bands of a function cut in ``n``: first ranks, extent along and length of each, the places of
        its ranks across, the sides of its loops and the lanes and room of its gutters."""
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
        # the ranks across: every band starts again at the top (TB) or left end (LR), or runs backwards (snake)
        rank_at: dict[int, float] = {}
        rank_span: dict[int, tuple[float, float]] = {}
        longest = max(lengths) if lengths else 0.0
        c = MARGIN + header
        prev_band = 0
        for i, rank in enumerate(fn_ranks[name]):
            k = band[i]
            if k != prev_band:
                c = MARGIN + header
                prev_band = k
            e = exts[name][i]
            q = c
            if snake and k % 2 == 1:  # a band running backwards: its first rank at the far end
                q = MARGIN + header + longest - (c - MARGIN - header) - e
            rank_at[rank] = q
            rank_span[rank] = (q, q + e)
            c += e + GAP_RANK
        out = {"starts": starts, "band": band, "widths": widths, "lengths": lengths, "across": fn_across,
               "rank_at": rank_at, "rank_span": rank_span}
        rel = places(name, out, [0.0] * n)
        flips = [bool(snake and k % 2 == 1) for k in range(n)]
        loops = _loop_sides(frames, drawn, rel, versions, name, widths, flips, along, across)
        if loops["head"] and loops["gain"] < HEAD_GAIN * max(len(frames), 1):  # not worth its room: closed
            loops = _loop_sides(frames, drawn, rel, versions, name, widths, flips, along, across, head_open=False)
        lanes = loops["mid"]
        gaps = [gutter_gap(k) for k in lanes]
        out.update({"lanes": lanes, "gaps": gaps, "along": sum(widths) + sum(gaps), "sides": loops["sides"],
                    "head_lanes": loops["head"], "tail_lanes": loops["tail"],
                    # room before the first band for the head gutter, and past the last one for more tail lanes
                    "head": LANE + GUTTER_STEP * (loops["head"] - 1) + HEAD_CLEAR if loops["head"] else 0.0,
                    "tail": GUTTER_STEP * (loops["tail"] - (0 if name in outward else 1)) if loops["tail"] else 0.0})
        shapes[key] = out
        return out

    def extent(choice: dict[str, int]) -> tuple[float, float]:
        a = MARGIN
        for name in names:
            if not tb:
                a += HEADER
            sh = shape(name, choice[name])
            a += sh["head"] + sh["along"] + sh["tail"] + FUNCTION_GAP
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
    band_start: dict[str, list[float]] = {}
    fn_start: dict[str, float] = {}
    a = MARGIN
    for name in names:
        if not tb:
            a += HEADER  # the function name sits above its band (and above its head gutter)
        sh = chosen[name]
        a += sh["head"]
        fn_start[name] = a
        starts = []
        p = a
        for k, w in enumerate(sh["widths"]):
            starts.append(p)
            p += w + (sh["gaps"][k] if k < len(sh["gaps"]) else 0.0)
        band_start[name] = starts
        a += sh["along"] + sh["tail"] + FUNCTION_GAP
    width, height = extent(counts)
    placed = {name: places(name, chosen[name], band_start[name]) for name in names}
    positions: list[dict[str, list[float]]] = []
    for i, f in enumerate(frames):
        pos: dict[str, list[float]] = {}
        gone = {vid for vid, nd in f["nodes"].items() if nd.get("mark") == "gone"}
        for name in names:
            for vid, (_k, q, p) in placed[name][i].items():
                if vid not in gone:
                    pos[vid] = [round(p, 1), round(q, 1)] if tb else [round(q, 1), round(p, 1)]
        for vid in f["nodes"]:  # gone versions last, at their place of the frame before
            if vid in gone:
                v = versions[vid]
                got = placed[v["function"]][i].get(vid)
                if got is not None:
                    pos[vid] = [round(got[2], 1), round(got[1], 1)] if tb else [round(got[1], 1), round(got[2], 1)]
        positions.append(pos)
    if sides is not None:
        sides.clear()
        for i in range(len(frames)):
            merged: dict[str, str] = {}
            for name in names:
                merged.update(chosen[name]["sides"][i])
            sides.append(merged)
    headers = {}
    bands = {}
    wrapped_box = {}
    loops_anywhere = False
    for fn in functions:
        n = fn["name"]
        sh = chosen[n]
        first_w = sh["widths"][0]
        if tb:
            headers[n] = {"x": round(fn_start[n] + first_w / 2, 1), "y": round(MARGIN + HEADER / 2, 1), "anchor": "middle"}
        else:
            headers[n] = {"x": round(MARGIN, 1), "y": round(fn_start[n] - sh["head"] - 10, 1), "anchor": "start"}
        # the extent of the function along the packing axis; the lane of the back edges between functions, past
        # the lanes of its tail gutter; the head and tail gutters of its loops, when it has some
        end = fn_start[n] + sh["along"]
        bands[n] = {"start": round(fn_start[n], 1), "end": round(end, 1),
                    "lane": round(end + LANE + (GUTTER_STEP * sh["tail_lanes"] if n in outward else 0.0), 1)}
        if sh["head_lanes"]:
            bands[n]["head"] = {"at": round(fn_start[n] - LANE, 1), "lanes": sh["head_lanes"], "step": GUTTER_STEP}
        if sh["tail_lanes"]:
            bands[n]["tail"] = {"at": round(end + LANE, 1), "lanes": sh["tail_lanes"], "step": GUTTER_STEP}
        blocks = {b["name"]: [sh["band"][index[n][ranks[n][b["name"]]]], index[n][ranks[n][b["name"]]],
                              round(sh["rank_span"][ranks[n][b["name"]]][0], 1),
                              round(sh["rank_span"][ranks[n][b["name"]]][1], 1)] for b in fn["blocks"]}
        if len(sh["widths"]) > 1:
            first = MARGIN + header
            longest = max(sh["lengths"])
            wrapped_box[n] = {
                "cut": sh["starts"],
                "bands": [{"start": round(s, 1), "end": round(s + w, 1), "flip": bool(snake and k % 2 == 1)}
                          for k, (s, w) in enumerate(zip(band_start[n], sh["widths"]))],
                "gutters": [{"at": round(band_start[n][k] + sh["widths"][k] + GUTTER_FIRST, 1), "lanes": max(lanes, 1),
                             "step": GUTTER_STEP} for k, lanes in enumerate(sh["lanes"])],
                "top": round(first - END_GAP * GAP_RANK, 1), "bottom": round(first + longest + END_GAP * GAP_RANK, 1),
                "blocks": blocks,
            }
        elif sh["head_lanes"] or sh["tail_lanes"]:  # the ranks of a function without bands, to route its loops
            bands[n]["blocks"] = blocks
        loops_anywhere = loops_anywhere or bool(sh["head_lanes"] or sh["tail_lanes"] or any(sh["lanes"]))
    box = {"width": round(width, 1), "height": round(height, 1),
           "direction": "TB" if tb else "LR", "headers": headers, "bands": bands,
           "sizes": {vid: list(s) for vid, s in sizes.items()}}
    if wrapped_box:
        box["rankWrap"] = wrapped_box
    if wrapped_box or loops_anywhere:
        box["gaps"] = {"rank": GAP_RANK, "line": GAP_LINE}
    return box, positions
