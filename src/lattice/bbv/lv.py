"""Lambda Versioning (thesis chapter 3, algorithms 2.1 to 2.10): SBBV plus specialized entry points
for call sites (forward) and specialized return points for the exit sites reachable from each entry
(backward). Written as a subclass of the SBBV specializer, like the thesis presents it as a diff.
"""
from __future__ import annotations

from .ir import RESULT, Assign, Call, Const, Fail, Function, Goto, If, Move, Return, Var
from .prims import DEFAULT_PRIMS
from .rich import SEP, binding, context, join, ver
from .sbbv import CallInfo, Line, Specializer, Version
from .types import ANY, Context, Type

INTRA = ("goto", "true", "false", "return")
# Primitives with a side effect (I/O, mutation, a fresh random value): a callee using one is never folded
EFFECTS = frozenset({"display", "read", "random", "vector-set!", "##vector-set!"})
_INT = Type.of("fx", "bg")


def constant_text(t: Type) -> str | None:
    """The constant a type stands for, as written in a program (``1``, ``#t``, ``'()``), or ``None`` when
    the type holds more than one value: an integer with a singleton interval, ``#t``, ``#f`` or ``nil``."""
    if t.range is not None and t.range.is_singleton() and not t.range.symbols() and t.subset(_INT):
        return str(t.range.lo)
    for name, text in (("#t", "#t"), ("#f", "#f"), ("nil", "'()")):
        if t.is_exactly(name):
            return text
    return None


def return_context_of(ctx: Context, binds: dict, after: Context) -> Context:
    """``callContext ∩ exitSite.contextAfter`` (algorithm 2.8), from the caller's context at the call,
    the bindings of the callee's parameters and the callee's context after its exit; also used by
    the walk of paths. A symbolic bound of the callee names a callee variable: it is translated to
    the caller's argument when the variable is a parameter bound to a variable, and widened otherwise."""
    names = {after.rep(p): ctx.rep(a.name) for p, a in binds.items() if isinstance(a, Var) and p in after}
    back = {v: names.get(v) for v in after.vars()}
    for p, a in binds.items():
        if isinstance(a, Var):
            ctx = ctx.narrow(a.name, after.get(p).remap_symbols(back))
    ctx = ctx.set(RESULT, after.get(RESULT).remap_symbols(back))
    for p, a in binds.items():
        if isinstance(a, Var) and after.same(RESULT, p):
            ctx = ctx.equate(RESULT, a.name)
    return ctx


