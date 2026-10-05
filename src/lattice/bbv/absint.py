"""Abstract interpretation over a fixed CFG (thesis chapter 1.1): one context per block, joined by
union with widening at block entries, narrowed at conditionals, driven by a worklist until a
fixed point. The precursor of SBBV: the graph never changes, only its annotations do.
"""
from __future__ import annotations

from collections import deque
from typing import Callable

from .intervals import Bound, thresholds_from, using_fixnum_bits
from .ir import RESULT, Assign, Block, Call, Const, Fail, Function, Goto, If, Move, Program, Return, Var
from .rich import SEP, binding, code, context, join, ty, ver
from .sbbv import Specializer
from .types import ANY, Context, Type

Emit = Callable[..., None]
_INT = Type.of("fx", "bg")


def value_text(t: Type) -> str:
    """A type for display: an integer with no known interval shows ``(-∞, ∞)``, as in the figures."""
    text = str(t)
    if t.range is None and t.bits and t.subset(_INT):
        text += " (-∞, ∞)"
    return text


class AbstractInterpreter:
    def __init__(self, program: Program, function: str | None = None, *, thresholds="machine",
                 narrowing: bool = True, fixnum_bits: int = 61, max_steps: int = 2000, emit: Emit | None = None):
        self.program = program
        self.function: Function = program.function(function) if function else next(iter(program.functions.values()))
        self.thresholds: list[Bound] | None = thresholds_from(thresholds, fixnum_bits)
        self.narrowing = narrowing
        self.fixnum_bits = fixnum_bits
        self.max_steps = max_steps
        self.emit = emit or (lambda kind, **info: None)
        self.helper = Specializer(program, intervals=True, fixnum_bits=fixnum_bits)  # transfer functions
        self.contexts: dict[str, Context | None] = {b.name: None for b in self.function.blocks.values()}  # entry contexts
        self.after: dict[str, Context | None] = {b.name: None for b in self.function.blocks.values()}  # exit contexts
        self.worklist: deque[str] = deque()
        self.queued: set[str] = set()
        self.history: dict[str, list[tuple[str, str]]] = {}  # "BLOCK.var" -> [(kind, value text)]
        self.steps = 0
        self.truncated = False
        self.dead: set[tuple[str, str]] = set()  # edges found dead (src, dst)

    # ------------------------------------------------------------ helpers
    def refine(self, ctx: Context) -> Context:
        return ctx.map(lambda t: t.refined(self.fixnum_bits))

    def enqueue(self, name: str) -> bool:
        if name in self.queued:
            return False
        self.worklist.append(name)
        self.queued.add(name)
        return True

    def record(self, block: str, ctx: Context, kinds: dict[str, str]) -> None:
        for v in ctx.vars():
            key = f"{block}.{v}"
            t = ctx.get(v)
            text = str(t.range) if t.range is not None else value_text(t)
            if not self.history.get(key) or self.history[key][-1][1] != text:
                self.history.setdefault(key, []).append((kinds.get(v, "∪"), text))

    # ------------------------------------------------------------ the algorithm
    def run(self) -> None:
        with using_fixnum_bits(self.fixnum_bits):
            self._run()

    def _run(self) -> None:
        fn = self.function
        entry = fn.entry
        ctx = Context({p: fn.param_types.get(p, ANY) for p in fn.params}).restrict(entry.params)
        ctx = self.refine(ctx)
        self.contexts[entry.name] = ctx
        self.record(entry.name, ctx, {v: "" for v in ctx.vars()})
        self.enqueue(entry.name)
        self.emit("start", block=entry.name)
        while self.worklist:
            if self.steps >= self.max_steps:
                self.truncated = True
                break
            name = self.worklist.popleft()
            self.queued.discard(name)
            self.steps += 1
            block = fn.blocks[name]
            self.emit("dequeue", block=name)
            outs = self.interpret(block, self.contexts[name])
            for succ, out, kind, what in outs:
                self.propagate(block, succ, out, kind, what)
        self.emit("done")

    def interpret(self, block: Block, ctx: Context) -> list[tuple[Block, Context | None, str, str]]:
        """Run the transfer functions of a block; returns the outgoing (successor, context or None
        when the edge is dead, edge kind, test text) tuples."""
        fn = self.function
        prims = self.program.prims
        outs: list[tuple[Block, Context | None, str, str]] = []
        for instr in block.instrs:
            note = ""
            if isinstance(instr, Assign):
                p = prims[instr.prim]
                if p.args is not None:
                    for a, req in zip(instr.args, p.args):
                        if isinstance(a, Var):
                            ctx = ctx.narrow(a.name, req)
                if ctx.is_bottom():
                    note = f"{code(instr.prim)} cannot accept these types: the block fails here"
                    self.emit("instruction", block=block.name, text=instr.text, what="fail", note=note, line=instr.line,
                              context=ctx)
                    self.after[block.name] = ctx
                    return []
                t = self.helper.result_of(ctx, p, instr.args)
                ctx = ctx.set(instr.target, t)
                note = binding(instr.target, t)
                kind = "assign"
            elif isinstance(instr, Move):
                ctx = ctx.set(instr.target, self.helper.type_of(ctx, instr.source))
                if isinstance(instr.source, Var) and instr.source.name != instr.target:
                    ctx = ctx.equate(instr.target, instr.source.name)
                note, kind = binding(instr.target, ctx.get(instr.target)), "assign"
            elif isinstance(instr, If):
                yes, no, what = self.helper.branch_contexts(ctx, instr)
                if not self.narrowing:  # outcomes stay possible or not, but nothing is learned
                    yes = ctx if yes is not None else None
                    no = ctx if no is not None else None
                yes = self.refine(yes) if yes is not None else None
                no = self.refine(no) if no is not None else None
                then_b, else_b = fn.block(instr.then), fn.block(instr.otherwise)
                outs.append((then_b, yes.restrict(then_b.params) if yes is not None else None, "true", what))
                outs.append((else_b, no.restrict(else_b.params) if no is not None else None, "false", what))
                parts = []
                if yes is None:
                    parts.append(f"{code(what)} never holds")
                elif no is None:
                    parts.append(f"{code(what)} always holds")
                else:
                    parts.append("both outcomes are possible")
                note, kind = join(parts), "if"
            elif isinstance(instr, Goto):
                target = fn.block(instr.target)
                mapping = {k: (a.type if isinstance(a, Const) else a.name) for k, a in instr.binds.items()}
                tctx = ctx.rename(mapping, target.params)
                outs.append((target, tctx, "goto", ""))
                note, kind = f"{ver(target.name, target.key)} receives {context(tctx)}", "goto"
            elif isinstance(instr, Call):
                ret = fn.block(instr.ret)
                if instr.callee not in self.program.functions:
                    ctx = ctx.narrow(instr.callee, Type.of("proc"))
                outs.append((ret, ctx.set(RESULT, ANY).restrict(ret.params), "return", ""))
                note, kind = f"the call is opaque{SEP}{binding(RESULT, 'any')} at {ver(ret.name, ret.key)}", "call"
            elif isinstance(instr, Return):
                if instr.prim is not None:
                    p = prims[instr.prim]
                    for a, req in zip(instr.args, p.args or []):
                        if isinstance(a, Var):
                            ctx = ctx.narrow(a.name, req)
                    t = self.helper.result_of(ctx, p, instr.args)
                else:
                    t = self.helper.type_of(ctx, instr.value)
                ctx = ctx.set(RESULT, t)
                note, kind = f"returns {ty(t)}", "return"
            elif isinstance(instr, Fail):
                note, kind = "the block fails here", "fail"
            self.emit("instruction", block=block.name, text=instr.text, what=kind, note=note, line=instr.line, context=ctx)
        self.after[block.name] = ctx
        return outs

    def propagate(self, src: Block, dst: Block, out: Context | None, kind: str, what: str) -> None:
        if out is None:
            self.dead.add((src.name, dst.name))
            self.emit("propagate", src=src.name, dst=dst.name, edge=kind, result="dead", what=what, changes=[])
            return
        self.dead.discard((src.name, dst.name))
        old = self.contexts[dst.name]
        if old is None:
            self.contexts[dst.name] = out
            self.record(dst.name, out, {v: "" for v in out.vars()})
            self.enqueue(dst.name)
            self.emit("propagate", src=src.name, dst=dst.name, edge=kind, result="first", what=what,
                      changes=[(v, None, str(out.get(v)), str(out.get(v)), False) for v in out.vars()])
            return
        plain = self.refine(old.union(out))
        joined = self.refine(old.union(out, self.thresholds, widen=True))
        if joined == old:
            self.emit("propagate", src=src.name, dst=dst.name, edge=kind, result="unchanged", what=what, changes=[])
            return
        changes, kinds = [], {}
        for v in joined.vars():
            if joined.get(v) != old.get(v):
                widened = joined.get(v).range != plain.get(v).range
                kinds[v] = "∇" if widened else "∪"
                changes.append((v, value_text(old.get(v)), value_text(out.get(v)), value_text(joined.get(v)), widened))
        self.contexts[dst.name] = joined
        self.record(dst.name, joined, kinds)
        requeued = self.enqueue(dst.name)
        self.emit("propagate", src=src.name, dst=dst.name, edge=kind, what=what,
                  result="widened" if any(c[4] for c in changes) else "union", changes=changes, queued=requeued)
