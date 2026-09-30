---
title: Sorting, your way
author: Workshop
theme: dark
tours:
  bubble-only: [sorting-your-way, pick, bubble, compare, done]
---

# Sorting, your way {layout=title}

A choose-your-own workshop: the audience picks the algorithm.

# Pick an algorithm {#pick}

Every option ends on the same comparison slide.

::: branch {layout=cards}
- [[bubble|Bubble sort]] swap neighbours until nothing moves
- [[insertion|Insertion sort]] grow a sorted prefix
- [[quick|Quicksort]] partition around a pivot
:::

::: notes
Let the room vote. Press 1, 2 or 3, or click a card.
:::

# Bubble sort {#bubble next=compare}

:::: columns
::: column {width=5fr}
```code {#src lang=python file="sorts.py" symbol=bubble_sort follow=bars}
```
:::
::: column {width=6fr}
```array-anim {#bars source="sorts.py:bubble_trace"}
values: [5, 1, 4, 2, 8, 3]
```
:::
::::

# Insertion sort {#insertion next=compare}

:::: columns
::: column {width=5fr}
```code {#src lang=python file="sorts.py" symbol=insertion_sort follow=bars}
```
:::
::: column {width=6fr}
```array-anim {#bars source="sorts.py:insertion_trace"}
values: [5, 1, 4, 2, 8, 3]
panel: [key]
```
:::
::::

# Quicksort {#quick next=compare}

{.reveal}
- Choose a pivot, partition, recurse on both sides
- Lomuto partition: one scan, pivot at the end

```array-anim {#bars source="sorts.py:quick_trace"}
values: [5, 1, 4, 2, 8, 3, 7, 6]
```

```timeline
reveal 1
reveal 2
bars 1..end
```

::: detour {label="The recursion tree" key=r}
# The recursion tree

```dot
digraph {
  node [shape=box, style=rounded, fontname="Helvetica"]; edge [arrowsize=0.6];
  a [label="5 1 4 2 8 3 7 6"]; b [label="5 1 4 2 3"]; c [label="8 7"];
  d [label="1 2"]; e [label="5 4"]; f [label="7"];
  a -> b; a -> c; b -> d; b -> e; c -> f;
}
```

Balanced splits give depth $\log_2 n$; a sorted input with a last-element pivot gives depth $n$.
:::

# How many comparisons? {#compare}

```plot {source="sorts.py:comparison_plot"}
```

Counted by instrumented versions of the three sorts on random inputs (seeded, so the chart is reproducible).

# Thanks {#done .center}

Press `o` to see the three paths through this deck.
