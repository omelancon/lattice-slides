"""Algorithms and their animation traces for the shortest-paths deck."""
from collections import deque
from heapq import heappop, heappush

from lattice import ArrayTrace, GraphTrace

INF = float("inf")


def dijkstra(graph, source):
    dist = {v: INF for v in graph}
    dist[source] = 0
    queue = [(0, source)]
    while queue:
        d, u = heappop(queue)
        if d > dist[u]:
            continue
        for v, w in graph[u].items():
            if d + w < dist[v]:
                dist[v] = d + w
                heappush(queue, (dist[v], v))
    return dist


def dijkstra_trace(g, start="A"):
    """Replays `dijkstra` above on a networkx graph. meta["line"] points into its source."""
    t = GraphTrace(g)
    dist = {v: INF for v in g}
    dist[start] = 0
    parent = {}
    queue = [(0, start)]

    def panel():
        return {"dist": {v: ("\u221e" if d == INF else d) for v, d in sorted(dist.items())},
                "queue": [f"{v}:{d}" for d, v in sorted(queue)]}

    t.frame(nodes={start: {"state": "frontier", "label": 0}}, panel=panel(),
            caption=f"dist[{start}] = 0, push {start}", meta={"lines": [3, 4]})
    done = set()
    while queue:
        d, u = heappop(queue)
        if d > dist[u]:
            t.frame(panel=panel(), caption=f"Stale entry {u}:{d}, skip it", meta={"lines": [7, 8]})
            continue
        t.frame(nodes={u: "active"}, panel=panel(), caption=f"Pop {u} at distance {d}", meta={"line": 6})
        for v in sorted(g[u]):
            w = g[u][v]["weight"]
            if v in done:
                continue
            t.frame(edges={(u, v): "active"}, caption=f"Relax {u}-{v}: {d} + {w} vs {dist[v] if dist[v] != INF else 'inf'}",
                    meta={"line": 10})
            if d + w < dist[v]:
                edges = {(u, v): "tree"}
                if v in parent:
                    edges[(parent[v], v)] = None  # the old tree edge is no longer used
                dist[v] = d + w
                parent[v] = u
                heappush(queue, (dist[v], v))
                t.frame(nodes={v: {"state": "frontier", "label": dist[v]}}, edges=edges, panel=panel(),
                        caption=f"Improve dist[{v}] to {dist[v]}", meta={"lines": [11, 12]})
            else:
                t.frame(edges={(u, v): None}, caption=f"No improvement for {v}", meta={"line": 10})
        done.add(u)
        t.frame(nodes={u: "visited"}, caption=f"{u} is final", meta={"line": 5})
    t.frame(caption="Queue empty: the tree edges form a shortest-path tree", meta={"line": 13})
    return t


def bfs_trace(g, start="A"):
    t = GraphTrace(g)
    level = {start: 0}
    queue = deque([start])
    t.frame(nodes={start: {"state": "frontier", "label": 0}}, caption=f"Start at {start}, layer 0")
    while queue:
        u = queue.popleft()
        t.frame(nodes={u: "active"}, caption=f"Visit {u}")
        found = []
        for v in sorted(g[u]):
            if v not in level:
                level[v] = level[u] + 1
                queue.append(v)
                found.append(v)
                t.frame(nodes={v: {"state": "frontier", "label": level[v]}}, edges={(u, v): "tree"})
        if found:
            t.frames[-1]["caption"] = f"Discover {', '.join(found)} in layer {level[u] + 1}"
        t.frame(nodes={u: "visited"})
    t.frame(caption="Every vertex is labelled with its number of edges from " + start)
    return t


def heap_push_trace(values, push=1):
    """Push `push` onto the heap `values` and sift it up."""
    a = list(values) + [push]
    t = ArrayTrace(values + [None])
    i = len(a) - 1
    t.frame(values=a, marks={i: "pivot"}, pointers={"new": i}, caption=f"Append {push} at index {i}")
    while i > 0:
        p = (i - 1) // 2
        t.frame(marks={i: "compare", p: "compare"}, pointers={"new": i, "parent": p},
                caption=f"Compare a[{i}] = {a[i]} with its parent a[{p}] = {a[p]}")
        if a[p] <= a[i]:
            break
        a[i], a[p] = a[p], a[i]
        t.frame(values=a, marks={i: "swap", p: "swap"}, pointers={"new": p, "parent": None},
                caption="Swap: the parent was larger")
        i = p
    t.frame(values=a, marks={i: "done"}, pointers={"new": i, "parent": None}, caption="Heap order restored")
    return t
