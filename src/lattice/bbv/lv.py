"""Lambda Versioning (thesis chapter 3, algorithms 2.1 to 2.10): SBBV plus specialized entry points
for call sites (forward) and specialized return points for the exit sites reachable from each entry
(backward). Written as a subclass of the SBBV specializer, like the thesis presents it as a diff.
"""
from __future__ import annotations

from .ir import RESULT, Call, Const, Function, Var
from .rich import SEP, binding, context, join, ver
from .sbbv import CallInfo, Line, Specializer, Version
from .types import ANY, Context, Type

INTRA = ("goto", "true", "false", "return")


class LambdaVersioning(Specializer):
    interprocedural = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.generic_done = False
        self.return_index: dict[int, int] = {}  # exit version -> index of its return point

    # ------------------------------------------------------------ traversal order (as in the implementation)
    def start(self) -> None:
        self.queue_generic_entry(self.entry_function)
        self.emit("start", versions=[r.id for r in self.roots])

    def after_step(self) -> None:
        if not self.queue and not self.generic_done:
            self.generic_done = True
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
        mapping = {p: (a.type if isinstance(a, Const) else a.name) for p, a in binds.items()}
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
        ctx = cs.call.context
        after = exit.context_after
        for p, a in cs.call.binds.items():
            if isinstance(a, Var):
                ctx = ctx.narrow(a.name, after.get(p))
        ctx = ctx.set(RESULT, after.get(RESULT))
        for p, a in cs.call.binds.items():
            if isinstance(a, Var) and after.same(RESULT, p):
                ctx = ctx.equate(RESULT, a.name)
        return ctx

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
