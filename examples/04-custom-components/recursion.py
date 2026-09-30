"""The function shown on the slides, and a trace of its calls."""
from lattice import Trace


def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def fib_trace(n=4):
    t = Trace({"stack": []})
    stack = []

    def call(k):
        stack.append({"call": f"fib({k})", "note": "running"})
        t.frame(stack=list(map(dict, stack)), caption=f"Call fib({k})", meta={"line": 2})
        if k < 2:
            stack[-1]["ret"] = k
            t.frame(stack=list(map(dict, stack)), caption=f"Base case: fib({k}) = {k}", meta={"line": 3})
            stack.pop()
            return k
        stack[-1]["note"] = f"waiting for fib({k - 1})"
        a = call(k - 1)
        stack[-1]["note"] = f"got {a}, waiting for fib({k - 2})"
        b = call(k - 2)
        stack[-1]["ret"] = a + b
        t.frame(stack=list(map(dict, stack)), caption=f"fib({k}) = {a} + {b}", meta={"line": 4})
        stack.pop()
        return a + b

    result = call(n)
    t.frame(stack=[], caption=f"fib({n}) = {result} after {len(t)} steps", meta={"line": 1})
    return t
