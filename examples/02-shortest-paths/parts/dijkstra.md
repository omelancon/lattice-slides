# Dijkstra's algorithm {#dijkstra}

:::: columns
::: column {width=6fr}
```code {#code lang=python file="../algos.py" symbol=dijkstra follow=trace}
```
:::
::: column {width=6fr}
```graph-anim {#trace source="../algos.py:dijkstra_trace" graph="../data/city.dot" start=A}
panel: [dist, queue]
height: 330
```
:::
::::

::: notes
The code on the left follows the animation: each frame names the line it executes.
If someone asks about negative weights, go to [[bellman-ford]].
For the correctness argument, see [[dijkstra-proof]].
:::

# Complexity {#complexity}

With a binary heap, each vertex is popped once and each edge relaxed once:

$$O\big((V + E)\log V\big)$$

```plot {data="../data/bench.csv" x=vertices y=ms group=queue logy=true height=3.6}
xlabel: vertices (E = 4V)
ylabel: time (ms, log scale)
```

::: detour {#heap-refresher label="Refresher: binary heaps" key=h}
::include{file="../shared/heaps.md"}
:::

::: notes
Numbers in the chart are illustrative, generated for this example.
:::
