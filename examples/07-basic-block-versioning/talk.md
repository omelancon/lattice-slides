---
title: Basic Block Versioning
author: Compilers, ahead-of-time optimization of dynamic languages
tours:
  short: [basic-block-versioning, sum-to-n-ai, fact-ai, find-cfg, find-sbbv, power4-lv, fact-lv, thanks]
---

# Basic Block Versioning {layout=title}

Specializing control-flow graphs ahead of time, one version at a time.

# Abstract interpretation: union, widening, narrowing {#sum-to-n-ai}

```abstract-interp-anim {#ai program="programs/sum-to-n.bbv" height=420}
show: [label, context, code]
panel: [worklist, history]
history: [B.i]
```

::: notes
Thesis figures 1 and 2. One context per block; at the loop entry B the context of `i` grows by union, and widening jumps to the next threshold (sign, 8, 32, 64 bits): the chain in the panel is the red path of figure 2.
:::

# Narrowing at a conditional: `fact` {#fact-ai}

```abstract-interp-anim {#fai program="programs/fact-loop.bbv" height=400}
show: [label, context, code]
panel: [worklist]
```

::: notes
Thesis figure 4. `(> i 0)` narrows `i` to `[1, ∞)` in the loop body, so `(* acc i)` multiplies positive integers and the result is positive. The argument is assumed to be an integer (`n: fx | bg`).
:::

# A control-flow graph with redundant checks {#find-cfg}

:::: columns
::: column {width=3fr}
```bbv-cfg {#cfg program="programs/find.bbv" height=470}
```
:::
::: column {width=2fr}
{.reveal}
- `find` returns the first element of `lst` satisfying `p`
- Every `car`, `cdr` and call is guarded: `pair?` and `procedure?` tests
- Abstract interpretation removes the repeated `pair?` tests of one iteration
- But `p` is checked again at every iteration: the loop entry `A` is shared
:::
::::

::: notes
The source CFG of thesis figure 6, with the run-time checks inlined. Press Down for the loop entry's story.
:::

# SBBV specializes `find` (limit 2) {#find-sbbv}

:::: columns
::: column {width=1fr}
```bbv-cfg {#src program="programs/find.bbv" follow=trace height=440}
show: [label]
```
:::
::: column {width=3fr}
```bbv-anim {#trace program="programs/find.bbv" algorithm=sbbv limit=2 direction=LR height=440}
show: [label, context]
panel: [queue, checks]
```
:::
::::

::::: detour {#one-block label="One block at a time" key=b}
# Specializing one block at a time {#one-block-steps}

:::: columns
::: column {width=5fr}
```code {#algo lang=text file="lattice:bbv/pseudocode/sbbv.txt" lines=22-51 follow=inst meta=algo line_base=file linenos=true}
```
:::
::: column {width=4fr}
```bbv-anim {#inst program="programs/power4.bbv" algorithm=sbbv limit=2 entry=square granularity=instruction height=460}
functions: [square]
events: [start, dequeue, instruction, done]
```
:::
::::

::: notes
Thesis algorithms 1.4 to 1.6. Each step specializes one instruction of the dequeued version; the listing on the left follows.
:::
:::::

::: notes
The specialized CFG of figure 6: A2 is the loop entry where `p` is known to be a procedure, and B2 turns the `procedure?` test into a `goto`. The source CFG on the left highlights the block being specialized.
:::

# How many versions? {#limits}

The version limit bounds duplication. What happens to `find` with another limit?

::: branch
- [[find-limit-1|Limit 1: merges]] every block keeps one version
- [[find-limit-3|Limit 3: more room]] nothing needs merging
:::

# Limit 1: the loop entry merges back {#find-limit-1 next=power4-lv}

```bbv-anim {#l1 program="programs/find.bbv" algorithm=sbbv limit=1 direction=LR height=470}
show: [label, context]
panel: [queue, merges]
```

::: notes
A2 (p: proc) is merged into A1: the union is the generic context, so the loop returns to A1 and `procedure?` is checked at every iteration again. Notice the versions that become unreachable after the merge.
:::

# Limit 3: the same result as limit 2 {#find-limit-3 next=power4-lv}

```bbv-anim {#l3 program="programs/find.bbv" algorithm=sbbv limit=3 direction=LR height=470}
show: [label, context]
panel: [versions, checks]
```

# Lambda versioning: specialized return points {#power4-lv}

```bbv-anim {#lv program="programs/power4.bbv" algorithm=lv limit=3 entry=power4 wrap=3 height=470}
functions: [power4, square]
show: [label, context]
panel: [queue]
```

::: notes
Thesis figure 14. `power4` calls `square` twice. The first call site gets one return point per exit contract of `square` (fixnum, flonum, generic), and each return point calls a specialized entry of `square`. Return edges are dashed and indexed.
:::

# Operators as hyperfunctions {#square-ops}

```bbv-anim {#ops program="programs/square-ops.bbv" algorithm=lv limit=3 entry=square height=470}
functions: [square, "*"]
show: [label, context]
```

::: notes
Thesis figure 15. `*` is an ordinary function with no version limit. Because `square` passes the same variable twice, the entry contexts of `*` keep `a/b` in one class: one type test covers both arguments.
:::

# Recursion: `fact` checks its argument once {#fact-lv}

```bbv-anim {#fact program="programs/fact.bbv" algorithm=lv limit=2 entry=fact heuristic=arithmetic height=400}
show: [label, context, code]
panel: [queue, checks]
```

::: notes
Thesis figure 16. The operators `=`, `-` and `*` are hidden hyperfunctions of the runtime. A generic entry A1 checks the type of n once, then the recursive call uses the fixnum entry: the whole fixnum path runs without a type test; overflows fall back to the generic path through the `[1]` return points.
:::

::::: detour {#sbbv-fact label="The same program under SBBV" key=s}
# `fact` under SBBV: calls are opaque {#fact-sbbv}

```bbv-anim {#fs program="programs/fact.bbv" algorithm=sbbv limit=2 entry=fact height=440}
panel: [checks]
```

::: notes
Without interprocedural propagation every call returns an unknown value, so nothing is learned about `n` or the result.
:::
:::::

# Thanks {#thanks .center}

Programs are written in a small CFG language; the algorithms run at build time. Press `o` for the overview.
