---
title: Extending Lattice
author: Lattice examples
---

# Extending Lattice {layout=title}

Two custom components, written in a single `lattice_plugins.py` next to this deck.

# A plugin is a Python file {#plugin-file}

```code-steps {file="lattice_plugins.py" lang=python lines=16-60 line_base=file linenos=true}
steps:
  - 16-21     # register a name, declare options, body kind and CSS
  - 23-28     # parse the block body
  - 29-37     # compute the table at build time
  - 38        # return HTML: no JavaScript needed
  - 46-52     # an animated component also names its runtime
  - 54-60     # frames come from a Trace; positions drive the steps
```

::: notes
Lattice imports `lattice_plugins.py` automatically; installed packages are enabled with `plugins:` in the front matter.
:::

# Truth tables, computed at build time {#truth}

:::: columns
::: column {width=3fr}
```truth-table
a and b
a or b
not (a and b) == (not a or not b)
```
:::
::: column {width=2fr}
{.reveal}
- The body lists expressions; variables are found with `ast`
- The last column checks De Morgan's law: it is always 1
- Nothing runs in the browser for this component
:::
::::

# The call stack of fib(4) {#stack}

:::: columns
::: column {width=5fr}
```code {#src lang=python file="recursion.py" symbol=fib follow=calls}
```
:::
::: column {width=6fr}
```call-stack {#calls source="recursion.py:fib_trace"}
n: 4
```
:::
::::

# Its runtime, in a few lines {#runtime}

```code-steps {file="call_stack.js" lang=javascript linenos=true line_base=file}
steps:
  - 2-6       # mount: build the DOM once, keep references
  - 7-17      # show: render the state at an absolute position
```

# Thanks {.center}

Components are Python classes plus optional JavaScript. See `docs/spec.md`, section 8.
