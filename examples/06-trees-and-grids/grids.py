"""Grid algorithms for the slides: breadth-first search in a maze and a longest common subsequence."""
from collections import deque

from lattice import GridTrace


def maze_bfs(values):
    """`values` is a list of strings: '#' wall, 'S' start, 'G' goal, anything else open."""
    rows = [list(r) for r in values]
    find = {ch: (r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch in "SG"}
    start, goal = find["S"], find["G"]
    t = GridTrace([["" for _ in row] for row in rows])
    base = {(r, c): "wall" for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "#"}
    base[start], base[goal] = "start", "goal"
    t.frame(cells=base, put={start: 0}, caption="Start at S; every cell will get its distance")
    dist, parent = {start: 0}, {}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            break
        found = {}
        r, c = cell
        for nr, nc in ((r - 1, c), (r, c + 1), (r + 1, c), (r, c - 1)):
            nxt = (nr, nc)
            if 0 <= nr < len(rows) and 0 <= nc < len(rows[nr]) and rows[nr][nc] != "#" and nxt not in dist:
                dist[nxt], parent[nxt] = dist[cell] + 1, cell
                queue.append(nxt)
                found[nxt] = "frontier" if nxt != goal else "goal"
        t.frame(cells={cell: "visited" if cell != start else "start", **found},
                put={n: dist[n] for n in found}, marks={cell: "active"}, pointers={"u": cell},
                panel={"queue": len(queue)}, caption=f"Visit a cell at distance {dist[cell]}")
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    path.reverse()
    t.frame(cells={p: "path" for p in path}, arrows={(a, b): "path" for a, b in zip(path, path[1:])},
            pointers={"u": None}, caption=f"Follow the parents back: a shortest path of {len(path) - 1} steps")
    return t


def lcs(a, b):
    n, m = len(a), len(b)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                L[i][j] = L[i - 1][j - 1] + 1
            else:
                L[i][j] = max(L[i - 1][j], L[i][j - 1])
    return L


def lcs_trace(a="ABCBDAB", b="BDCABA"):
    n, m = len(a), len(b)
    L = lcs(a, b)
    grid = [[0 if i == 0 or j == 0 else None for j in range(m + 1)] for i in range(n + 1)]
    t = GridTrace(grid, rows=["", *a], cols=["", *b])
    t.frame(caption="Row 0 and column 0 are 0: an empty prefix has nothing in common")
    back = {}
    prev = None
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                src, why = (i - 1, j - 1), f"{a[i - 1]} = {b[j - 1]}: diagonal + 1"
            elif L[i - 1][j] >= L[i][j - 1]:
                src, why = (i - 1, j), f"{a[i - 1]} ≠ {b[j - 1]}: max comes from above"
            else:
                src, why = (i, j - 1), f"{a[i - 1]} ≠ {b[j - 1]}: max comes from the left"
            back[(i, j)] = src
            arrows = {((i, j), src): "active"}
            if prev:
                arrows[prev] = "dim"
            prev = ((i, j), src)
            t.frame(put={(i, j): L[i][j]}, cells={(i, j): "visited"}, marks={(i, j): "active", src: "compare"},
                    arrows=arrows, caption=why)
    i, j, path = n, m, []
    while i and j:
        path.append((i, j))
        i, j = back[(i, j)]
    common = "".join(a[i - 1] for i, j in reversed(path) if back[(i, j)] == (i - 1, j - 1))
    t.frame(arrows={((p, back[p])): "path" for p in path}, cells={p: "path" for p in path},
            caption=f"Follow the arrows back from the corner: LCS = {common}, length {L[n][m]}")
    return t
