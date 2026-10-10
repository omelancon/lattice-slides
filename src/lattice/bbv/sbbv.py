"""Static Basic Block Versioning (thesis chapter 2, algorithms 1.1 to 1.7).

The specializer runs a breadth-first traversal over *versions* (a block and a context), merges
versions when a block exceeds its limit, and reports every step through an ``emit`` callback that
the trace turns into frames. Calls are opaque here; :mod:`lv` adds the interprocedural parts.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .heuristics import HEURISTICS
from .intervals import Bound, thresholds_from, using_fixnum_bits, using_vector_bounds
from .ir import RESULT, Arg, Assign, Block, Call, Const, Fail, Function, Goto, If, Move, Program, Return, Var
from .rich import SEP, binding, code, context, join, struck, ver
from .types import ANY, Context, Type


@dataclass
class Edge:
    src: int
    dst: int
    kind: str  # goto, true, false, return, call
    exit: int | None = None  # for return edges: the exit site served

    @property
    def key(self) -> str:
        return f"{self.src}->{self.dst}:{self.kind}" + (f":{self.exit}" if self.exit is not None else "")


@dataclass
class Line:
    """One line of specialized code."""

    text: str
    line: int  # source line of the instruction
    removed: bool = False  # a test decided by the context (struck through)
    exit: int | None = None  # a ``return`` line: the exit site, for the ``[i]`` label
    callee: int | None = None  # a ``call`` line: the call site, for the entry label

    def as_dict(self) -> dict:
        d = {"text": self.text, "line": self.line}
        if self.removed:
            d["removed"] = True
        if self.exit is not None:
            d["exit"] = self.exit
        if self.callee is not None:
            d["callee"] = self.callee
        return d


@dataclass
class CallInfo:
    entry: int  # callee entry version
    ret: Block
    binds: dict[str, Arg]  # callee parameter -> argument
    context: Context  # caller context at the call


@dataclass
class Version:
    id: int
    block: Block
    context: Context
    label: str
    body: list[Line] | None = None
    context_after: Context | None = None
    merged: "Version | None" = None
    edges: list[Edge] = field(default_factory=list)
    is_entry: bool = False
    is_exit: bool = False
    generic: bool = False  # a generic entry point (root)
    call_sites: set[int] = field(default_factory=set)  # entry points only
    exit_sites: list[int] = field(default_factory=list)  # entry points only
    call: CallInfo | None = None  # call sites only
    folded: "Type | None" = None  # a call site folded by ΛV (``fold``): the constant that replaced the call
    folded_from: list[Line] | None = None  # its code before the fold
    folded_entry: int | None = None  # the callee entry it called

    @property
    def done(self) -> bool:
        return self.body is not None

    @property
    def function(self) -> str:
        return self.block.function


Emit = Callable[..., None]


class Specializer:
    """SBBV. ``emit(kind, **info)`` is called at every event of the traversal."""

    interprocedural = False

    def __init__(self, program: Program, limit: int = 2, heuristic: str = "similarity", *,
                 entry: str | None = None, limits: dict | None = None, seed: int = 0,
                 max_steps: int = 5000, emit: Emit | None = None, intervals: bool = False,
                 thresholds="machine", fixnum_bits: int = 61, vector_bounds: bool = True):
        self.program = program
        self.limit = limit
        self.intervals = intervals
        self.thresholds: list[Bound] | None = thresholds_from(thresholds, fixnum_bits)
        self.fixnum_bits = fixnum_bits
        self.vector_bounds = vector_bounds
        self.limits = dict(limits or {})
        if heuristic not in HEURISTICS:
            raise ValueError(f"unknown merge heuristic {heuristic!r}")
        self.heuristic = HEURISTICS[heuristic]
        self.rng = random.Random(seed)
        self.max_steps = max_steps
        self.emit = emit or (lambda kind, **info: None)
        self.entry_function = program.function(entry) if entry else next(iter(program.functions.values()))
        self.versions: dict[str, dict[Context, Version]] = {}  # block key -> context -> version
        self.by_id: dict[int, Version] = {}
        self.labels: dict[str, int] = {}  # block key -> versions created
        self.queue: deque[Version] = deque()
        self.roots: list[Version] = []
        self.steps = 0
        self.merges = 0
        self._reachable: set[int] | None = None
        self.truncated = False

    # ------------------------------------------------------------ versions (algorithms 1.2, 1.3)
    def block_limit(self, block: Block) -> float:
        fn = self.program.function(block.function)
        lim = self.limits.get(fn.name, fn.limit)
        if lim is None:
            return self.limit
        if lim == "none":
            return float("inf")
        return int(lim)

    def get_version(self, block: Block, context: Context) -> Version | None:
        v = self.versions.get(block.key, {}).get(context)
        if v is None:
            return None
        return self.resolve(v)

    @staticmethod
    def resolve(v: Version) -> Version:
        while v.merged is not None:
            v = v.merged
        return v

    def get_or_create(self, block: Block, context: Context) -> Version:
        context = context.restrict(block.params)
        v = self.get_version(block, context)
        if v is not None:
            return v
        n = self.labels.get(block.key, 0) + 1
        self.labels[block.key] = n
        sep = "." if block.name and block.name[-1].isdigit() else ""
        v = Version(len(self.by_id) + 1, block, context, f"{block.name}{sep}{n}")
        self.versions.setdefault(block.key, {})[context] = v
        self.by_id[v.id] = v
        self.queue.append(v)
        return v

    def reachable_versions(self, block: Block) -> list[Version]:
        r = self.reachable()
        return [v for v in self.versions.get(block.key, {}).values() if v.merged is None and v.id in r]

    # ------------------------------------------------------------ reachability
    def invalidate(self) -> None:
        self._reachable = None

    def reachable(self) -> set[int]:
        if self._reachable is None:
            seen: set[int] = set()
            stack = [self.resolve(r).id for r in self.roots]
            while stack:
                i = stack.pop()
                if i in seen:
                    continue
                seen.add(i)
                for e in self.by_id[i].edges:
                    if e.dst not in seen:
                        stack.append(e.dst)
            self._reachable = seen
        return self._reachable

    def is_reachable(self, v: Version) -> bool:
        return v.merged is None and v.id in self.reachable()

    def add_edge(self, src: Version, dst: Version, kind: str, exit: int | None = None) -> Edge | None:
        e = Edge(src.id, dst.id, kind, exit)
        if any(x.key == e.key for x in src.edges):
            return None
        src.edges.append(e)
        self.invalidate()
        return e

    def redirect(self, olds: list[Version], new: Version) -> list[tuple[Edge, int]]:
        """Point every edge into ``olds`` at ``new``. Returns the changed edges with their old target."""
        ids = {o.id for o in olds}
        changed = []
        for v in self.by_id.values():
            kept: list[Edge] = []
            for e in v.edges:
                if e.dst in ids:
                    old = e.dst
                    e.dst = new.id
                    if any(x.key == e.key for x in kept):
                        continue  # duplicate after redirection
                    changed.append((e, old))
                kept.append(e)
            v.edges = kept
        self.invalidate()
        return changed

    # ------------------------------------------------------------ main loop (algorithm 1.1)
    def start(self) -> None:
        """Queue the generic entry of every function, the entry function first (SBBV is intraprocedural)."""
        fns = [self.entry_function] + [f for f in self.program.functions.values() if f is not self.entry_function]
        for fn in fns:
            self.queue_generic_entry(fn)
        self.emit("start", versions=[r.id for r in self.roots])

    def queue_generic_entry(self, fn: Function) -> Version:
        ctx = Context({p: fn.param_types.get(p, ANY) for p in fn.params})
        if not self.intervals:
            ctx = Context({p: t.without_range() for p, t in ctx.types().items()})
        else:
            if not self.vector_bounds:  # annotations naming a vector length: widened at once
                ctx = ctx.map(lambda t: t.remap_symbols({s: None for s in t.symbols()}))
            ctx = ctx.map(lambda t: t.refined())
        v = self.get_or_create(fn.entry, ctx)
        v.is_entry = True
        v.generic = True
        if v not in self.roots:
            self.roots.append(v)
        self.invalidate()
        return v

    def run(self) -> None:
        with using_fixnum_bits(self.fixnum_bits), using_vector_bounds(self.vector_bounds):
            self._run()

    def _run(self) -> None:
        self.start()
        while self.queue:
            if self.steps >= self.max_steps:
                self.truncated = True
                break
            v = self.queue.popleft()
            if not self.is_reachable(v) or v.done:
                continue
            self.steps += 1
            self.emit("dequeue", version=v.id)
            if len(self.reachable_versions(v.block)) > self.block_limit(v.block):
                self.merge_some(v.block)
            if self.is_reachable(v) and not v.done:
                self.specialize(v)
            self.requeue()
            self.after_step()
        self.finish()
        self.emit("done")

    def requeue(self) -> list[int]:
        """Versions that were skipped while unreachable and are reachable again go back in the queue."""
        queued = {q.id for q in self.queue}
        r = self.reachable()
        back = []
        for v in self.by_id.values():
            if v.merged is None and not v.done and v.id in r and v.id not in queued:
                self.queue.append(v)
                back.append(v.id)
        return back

    def after_step(self) -> None:
        pass

    def finish(self) -> None:
        pass

    # ------------------------------------------------------------ merging (algorithm 1.7)
    def merge_some(self, block: Block) -> None:
        limit = self.block_limit(block)
        while len(self.reachable_versions(block)) > limit:
            versions = self.reachable_versions(block)
            self.emit("must-merge", block=block.key, versions=[v.id for v in versions], limit=limit)
            by_ctx = {v.context: v for v in versions}
            c1, c2 = self.heuristic(list(by_ctx), self.rng)
            pair = [by_ctx[c1], by_ctx[c2]]
            merged_ctx, widened = self.merge_contexts(pair)
            new = self.get_or_create(block, merged_ctx)
            olds = [v for v in pair if v is not new]
            for v in olds:
                v.merged = new
                if v.is_entry:
                    new.is_entry = True
                    new.call_sites |= v.call_sites
                    if v.generic:
                        new.generic = True
                if v in self.roots:
                    self.roots[self.roots.index(v)] = new
            changed = self.redirect(olds, new)
            self.merges += 1
            self.after_merge(block, olds, new)
            self.emit("merge", block=block.key, merged=[v.id for v in pair], into=new.id,
                      queued=not new.done, edges=[(e.key, old) for e, old in changed], widened=widened)

    def merge_contexts(self, pair: list[Version]) -> tuple[Context, list[str]]:
        """The context of a merge: the union of the two contexts, with intervals widened against
        the older version (the ∪∇ of the paper's algorithm 4). Returns it with the variables whose
        interval was widened."""
        older, newer = sorted(pair, key=lambda v: v.id)
        if not self.intervals:
            return older.context.union(newer.context), []
        plain = older.context.union(newer.context).map(lambda t: t.refined())
        merged = older.context.union(newer.context, self.thresholds, widen=True).map(lambda t: t.refined())
        widened = [v for v in merged.vars() if merged.get(v).range != plain.get(v).range]
        return merged, widened

    def after_merge(self, block: Block, olds: list[Version], new: Version) -> None:
        pass

    # ------------------------------------------------------------ specialization (algorithms 1.4 to 1.6)
    # ``self.intervals``: SBBV and ΛV track types only by default (paper section 3.2 adds intervals);
    # the abstract interpreter always tracks intervals.

    def type_of(self, ctx: Context, a: Arg) -> Type:
        t = a.type if isinstance(a, Const) else ctx.get(a.name)
        return t if self.intervals else t.without_range()

    def result_of(self, ctx: Context, p, args: list[Arg]) -> Type:
        """The result type of a primitive applied to ``args`` in ``ctx`` (a symbolic bound names the
        class of the argument); with intervals, the interval decides ``fx`` against ``bg``."""
        names = [ctx.rep(a.name) if isinstance(a, Var) else None for a in args]
        t = p.result_type([self.type_of(ctx, a) for a in args], names)
        return t.refined() if self.intervals else t

    def branch_contexts(self, ctx: Context, instr: If) -> tuple[Context | None, Context | None, str]:
        """The contexts of the two outcomes of a test (``None`` when an outcome is impossible), and the
        text naming the test for captions. Type tests and comparisons narrow through the primitive's
        rule; a bare variable is tested for truthiness."""
        prims = self.program.prims
        args = instr.args or [instr.arg]
        if instr.prim is not None:
            p = prims[instr.prim]
            if p.args is not None:  # the test executes: its arguments must be acceptable
                for a, req in zip(args, p.args):
                    if isinstance(a, Var):
                        ctx = ctx.narrow(a.name, req)
            if ctx.is_bottom():
                return None, None, instr.prim
            types = [self.type_of(ctx, a) for a in args]
            if p.narrow is not None:
                yes, no = p.narrow(types)
            else:
                yes, no = list(types), list(types)
            outs = []
            for narrowed in (yes, no):
                if narrowed is None:
                    outs.append(None)
                    continue
                c = ctx
                for a, t in zip(args, narrowed):
                    if isinstance(a, Var):
                        c = c.narrow(a.name, t if self.intervals else t.without_range())
                if self.intervals:
                    c = c.map(lambda t: t.refined())
                outs.append(None if c.is_bottom() else c)
            what = f"{instr.prim}({', '.join(str(a) for a in args)})"
            return outs[0], outs[1], what
        a = instr.arg
        hold = Type.of("#f").complement()
        if isinstance(a, Var):
            yes, no = ctx.narrow(a.name, hold), ctx.narrow(a.name, Type.of("#f"))
            return (None if yes.is_bottom() else yes), (None if no.is_bottom() else no), str(a)
        can_true = not a.type.intersection(hold).is_bottom()
        can_false = not a.type.intersection(Type.of("#f")).is_bottom()
        return (ctx if can_true else None), (ctx if can_false else None), str(a)

    # The transfer functions of assignments, moves and returns, shared with the walk of paths
    # (``paths.py``). ``adjust(prim, type)`` lets a caller change a primitive's result (the types of
    # ``read()`` along a path, the overflow of ``fx+?``). A context that becomes ``⊥`` means the
    # primitive cannot accept its arguments there.
    def assign_context(self, ctx: Context, instr: Assign, adjust=None) -> Context:
        p = self.program.prims[instr.prim]
        if p.args is not None:
            for a, req in zip(instr.args, p.args):
                if isinstance(a, Var):
                    ctx = ctx.narrow(a.name, req)
                elif a.type.intersection(req).is_bottom():
                    ctx = ctx.set(instr.target, Type.bottom())
        if ctx.is_bottom():
            return ctx
        t = self.result_of(ctx, p, instr.args)
        return ctx.set(instr.target, adjust(instr.prim, t) if adjust is not None else t)

    def move_context(self, ctx: Context, instr: Move) -> Context:
        ctx = ctx.set(instr.target, self.type_of(ctx, instr.source))
        if isinstance(instr.source, Var) and instr.source.name != instr.target:
            ctx = ctx.equate(instr.target, instr.source.name)
        return ctx

    def exit_context(self, ctx: Context, instr: Return, adjust=None) -> Context:
        """The context after ``return``: ``#res`` holds the returned value."""
        if instr.prim is not None:
            p = self.program.prims[instr.prim]
            for a, req in zip(instr.args, p.args or []):
                if isinstance(a, Var):
                    ctx = ctx.narrow(a.name, req)
            if ctx.is_bottom():
                return ctx
            t = self.result_of(ctx, p, instr.args)
            return ctx.set(RESULT, adjust(instr.prim, t) if adjust is not None else t)
        ctx = ctx.set(RESULT, self.type_of(ctx, instr.value))
        if isinstance(instr.value, Var) and instr.value.name != RESULT:
            ctx = ctx.equate(RESULT, instr.value.name)
        return ctx

    def goto_context(self, ctx: Context, instr: Goto, target: Block) -> Context:
        """The context sent to the target of ``goto``, its parameters rebound (a constant through
        ``type_of``: no singleton unless intervals are on)."""
        mapping: dict[str, str | Type] = {}
        for k, a in instr.binds.items():
            mapping[k] = self.type_of(ctx, a) if isinstance(a, Const) else a.name
        return ctx.rename(mapping, target.params)

    def specialize(self, v: Version) -> None:
        ctx = v.context
        body: list[Line] = []
        queued_before = {q.id for q in self.queue}
        removed = 0
        fn = self.program.function(v.function)
        halted = False
        for instr in v.block.instrs:
            kind, note = "other", ""
            if isinstance(instr, Assign):
                ctx = self.assign_context(ctx, instr)
                if ctx.is_bottom():
                    body.append(Line(instr.text, instr.line))
                    body.append(Line("fail", instr.line))
                    kind, note, halted = "fail", f"{code(instr.prim)} cannot accept these types: the block fails here", True
                else:
                    body.append(Line(instr.text, instr.line))
                    kind, note = "assign", binding(instr.target, ctx.get(instr.target))
            elif isinstance(instr, Move):
                ctx = self.move_context(ctx, instr)
                body.append(Line(instr.text, instr.line))
                kind, note = "assign", binding(instr.target, ctx.get(instr.target))
            elif isinstance(instr, If):
                ctx_true, ctx_false, what = self.branch_contexts(ctx, instr)
                can_true, can_false = ctx_true is not None, ctx_false is not None
                then_b, else_b = fn.block(instr.then), fn.block(instr.otherwise)
                if not can_true and not can_false:
                    body.append(Line(instr.text, instr.line, removed=True))
                    body.append(Line("fail", instr.line))
                    kind, note = "fail", f"{struck(what)}{SEP}neither outcome is possible: the block fails here"
                elif not can_true:
                    removed += 1
                    body.append(Line(instr.text, instr.line, removed=True))
                    body.append(Line(f"goto {instr.otherwise}", instr.line))
                    t = self.get_or_create(else_b, ctx_false)
                    self.add_edge(v, t, "goto")
                    kind, note = "if-false", f"{struck(what)} never holds here{SEP}{code('goto')} {ver(t.label, t.block.key)}"
                elif not can_false:
                    removed += 1
                    body.append(Line(instr.text, instr.line, removed=True))
                    body.append(Line(f"goto {instr.then}", instr.line))
                    t = self.get_or_create(then_b, ctx_true)
                    self.add_edge(v, t, "goto")
                    kind, note = "if-true", f"{struck(what)} always holds here{SEP}{code('goto')} {ver(t.label, t.block.key)}"
                else:
                    body.append(Line(instr.text, instr.line))
                    t1 = self.get_or_create(then_b, ctx_true)
                    t2 = self.get_or_create(else_b, ctx_false)
                    self.add_edge(v, t1, "true")
                    self.add_edge(v, t2, "false")
                    kind, note = "if", join(["both outcomes are possible, the test stays", f"{ver(t1.label, t1.block.key)} {context(t1.context)}",
                                               f"{ver(t2.label, t2.block.key)} {context(t2.context)}"])
                halted = True
            elif isinstance(instr, Goto):
                target = fn.block(instr.target)
                tctx = self.goto_context(ctx, instr, target)
                body.append(Line(instr.text, instr.line))
                t = self.get_or_create(target, tctx)
                self.add_edge(v, t, "goto")
                kind, note, halted = "goto", f"request {ver(t.label, t.block.key)} {context(t.context)}", True
            elif isinstance(instr, Call):
                lines, ctx = self.specialize_call(v, ctx, instr)
                body.extend(lines)
                kind, note, halted = "call", self.call_note, True
            elif isinstance(instr, Return):
                ctx = self.exit_context(ctx, instr)
                if ctx.is_bottom():
                    body.append(Line(instr.text, instr.line))
                    body.append(Line("fail", instr.line))
                    break
                v.is_exit = True
                body.append(Line(instr.text, instr.line, exit=v.id))
                kind, note, halted = "return", binding(RESULT, ctx.get(RESULT)), True
            elif isinstance(instr, Fail):
                body.append(Line(instr.text, instr.line))
                kind, note, halted = "fail", "the block fails here", True
            self.emit("instruction", version=v.id, shown=len(body), text=instr.text, what=kind, note=note,
                      line=instr.line)
            if halted:
                break
        v.body = body
        v.context_after = ctx
        self.invalidate()
        queued = [q.id for q in self.queue if q.id not in queued_before]
        self.after_specialize(v)
        self.emit("specialize", version=v.id, removed=removed, queued=queued,
                  targets=[e.dst for e in v.edges])

    call_note = ""

    def specialize_call(self, v: Version, ctx: Context, instr: Call) -> tuple[list[Line], Context]:
        """SBBV: the call is opaque, the return block receives an unknown result."""
        fn = self.program.function(v.function)
        ret = fn.block(instr.ret)
        if instr.callee not in self.program.functions:
            ctx = ctx.narrow(instr.callee, Type.of("proc"))
        rp = self.get_or_create(ret, ctx.set(RESULT, ANY))
        self.add_edge(v, rp, "return")
        self.call_note = f"the call is opaque{SEP}return point {ver(rp.label, rp.block.key)} receives {binding(RESULT, 'any')}"
        return [Line(instr.text, instr.line)], ctx

    def after_specialize(self, v: Version) -> None:
        pass

    # ------------------------------------------------------------ results
    def final_versions(self) -> list[Version]:
        r = self.reachable()
        return [v for v in self.by_id.values() if v.merged is None and v.id in r]

    def tests_remaining(self) -> int:
        """Tests left in reachable, specialized code: type tests, comparisons (bound checks),
        overflow and truthiness tests alike."""
        n = 0
        for v in self.final_versions():
            for line in v.body or []:
                if not line.removed and line.text.startswith("if "):
                    n += 1
        return n
