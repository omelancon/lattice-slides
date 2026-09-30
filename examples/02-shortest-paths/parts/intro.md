# The problem {#problem}

Given a weighted graph and a source $s$, find $\text{dist}(s, v)$ for every vertex $v$.

{.reveal}
- Road networks, packet routing, game path finding
- Weights are **non-negative** today (see [[bellman-ford]] otherwise)
- Unweighted graphs are the easy case: breadth-first search

::: notes
Ask the room for other applications before revealing the list.
:::

# Unweighted warm-up: BFS {#bfs}

{.reveal}
- BFS explores the graph layer by layer
- Each layer is one edge further from the source

```graph-anim {#bfs source="../algos.py:bfs_trace" graph="../data/city.dot" start=A}
edge_labels: false
height: 360
```

{.reveal}
- With weights, "fewer edges" no longer means "shorter"

```timeline
reveal 2          # both bullets before the animation starts
bfs 1..end        # then every BFS frame
reveal 3          # finally the conclusion
```