class LambdaVersioning(Specializer):
    interprocedural = True

    def __init__(self, *args, fold: bool = False, generic_entry: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fold = fold  # constant folding at call sites (thesis section 4.2)
        self.generic_entry = generic_entry  # queue the generic entries of the other functions when the queue empties
        self.folds = 0
        self.generic_done = False
        self.return_index: dict[int, int] = {}  # exit version -> index of its return point

    # ------------------------------------------------------------ traversal order (as in the implementation)
    def start(self) -> None:
        self.queue_generic_entry(self.entry_function)
        self.emit("start", versions=[r.id for r in self.roots])

    def after_step(self) -> None:
        if self.fold:
            self.fold_call_sites()
        if not self.queue and not self.generic_done:
            self.generic_done = True
            if not self.generic_entry:  # only the entry function's generic entry, and the entries calls create
                return
            others = [f for f in self.program.functions.values() if f is not self.entry_function]
            before = set(self.by_id)
            ids = [self.queue_generic_entry(f).id for f in others]
            if ids:
                self.sync_all()
                self.requeue()
                self.emit("generic-entries", versions=ids, created=[i for i in ids if i not in before])

    # ------------------------------------------------------------ calls (algorithm 2.7)
    def callee_of(self, ctx: Context, instr: Call) -> Function | None:
        if instr.callee in self.program.functions:
            return self.program.functions[instr.callee]
        t = ctx.get(instr.callee)
        if t.procs is not None and len(t.procs) == 1 and t.is_exactly("proc"):
            name = next(iter(t.procs))
            return self.program.functions.get(name)
        return None

    def specialize_call(self, v: Version, ctx: Context, instr: Call) -> tuple[list[Line], Context]:
        fn = self.program.function(v.function)
        ret = fn.block(instr.ret)
        callee = self.callee_of(ctx, instr)
        if instr.callee not in self.program.functions:
            ctx = ctx.narrow(instr.callee, Type.of("proc"))
        if callee is None:
            rp = self.get_or_create(ret, ctx.set(RESULT, ANY))
            self.add_edge(v, rp, "return")
            self.call_note = f"the callee is unknown, generic call{SEP}return point {ver(rp.label, rp.block.key)} receives {binding(RESULT, 'any')}"
            return [Line(instr.text, instr.line)], ctx
        binds = dict(zip(callee.params, instr.args))
        # a constant argument through type_of: no singleton interval unless intervals are on
        mapping = {p: (self.type_of(ctx, a) if isinstance(a, Const) else a.name) for p, a in binds.items()}
        ectx = ctx.rename(mapping, callee.entry.params)
        created = self.get_version(callee.entry, ectx.restrict(callee.entry.params)) is None
        entry = self.get_or_create(callee.entry, ectx)
        entry.is_entry = True
        entry.call_sites.add(v.id)
        v.call = CallInfo(entry.id, ret, binds, ctx)
        self.add_edge(v, entry, "call")
        self.emit("entry", call_site=v.id, entry=entry.id, created=created)
        args = ", ".join(str(a) for a in instr.args)
        line = Line(f"call {callee.name}[{{callee}}]({args}) -> {instr.ret}", instr.line)
        line.callee = v.id  # resolved through the call site once labels are final
        self.reconcile_call_site(v)
        n = len([e for e in v.edges if e.kind == "return"])
        self.call_note = join([f"{'creates' if created else 'uses'} entry point {ver(entry.label, entry.block.key)} of {callee.name}",
                               context(entry.context),
                               f"{n} return point{'s' if n > 1 else ''} for its known exit sites" if n else "no exit site is known yet"])
        return [line], ctx

    # ------------------------------------------------------------ return points (algorithms 2.8, 2.9)
    def return_context(self, cs: Version, exit: Version) -> Context:
        """``callContext ∩ exitSite.contextAfter`` (algorithm 2.8)."""
        return return_context_of(cs.call.context, cs.call.binds, exit.context_after)

    def reconcile_call_site(self, cs: Version) -> tuple[list, list]:
        """Make the return edges of a call site match the exit sites of its callee entry."""
        entry = self.resolve(self.by_id[cs.call.entry])
        cs.call.entry = entry.id
        wanted: dict[tuple[int, int], Version] = {}
        for x in entry.exit_sites:
            exit = self.by_id[x]
            rctx = self.return_context(cs, exit)
            if rctx.is_bottom():
                continue
            rp = self.get_or_create(cs.call.ret, rctx)
            wanted[(rp.id, x)] = rp
        have = {(e.dst, e.exit): e for e in cs.edges if e.kind == "return"}
        added, removed = [], []
        for key, rp in wanted.items():
            if key not in have:
                self.add_edge(cs, rp, "return", exit=key[1])
                added.append(key)
        for key, e in have.items():
            if key not in wanted:
                cs.edges.remove(e)
                removed.append(key)
        if added or removed:
            self.invalidate()
            self.emit("return-points", call_site=cs.id, entry=entry.id, added=added, removed=removed)
        return added, removed

    def exits_from(self, entry: Version) -> list[int]:
        """Exit sites reachable from an entry point inside its function (multi-source reachability)."""
        seen: set[int] = set()
        out: list[int] = []
        stack = [entry.id]
        reach = self.reachable()
        while stack:
            i = stack.pop()
            if i in seen or i not in reach:
                continue
            seen.add(i)
            v = self.by_id[i]
            if v.is_exit:
                out.append(i)
            for e in v.edges:
                if e.kind in INTRA:
                    stack.append(e.dst)
        return sorted(out)

    def sync_all(self) -> None:
        """Bring every entry's exit sites and every call site's return points up to date, until stable.
        Additions are applied before removals, as the thesis requires for termination."""
        for _ in range(200):
            changed = False
            for phase in ("add", "remove"):
                for v in list(self.by_id.values()):
                    if not v.is_entry or not self.is_reachable(v):
                        continue
                    exits = self.exits_from(v)
                    if phase == "add":
                        new = [x for x in exits if x not in v.exit_sites]
                        if not new:
                            continue
                        v.exit_sites.extend(new)
                    else:
                        gone = [x for x in v.exit_sites if x not in exits]
                        if not gone:
                            continue
                        v.exit_sites = [x for x in v.exit_sites if x not in gone]
                    changed = True
                    for cs_id in sorted(v.call_sites):
                        cs = self.by_id[cs_id]
                        if cs.merged is None and self.is_reachable(cs) and cs.call is not None:
                            self.reconcile_call_site(cs)
            if not changed:
                return

    # ------------------------------------------------------------ constant folding (thesis section 4.2)
    def fold_call_sites(self) -> None:
        """Replace by its constant every call whose result is known exactly and whose callee has no side
        effect, as soon as both are known: once the versions the entry reaches are all specialized."""
        for cs in sorted(self.by_id.values(), key=lambda v: v.id):
            if cs.call is None or not cs.done or not self.is_reachable(cs):
                continue
            found = self.foldable(cs)
            if found is not None:
                self.apply_fold(cs, *found)

    def callee_region(self, entry: Version) -> list[int] | None:
        """The versions an entry point reaches: its function's versions along goto, test and return edges,
        and the callees it calls, through their entries. ``None`` while one of them is not specialized."""
        seen: set[int] = set()
        stack = [entry.id]
        reach = self.reachable()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            v = self.by_id[i]
            if v.merged is not None or i not in reach or not v.done:
                return None
            seen.add(i)
            for e in v.edges:
                if e.kind in INTRA or e.kind == "call":
                    stack.append(e.dst)
        return sorted(seen)

    def pure_prim(self, ctx: Context, name: str, args) -> bool:
        """A primitive without side effect that cannot raise an exception here: its arguments already have
        the types it requires. A primitive declared by the deck (``prims``) is assumed to have effects."""
        p = self.program.prims[name]
        if name in EFFECTS or p is not DEFAULT_PRIMS.get(name):
            return False
        return all(self.type_of(ctx, a).subset(req) for a, req in zip(args, p.args or []))

    def no_side_effect(self, v: Version) -> bool:
        """The instructions of a specialized version, replayed on its context: no effect, no unknown
        callee, no failure (a primitive whose argument may have the wrong type could raise one)."""
        if any(line.text == "fail" for line in v.body or []):
            return False
        ctx = v.context
        for instr in v.block.instrs:
            if isinstance(instr, Assign):
                if not self.pure_prim(ctx, instr.prim, instr.args):
                    return False
                ctx = self.assign_context(ctx, instr)
                if ctx.is_bottom():
                    return False
            elif isinstance(instr, Move):
                ctx = self.move_context(ctx, instr)
            elif isinstance(instr, If):
                return instr.prim is None or self.pure_prim(ctx, instr.prim, instr.args)
            elif isinstance(instr, Return):
                return instr.prim is None or self.pure_prim(ctx, instr.prim, instr.args)
            elif isinstance(instr, Call):
                return self.callee_of(ctx, instr) is not None  # a known callee is part of the region
            elif isinstance(instr, Goto):
                return True
            elif isinstance(instr, Fail):
                return False
        return True

    def foldable(self, cs: Version):
        """``(entry, region, return point, constant, type)`` when the call of ``cs`` can be replaced by a
        constant: its callee entry reaches no side effect, every exit site it reaches returns the same
        constant to ``cs``, and they all return to one return point. ``None`` otherwise."""
        entry = self.resolve(self.by_id[cs.call.entry])
        region = self.callee_region(entry)
        if region is None or cs.id in region:  # not specialized yet, or recursive
            return None
        if not all(self.no_side_effect(self.by_id[i]) for i in region):
            return None
        rets = [e for e in cs.edges if e.kind == "return"]
        if not rets or {e.exit for e in rets} != set(entry.exit_sites) or len({e.dst for e in rets}) != 1:
            return None
        texts, t = set(), None
        for x in entry.exit_sites:
            r = self.return_context(cs, self.by_id[x]).get(RESULT)
            texts.add(constant_text(r))
            t = r if t is None else t.union(r)
        if len(texts) != 1 or None in texts:
            return None
        return entry, region, self.by_id[rets[0].dst], texts.pop(), t

    def apply_fold(self, cs: Version, entry: Version, region: list[int], rp: Version, text: str, t: Type) -> None:
        """Three events: the region has no side effect, the call site receives a constant, then the fold:
        the call becomes ``#res = constant`` and a ``goto`` to the return point, and the callee versions
        that only this call reached become unreachable."""
        self.emit("fold-pure", call_site=cs.id, entry=entry.id, versions=list(region))
        self.emit("fold-site", call_site=cs.id, entry=entry.id, return_point=rp.id, value=text, type=t)
        call_line = cs.body[-1]
        cs.folded, cs.folded_from, cs.folded_entry = t, list(cs.body), entry.id
        cs.body = cs.body[:-1] + [Line(f"{RESULT} = {text}", call_line.line), Line(f"goto {cs.call.ret.name}", call_line.line)]
        cs.edges = [e for e in cs.edges if e.kind not in ("call", "return")]
        cs.context_after = cs.context_after.set(RESULT, t)
        entry.call_sites.discard(cs.id)
        cs.call = None
        self.add_edge(cs, rp, "goto")
        self.invalidate()
        self.folds += 1
        self.sync_all()
        self.requeue()
        self.emit("fold", call_site=cs.id, entry=entry.id, return_point=rp.id, value=text, versions=list(region))

    # ------------------------------------------------------------ hooks
    def after_specialize(self, v: Version) -> None:
        if v.is_exit:
            self.emit("exit", version=v.id)
        self.sync_all()

    def after_merge(self, block, olds, new) -> None:
        for old in olds:
            if old.call is not None:
                entry = self.by_id.get(old.call.entry)
                if entry is not None:
                    entry.call_sites.discard(old.id)
        self.sync_all()

    def finish(self) -> None:
        """Index allocation: one index per distinct exit contract of a function, reachable exits first."""
        for fn in self.program.functions.values():
            exits = [v for v in self.by_id.values() if v.function == fn.name and v.is_exit]
            reach = self.reachable()
            exits.sort(key=lambda v: (0 if (v.merged is None and v.id in reach) else 1, v.id))
            contracts: dict = {}
            for v in exits:
                c = v.context_after.restrict(list(fn.params) + [RESULT])
                idx = contracts.setdefault(c, len(contracts))
                self.return_index[v.id] = idx
