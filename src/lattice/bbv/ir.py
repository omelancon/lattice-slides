"""Programs for basic block versioning: functions, blocks and instructions, the text syntax
(``.bbv`` files) and the liveness analysis that gives blocks their parameters.

Text syntax, one instruction per line (``;`` starts a comment)::

    function find(p, lst)
    A:  if pair?(lst) goto B else goto L
    L:  return #f
    B:  if procedure?(p) goto D else goto E
    F:  tmp = car(lst)
        call p(tmp) -> G
    G:  if #res goto H else goto J
    J2: lst = cdr(lst)
        goto A

Blocks are ``LABEL:`` or ``LABEL(params):``; without a list the parameters are the variables live
at the block. ``goto A(i=tmp)`` rebinds a parameter by name (positional only when ``A`` declares its
parameters). ``call f(args) -> K`` continues at ``K`` with the result in ``#res``. A function line
may carry ``limit=N`` (or ``none``) and ``hidden``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

from .prims import DEFAULT_PRIMS, Prim, prim_from_spec
from .types import Type


class ProgramError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


# ------------------------------------------------------------------ operands

@dataclass(frozen=True)
class Var:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Const:
    text: str
    type: Type

    def __str__(self) -> str:
        return self.text


Arg = Union[Var, Const]


def parse_arg(text: str) -> Arg:
    text = text.strip()
    if text in ("#t", "#true"):
        return Const("#t", Type.of("#t"))
    if text in ("#f", "#false"):
        return Const("#f", Type.of("#f"))
    if text in ("nil", "'()", "()"):
        return Const("'()", Type.of("nil"))
    if re.fullmatch(r"-?\d+", text):
        return Const(text, Type.of("fx"))
    if re.fullmatch(r"-?\d+\.\d*|-?\d*\.\d+|-?\d+e-?\d+", text):
        return Const(text, Type.of("fl"))
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return Const(text, Type.of("str"))
    if re.fullmatch(r"[^\s(),=]+", text):
        return Var(text)
    raise ProgramError(f"cannot read operand {text!r}")


def _split_args(text: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [a.strip() for a in out]


# ------------------------------------------------------------------ instructions

@dataclass
class Instr:
    text: str = ""
    line: int = 0

    def uses(self) -> list[str]:
        return []

    def defines(self) -> str | None:
        return None

    def terminates(self) -> bool:
        return False


@dataclass
class Assign(Instr):
    target: str = ""
    prim: str = ""
    args: list[Arg] = field(default_factory=list)

    def uses(self):
        return [a.name for a in self.args if isinstance(a, Var)]

    def defines(self):
        return self.target


@dataclass
class Move(Instr):
    target: str = ""
    source: Arg = None

    def uses(self):
        return [self.source.name] if isinstance(self.source, Var) else []

    def defines(self):
        return self.target


@dataclass
class If(Instr):
    prim: str | None = None  # a type test, or None for a truthiness test of ``arg``
    arg: Arg = None
    then: str = ""
    otherwise: str = ""

    def uses(self):
        return [self.arg.name] if isinstance(self.arg, Var) else []

    def terminates(self):
        return True


@dataclass
class Goto(Instr):
    target: str = ""
    binds: dict[str, Arg] = field(default_factory=dict)  # target parameter -> argument
    positional: list[Arg] | None = None  # resolved into ``binds`` once the target is known

    def uses(self):
        return [a.name for a in self.binds.values() if isinstance(a, Var)]

    def terminates(self):
        return True


@dataclass
class Call(Instr):
    callee: str = ""  # a function name or a variable
    args: list[Arg] = field(default_factory=list)
    ret: str = ""  # return block
    passed: list[str] | None = None  # variables named in ``-> K(vars)``

    def uses(self):
        return [a.name for a in self.args if isinstance(a, Var)] + [self.callee]

    def terminates(self):
        return True


@dataclass
class Return(Instr):
    value: Arg = None  # ``return v``
    prim: str | None = None  # ``return prim(args)``
    args: list[Arg] = field(default_factory=list)

    def uses(self):
        if self.prim is not None:
            return [a.name for a in self.args if isinstance(a, Var)]
        return [self.value.name] if isinstance(self.value, Var) else []

    def terminates(self):
        return True


@dataclass
class Fail(Instr):
    def terminates(self):
        return True


RESULT = "#res"


# ------------------------------------------------------------------ blocks and functions

@dataclass
class Block:
    name: str
    function: str
    instrs: list[Instr] = field(default_factory=list)
    params: list[str] = field(default_factory=list)  # live variables (or the explicit list)
    explicit: bool = False
    line: int = 0
    is_return: bool = False  # reached by a call; ``#res`` is bound

    @property
    def key(self) -> str:
        return f"{self.function}/{self.name}"

    def successors(self) -> list[str]:
        last = self.instrs[-1] if self.instrs else None
        if isinstance(last, If):
            return [last.then, last.otherwise]
        if isinstance(last, Goto):
            return [last.target]
        if isinstance(last, Call):
            return [last.ret]
        return []

    def text_lines(self) -> list[str]:
        return [i.text for i in self.instrs]


@dataclass
class Function:
    name: str
    params: list[str]
    blocks: dict[str, Block] = field(default_factory=dict)
    limit: int | None | str = None  # None: the program's limit; "none": unlimited
    hidden: bool = False
    line: int = 0

    @property
    def entry(self) -> Block:
        return next(iter(self.blocks.values()))

    def block(self, name: str) -> Block:
        if name not in self.blocks:
            raise ProgramError(f"function {self.name!r} has no block {name!r}")
        return self.blocks[name]


@dataclass
class Program:
    functions: dict[str, Function] = field(default_factory=dict)
    prims: dict[str, Prim] = field(default_factory=lambda: dict(DEFAULT_PRIMS))
    source: list[str] = field(default_factory=list)  # text lines, for followers

    def function(self, name: str) -> Function:
        if name not in self.functions:
            raise ProgramError(f"unknown function {name!r}")
        return self.functions[name]

    def block(self, key: str) -> Block:
        fn, _, name = key.partition("/")
        return self.function(fn).block(name)

    def add_prims(self, spec: dict) -> None:
        for name, s in (spec or {}).items():
            self.prims[name] = prim_from_spec(name, s if isinstance(s, dict) else {"result": s})

    def finalize(self) -> "Program":
        """Resolve labels and positional rebindings, then compute block parameters."""
        for fn in self.functions.values():
            _resolve(self, fn)
            _liveness(self, fn)
        return self


# ------------------------------------------------------------------ text syntax

_FUNCTION = re.compile(r"^function\s+([^\s(]+)\s*\(([^)]*)\)\s*(.*)$")
_LABEL = re.compile(r"^([A-Za-z_$][\w$.'-]*)(\(([^)]*)\))?:\s*(.*)$")
_ASSIGN = re.compile(r"^([^\s=]+)\s*=\s*(.+)$")
_PRIMCALL = re.compile(r"^([^\s(]+)\((.*)\)$")
_IF = re.compile(r"^if\s+(.+?)\s+goto\s+(\S+)\s+else\s+goto\s+(\S+)$")
_GOTO = re.compile(r"^goto\s+([^\s(]+)\s*(\((.*)\))?$")
_CALL = re.compile(r"^call\s+([^\s(]+)\((.*)\)\s*->\s*([^\s(]+)\s*(\((.*)\))?$")
_RETURN = re.compile(r"^return\s+(.+)$")


def parse(text: str) -> Program:
    prog = Program(source=text.split("\n"))
    fn: Function | None = None
    block: Block | None = None
    for no, raw in enumerate(prog.source, 1):
        line = raw.split(";", 1)[0].rstrip()
        if not line.strip():
            continue
        m = _FUNCTION.match(line.strip())
        if m:
            name, params, rest = m.group(1), [p.strip() for p in m.group(2).split(",") if p.strip()], m.group(3)
            if name in prog.functions:
                raise ProgramError(f"function {name!r} defined twice", no)
            fn = Function(name, params, line=no)
            for opt in rest.split():
                if opt == "hidden":
                    fn.hidden = True
                elif opt.startswith("limit="):
                    v = opt[6:]
                    fn.limit = "none" if v == "none" else int(v)
                else:
                    raise ProgramError(f"unknown function option {opt!r}", no)
            prog.functions[name] = fn
            block = None
            continue
        if fn is None:
            raise ProgramError("instruction outside a function", no)
        m = _LABEL.match(line.strip())
        if m and not line.strip().startswith(("if ", "call ", "goto ", "return ")):
            label, plist, rest = m.group(1), m.group(3), m.group(4)
            if label in fn.blocks:
                raise ProgramError(f"block {label!r} defined twice in {fn.name!r}", no)
            block = Block(label, fn.name, line=no)
            if plist is not None:
                block.params = [p.strip() for p in plist.split(",") if p.strip()]
                block.explicit = True
            fn.blocks[label] = block
            if not rest.strip():
                continue
            line = rest
        if block is None:
            raise ProgramError("instruction before the first block label", no)
        if block.instrs and block.instrs[-1].terminates():
            raise ProgramError(f"block {block.name!r} continues after {block.instrs[-1].text!r}", no)
        block.instrs.append(_parse_instr(line.strip(), no))
    for f in prog.functions.values():
        if not f.blocks:
            raise ProgramError(f"function {f.name!r} has no block", f.line)
        for b in f.blocks.values():
            if not b.instrs or not b.instrs[-1].terminates():
                raise ProgramError(f"block {b.name!r} of {f.name!r} does not end with if, goto, call, return or fail",
                                   b.line)
    return prog.finalize()


def _parse_instr(text: str, no: int) -> Instr:
    try:
        if text == "fail":
            return Fail(text, no)
        m = _RETURN.match(text)
        if m:
            pm = _PRIMCALL.match(m.group(1).strip())
            if pm:
                return Return(text, no, prim=pm.group(1), args=[parse_arg(a) for a in _split_args(pm.group(2))])
            return Return(text, no, value=parse_arg(m.group(1)))
        m = _IF.match(text)
        if m:
            test, then, otherwise = m.group(1).strip(), m.group(2), m.group(3)
            pm = _PRIMCALL.match(test)
            if pm:
                args = _split_args(pm.group(2))
                if len(args) != 1:
                    raise ProgramError("a type test takes one argument", no)
                return If(text, no, prim=pm.group(1), arg=parse_arg(args[0]), then=then, otherwise=otherwise)
            return If(text, no, prim=None, arg=parse_arg(test), then=then, otherwise=otherwise)
        m = _GOTO.match(text)
        if m:
            g = Goto(text, no, target=m.group(1))
            if m.group(3) is not None and m.group(3).strip():
                parts = _split_args(m.group(3))
                if all("=" in p for p in parts):
                    for p in parts:
                        k, _, v = p.partition("=")
                        g.binds[k.strip()] = parse_arg(v)
                elif any("=" in p for p in parts):
                    raise ProgramError("mix of named and positional goto arguments", no)
                else:
                    g.positional = [parse_arg(p) for p in parts]
            return g
        m = _CALL.match(text)
        if m:
            c = Call(text, no, callee=m.group(1), args=[parse_arg(a) for a in _split_args(m.group(2))],
                     ret=m.group(3))
            if m.group(5) is not None:
                c.passed = [v.strip() for v in m.group(5).split(",") if v.strip()]
            return c
        m = _ASSIGN.match(text)
        if m:
            target, rhs = m.group(1), m.group(2).strip()
            pm = _PRIMCALL.match(rhs)
            if pm:
                return Assign(text, no, target=target, prim=pm.group(1), args=[parse_arg(a) for a in _split_args(pm.group(2))])
            return Move(text, no, target=target, source=parse_arg(rhs))
    except ProgramError as e:
        if e.line is None:
            raise ProgramError(str(e), no) from None
        raise
    raise ProgramError(f"cannot parse {text!r}", no)


# ------------------------------------------------------------------ resolution and liveness

def _resolve(prog: Program, fn: Function) -> None:
    for b in fn.blocks.values():
        for i in b.instrs:
            if isinstance(i, (If,)):
                for t in (i.then, i.otherwise):
                    if t not in fn.blocks:
                        raise ProgramError(f"unknown block {t!r}", i.line)
            elif isinstance(i, Goto):
                if i.target not in fn.blocks:
                    raise ProgramError(f"unknown block {i.target!r}", i.line)
                target = fn.blocks[i.target]
                if i.positional is not None:
                    if not target.explicit:
                        raise ProgramError(f"positional goto arguments need {i.target!r} to declare its parameters", i.line)
                    if len(i.positional) != len(target.params):
                        raise ProgramError(f"{i.target!r} takes {len(target.params)} parameters", i.line)
                    i.binds = dict(zip(target.params, i.positional))
                    i.positional = None
                for k in i.binds:
                    if k in fn.params:
                        raise ProgramError(f"cannot rebind function parameter {k!r} (use a block parameter)", i.line)
                    if target.explicit and k not in target.params:
                        raise ProgramError(f"{i.target!r} has no parameter {k!r}", i.line)
            elif isinstance(i, Call):
                if i.ret not in fn.blocks:
                    raise ProgramError(f"unknown return block {i.ret!r}", i.line)
                fn.blocks[i.ret].is_return = True
            elif isinstance(i, (Assign, Return)) and getattr(i, "prim", None) is not None:
                if i.prim not in prog.prims:
                    raise ProgramError(f"unknown primitive {i.prim!r}", i.line)
            elif isinstance(i, If) and i.prim is not None:
                pass
    for b in fn.blocks.values():
        for i in b.instrs:
            if isinstance(i, If) and i.prim is not None:
                p = prog.prims.get(i.prim)
                if p is None or p.test is None:
                    raise ProgramError(f"{i.prim!r} is not a type test", i.line)


def _liveness(prog: Program, fn: Function) -> None:
    """Backward liveness; a block's parameters are its live-in variables plus the function's."""
    blocks = list(fn.blocks.values())

    def uses(i: Instr) -> set[str]:
        return {u for u in i.uses() if not (isinstance(i, Call) and u == i.callee and u in prog.functions)}

    live_in: dict[str, set[str]] = {b.name: set() for b in blocks}
    changed = True
    while changed:
        changed = False
        for b in reversed(blocks):
            live: set[str] = set()
            last = b.instrs[-1]
            if isinstance(last, If):
                live |= live_in[last.then] | live_in[last.otherwise]
            elif isinstance(last, Goto):
                t = fn.blocks[last.target]
                target_live = set(t.params) if t.explicit else live_in[last.target]
                live |= target_live - set(last.binds)
            elif isinstance(last, Call):
                k = fn.blocks[last.ret]
                if last.passed is not None:
                    live |= set(last.passed)
                else:
                    live |= (set(k.params) if k.explicit else live_in[last.ret]) - {RESULT}
            for i in reversed(b.instrs):
                d = i.defines()
                if d is not None:
                    live.discard(d)
                live |= uses(i)
            live -= set(fn.params)
            if not b.is_return:
                live.discard(RESULT)
            if live != live_in[b.name]:
                live_in[b.name] = live
                changed = True
    entry = fn.entry
    order = _var_order(fn)
    for b in blocks:
        extra = live_in[b.name]
        if b.explicit:
            missing = extra - set(b.params) - set(fn.params) - ({RESULT} if b.is_return else set())
            if missing:
                raise ProgramError(f"block {b.name!r} uses {sorted(missing)} without declaring them", b.line)
            names = list(fn.params) + [p for p in b.params if p not in fn.params]
        else:
            names = list(fn.params) + sorted(extra - set(fn.params), key=order.index)
        if b.is_return and RESULT not in names:
            names.append(RESULT)
        if b is entry and (extra - set(fn.params)):
            raise ProgramError(f"entry block of {fn.name!r} uses undefined variables {sorted(extra - set(fn.params))}",
                               b.line)
        b.params = names
    for b in blocks:
        for i in b.instrs:
            if isinstance(i, Call) and i.passed is not None:
                k = fn.blocks[i.ret]
                unknown = set(i.passed) - set(k.params)
                if unknown:
                    raise ProgramError(f"{i.ret!r} does not take {sorted(unknown)}", i.line)


def _var_order(fn: Function) -> list[str]:
    """Variables in first-appearance order, for stable parameter lists."""
    seen: list[str] = list(fn.params)
    for b in fn.blocks.values():
        for p in (b.params if b.explicit else []):
            if p not in seen:
                seen.append(p)
        for i in b.instrs:
            for v in [i.defines()] + i.uses():
                if v and v not in seen and not (isinstance(i, Call) and v == i.callee):
                    seen.append(v)
    if RESULT not in seen:
        seen.append(RESULT)
    return seen
