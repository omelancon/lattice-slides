"""The function traced by the stack-anim plugin of the manual."""
from lattice import Trace


def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def fib_trace(n=4):
    """A plain Trace: frames hold a `stack` list and a caption; the runtime draws them."""
    t = Trace({"stack": []})
    stack = []

    def call(k):
        stack.append({"call": f"fib({k})", "note": "running"})
        t.frame(stack=[dict(f) for f in stack], caption=f"Call fib({k})", meta={"line": 1})
        if k < 2:
            stack[-1]["ret"] = k
            t.frame(stack=[dict(f) for f in stack], caption=f"Base case: fib({k}) = {k}", meta={"line": 3})
            stack.pop()
            return k
        a = call(k - 1)
        stack[-1]["note"] = f"got {a}"
        b = call(k - 2)
        stack[-1]["ret"] = a + b
        t.frame(stack=[dict(f) for f in stack], caption=f"fib({k}) = {a} + {b}", meta={"line": 4})
        stack.pop()
        return a + b

    result = call(n)
    t.frame(stack=[], caption=f"fib({n}) = {result}", meta={"line": 1})
    return t
