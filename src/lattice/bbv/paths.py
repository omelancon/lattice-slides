"""The walk of a path through the final graph of a versioning run (spec 9.5, Paths).

A path given by input types and the types returned by ``read()`` is an abstract run of the program
on the versions of the final graph, with a context of its own (the path context). Instructions run
again with the specializer's own transfer functions, so a value computed from an input or a read
stays narrowed. Calls and returns are matched with **summaries** (the functional approach to
interprocedural analysis): a callee is walked once per *activation*, its entry version with the
read position and the path context at its entry, and the exits that activation reaches are its
summary. Each call site that starts an activation receives the summary's exits through its own
return edges, now and whenever the summary grows; so an exit returns only to the call sites of its
own activations, at any depth of recursion, and the walk ends since activations are finite.

A state is a version, the read position and the activation it belongs to; its path context is the
union of the contexts that reach it. With intervals, unions are widened by the run's thresholds and
an activation is keyed by its entry version and read position only (its contexts are joined), so
that loops and recursion end.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .ir import RESULT, Assign, Call, Const, Fail, Goto, If, Move, Return
from .lv import return_context_of
from .sbbv import Specializer, Version
from .types import ANY, Context, Type

ROOT = ("root",)  # the activation of the entry function: its exits are the program returning
OVERFLOW = ("maybe", "never", "always")
NOT_FALSE = Type.of("#f").complement()
FALSE = Type.of("#f")


class PathError(ValueError):
    pass


@dataclass
class Walk:
    order: list[int] = field(default_factory=list)  # versions entered, in first-visit order
    edges: set[tuple[int, int, str]] = field(default_factory=set)  # (src, dst, kind) of the edges taken
    exits: dict[tuple[int, int], set[int]] = field(default_factory=dict)  # return edge (call site, return point) -> exits
    transitions: set[tuple[int, int]] = field(default_factory=set)  # version to version, an exit to its return point


class PathWalker:
    """Walk the versions of ``spec`` (a finished run) from the root of its entry function.

    ``inputs`` narrows the parameters of the entry function; ``reads`` gives the types of the
    successive ``read()`` calls, then ``exhausted`` (a list repeated as a cycle, or ``None`` for an
    error); ``overflow`` decides the result of ``fx+?`` and friends."""

    def __init__(self, spec: Specializer, *, inputs: dict[str, Type] | None = None, reads: list[Type] | None = None,
                 exhausted: list[Type] | None = None, overflow: str = "maybe", max_steps: int = 200000):
        self.spec = spec
        self.inputs = dict(inputs or {})
        self.reads = list(reads or [])
        self.exhausted = [ANY] if exhausted is None else list(exhausted)
        self.strict = exhausted is None
        self.overflow = overflow
        self.max_steps = max_steps
        self.states: dict[tuple, Context] = {}  # (version, read position, activation) -> path context
        self.callers: dict[tuple, set[tuple]] = {}  # activation -> (call site, read position, caller's activation)
        self.call_ctx: dict[tuple, Context] = {}  # (call site, read position, caller's activation, activation) -> context
        self.summary: dict[tuple, dict[tuple, Context]] = {}  # activation -> (exit, read position) -> exit context
        self.work: deque[tuple] = deque()
        self.queued: set[tuple] = set()
        self.result = Walk()

    # ------------------------------------------------------------ reads and primitive results
    def next_read(self, cur: int) -> tuple[Type, int]:
        n = len(self.reads)
        if cur < n:
            return self.reads[cur], cur + 1
        if self.strict:
            raise PathError(f"reads_exhausted: error: the path may execute read() more than {n} time"
                            f"{'s' if n != 1 else ''} (reads gives {n} type{'s' if n != 1 else ''})")
        k = cur - n
        return self.exhausted[k], n + (k + 1) % len(self.exhausted)

    def adjust(self, read: Type | None):
        def f(prim: str, t: Type) -> Type:
            if prim == "read" and read is not None:
                return read
            p = self.spec.program.prims[prim]
            if p.overflow and self.overflow == "never":
                return t.intersection(NOT_FALSE)
            if p.overflow and self.overflow == "always":
                return t.intersection(FALSE)
            return t
        return f

    # ------------------------------------------------------------ the walk
    def walk(self) -> Walk:
        spec = self.spec
        fn = spec.entry_function
        root = next((r for r in spec.roots if r.function == fn.name), None)
        if root is None:
            raise PathError(f"the run has no entry version of {fn.name}")
        root = spec.resolve(root)
        ctx = root.context
        for name, t in self.inputs.items():
            ctx = ctx.narrow(name, t)
        if not self.arrive(root.id, 0, ROOT, ctx, None):
            raise PathError(f"the entry version of {fn.name} does not admit this input, so the path is empty")
        steps = 0
        while self.work:
            steps += 1
            if steps > self.max_steps:
                raise PathError("the walk of the path did not end; give versions instead")
            key = self.work.popleft()
            self.queued.discard(key)
            self.step(key)
        return self.result

    def join(self, old: Context, new: Context) -> Context:
        if self.spec.intervals:
            return old.union(new, self.spec.thresholds, widen=True).map(lambda t: t.refined())
        return old.union(new)

    def admit(self, vid: int, ctx: Context) -> Context | None:
        """The path context on entering ``vid``, or ``None`` when the version's entry context does not
        meet the path's types (spec 9.5)."""
        v = self.spec.by_id[vid]
        names = v.context.vars()
        ctx = ctx.restrict(names)
        if any(v.context.get(n).intersection(ctx.get(n)).is_bottom() for n in names):
            return None
        ctx = ctx.intersection(v.context)
        return None if ctx.is_bottom() else ctx

    def arrive(self, vid: int, cur: int, act: tuple, ctx: Context | None, via, admitted: bool = False) -> bool:
        """Enter ``vid`` in activation ``act``; ``via`` is the edge taken, recorded once the version
        admits the path."""
        if not admitted:
            ctx = self.admit(vid, ctx)
        if ctx is None:
            return False
        r = self.result
        if via is not None:
            kind, src, dst, exit, frm = via
            r.edges.add((src, dst, kind))
            if exit is not None:
                r.exits.setdefault((src, dst), set()).add(exit)
            r.transitions.add((frm, dst))
        if vid not in r.order:
            r.order.append(vid)
        key = (vid, cur, act)
        old = self.states.get(key)
        new = ctx if old is None else self.join(old, ctx)
        if old is not None and new == old:
            return True
        self.states[key] = new
        if key not in self.queued:
            self.queued.add(key)
            self.work.append(key)
        return True

    def step(self, key: tuple) -> None:
        spec = self.spec
        vid, cur, act = key
        v = spec.by_id[vid]
        ctx = self.states[key]
        for instr in v.block.instrs:
            if isinstance(instr, Assign):
                read = None
                if instr.prim == "read":
                    read, cur = self.next_read(cur)
                ctx = spec.assign_context(ctx, instr, self.adjust(read))
                if ctx.is_bottom():
                    return
            elif isinstance(instr, Move):
                ctx = spec.move_context(ctx, instr)
            elif isinstance(instr, If):
                self.branch(v, ctx, instr, cur, act)
                return
            elif isinstance(instr, Goto):
                for e in v.edges:
                    if e.kind == "goto":
                        dst = spec.by_id[e.dst]
                        self.arrive(e.dst, cur, act, spec.goto_context(ctx, instr, dst.block), ("goto", vid, e.dst, None, vid))
                return
            elif isinstance(instr, Call):
                self.call(v, ctx, instr, cur, act)
                return
            elif isinstance(instr, Return):
                read = None
                if instr.prim == "read":
                    read, cur = self.next_read(cur)
                after = spec.exit_context(ctx, instr, self.adjust(read))
                if not after.is_bottom():
                    self.exit(v, after, cur, act)
                return
            elif isinstance(instr, Fail):
                return

    def branch(self, v: Version, ctx: Context, instr: If, cur: int, act: tuple) -> None:
        yes, no, _ = self.spec.branch_contexts(ctx, instr)
        for e in v.edges:
            if e.kind == "true":
                outs = [yes]
            elif e.kind == "false":
                outs = [no]
            elif e.kind == "goto":  # a removed test: the edge of the outcome it kept
                name = self.spec.by_id[e.dst].block.name
                outs = [c for b, c in ((instr.then, yes), (instr.otherwise, no)) if b == name]
            else:
                continue
            outs = [c for c in outs if c is not None]
            if not outs:
                continue
            out = outs[0] if len(outs) == 1 else outs[0].union(outs[1])
            self.arrive(e.dst, cur, act, out, (e.kind, v.id, e.dst, None, v.id))

    # ------------------------------------------------------------ calls and returns
    def call(self, v: Version, ctx: Context, instr: Call, cur: int, act: tuple) -> None:
        spec = self.spec
        if instr.callee not in spec.program.functions:
            ctx = ctx.narrow(instr.callee, Type.of("proc"))
        call_edge = next((e for e in v.edges if e.kind == "call"), None)
        if call_edge is None or v.call is None:  # an opaque call: the return point receives any result
            for e in v.edges:
                if e.kind == "return":
                    self.arrive(e.dst, cur, act, ctx.set(RESULT, ANY), ("return", v.id, e.dst, None, v.id))
            return
        entry = spec.by_id[call_edge.dst]
        mapping = {p: (spec.type_of(ctx, a) if isinstance(a, Const) else a.name) for p, a in v.call.binds.items()}
        ectx = self.admit(entry.id, ctx.rename(mapping, entry.block.params))
        if ectx is None:
            return
        callee = (entry.id, cur, None if spec.intervals else ectx)  # the activation this call starts
        caller = (v.id, cur, act)
        self.callers.setdefault(callee, set()).add(caller)
        k = caller + (callee,)
        old = self.call_ctx.get(k)
        new = ctx if old is None else self.join(old, ctx)
        if old is None or new != old:
            self.call_ctx[k] = new
            for (x, out), after in list(self.summary.get(callee, {}).items()):  # exits already known
                self.give_back(caller, callee, x, out, after)
        self.arrive(entry.id, cur, callee, ectx, ("call", v.id, entry.id, None, v.id), admitted=True)

    def exit(self, x: Version, after: Context, cur: int, act: tuple) -> None:
        if act == ROOT:
            return  # the program returns
        known = self.summary.setdefault(act, {})
        old = known.get((x.id, cur))
        new = after if old is None else self.join(old, after)
        if old is not None and new == old:
            return
        known[(x.id, cur)] = new
        for caller in list(self.callers.get(act, ())):
            self.give_back(caller, act, x.id, cur, new)

    def give_back(self, caller: tuple, callee: tuple, x: int, cur: int, after: Context) -> None:
        """Return from exit ``x`` of activation ``callee`` to ``caller``, through its return edge for ``x``."""
        cs_id, _, act = caller
        cs = self.spec.by_id[cs_id]
        rctx = return_context_of(self.call_ctx[caller + (callee,)], cs.call.binds, after)
        for e in cs.edges:
            if e.kind == "return" and e.exit == x:
                self.arrive(e.dst, cur, act, rctx, ("return", cs.id, e.dst, x, x))
