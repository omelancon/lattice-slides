---
title: Trees and Grids
author: Data structures, week 7
tours:
  short: [trees-and-grids, avl-insertions, lcs, thanks]
---

# Trees and Grids {layout=title}

Data structures, week 7. Animated from the implementations used in the lab.

# Balanced search trees

{.reveal}
- A binary search tree is fast only while it stays shallow
- An AVL tree keeps every **balance factor** (left height minus right height) in $[-1, 1]$
- When an insertion breaks that, one or two **rotations** repair it in $O(1)$

::: detour {#rotations label="Rotations up close" key=r}
# A right rotation {#right-rotation}

```tree-anim {#rot source="avl.py:rotation_trace" height=300}
```
:::

# AVL insertions {#avl-insertions pdf="6,19,end"}

:::: columns
::: column {width=5fr}
```code {#code lang=python file="avl.py" symbol=insert follow=tree}
```
:::
::: column {width=6fr}
```tree-anim {#tree source="avl.py:avl_trace" height=380}
values: [10, 20, 30, 40, 50, 25]
```
:::
::::

::: notes
The trace calls the lab's own `insert` with a callback; the code on the left follows it.
Badges are balance factors. The last insertion needs a double rotation.
:::

# Breadth-first search in a maze {#maze pdf=end}

```grid-anim {#bfs source="grids.py:maze_bfs" height=400}
panel: [queue]
values:
  - "#############"
  - "#S....#.....#"
  - "#.###.#.###.#"
  - "#...#...#...#"
  - "###.#####.#.#"
  - "#.........#G#"
  - "#############"
```

# Longest common subsequence {#lcs .small}

:::: columns
::: column {width=1fr}
$$
L_{i,j} = \begin{cases}
L_{i-1,j-1} + 1 & \text{if } a_i = b_j \\
\max(L_{i-1,j}, L_{i,j-1}) & \text{else}
\end{cases}
$$

Each cell depends on three neighbours; the arrows remember which one won.
:::
::: column {width=1fr}
```grid-anim {#table source="grids.py:lcs_trace" a=ABCBDAB b=BDCABA height=400}
```
:::
::::

# Costs

| Algorithm | Time | Space |
|---|---|---|
| AVL insertion | $O(\log n)$ | $O(1)$ extra |
| BFS on a grid | $O(rc)$ | $O(rc)$ |
| LCS table | $O(nm)$ | $O(nm)$ |

# Thanks {#thanks .center}

Questions? Press `o` for the overview.
