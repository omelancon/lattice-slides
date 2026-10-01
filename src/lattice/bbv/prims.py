"""Primitive operations known to the specializers and the abstract interpreter: argument
requirements, result types (with intervals for integer arithmetic) and the narrowing of type
tests and comparisons at conditionals (the ``fixnum?``, ``fx*?``, ``##*``, ``>`` family of the thesis)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .intervals import Interval
from .types import Type

Result = Type | Callable[[list[Type]], Type]
# narrow(arg types) -> (types when the test holds, types when it fails); None marks an impossible outcome
Narrow = Callable[[list[Type]], tuple[list[Type] | None, list[Type] | None]]


@dataclass(frozen=True)
class Prim:
    name: str
    args: tuple[Type, ...] | None = None  # required argument types (the call fails otherwise)
    result: Result = Type.any()
    test: Type | None = None  # for type predicates: the type of the argument when the test holds
    narrow: Narrow | None = None  # for predicates usable in ``if``

    def result_type(self, arg_types: list[Type]) -> Type:
        if callable(self.result):
            return self.result(arg_types)
        return self.result


FX, FL, NUM, BOOL, PAIR, ANY = (Type.of("fx"), Type.of("fl"), Type.of("num"), Type.of("bool"), Type.of("pair"),
                                Type.any())
INT = Type.of("fx", "bg")


def _integers(types: list[Type]) -> bool:
    return all(t.subset(INT) and not t.is_bottom() for t in types)


def _ranges(types: list[Type]) -> list[Interval]:
    return [t.range if t.range is not None else Interval.full() for t in types]


def _int_op(op: Callable[[Interval, Interval], Interval], bits: Type):
    """An integer operation: the result keeps the interval computed from the argument intervals."""

    def result(types: list[Type]) -> Type:
        if len(types) == 2 and _integers(types) and any(t.range is not None for t in types):
            a, b = _ranges(types)
            try:
                return bits.with_range(op(a, b))
            except ValueError:
                return bits
        return bits

    return result


def _arith(op: Callable[[Interval, Interval], Interval]):
    """Generic arithmetic: two integers stay integers (the interval decides fixnum or bignum),
    two flonums stay flonums, anything else is a number."""
    integer = _int_op(op, INT)

    def result(types: list[Type]) -> Type:
        if _integers(types):
            return integer(types)
        if all(t.is_exactly("fl") for t in types):
            return FL
        return NUM

    return result


def _type_test(hold: Type) -> Narrow:
    def narrow(types: list[Type]):
        t = types[0]
        yes, no = t.intersection(hold), t.intersection(hold.complement())
        return ([yes] if not yes.is_bottom() else None), ([no] if not no.is_bottom() else None)

    return narrow


def _compare(holds: str) -> Narrow:
    """Narrowing for ``<``, ``<=``, ``=``, ``>``, ``>=`` on two integer arguments."""
    def pair(a: Interval, b: Interval, op: str):
        if op == "<":
            return a.lt(b)
        if op == "<=":
            return a.le(b)
        if op == "=":
            return a.eq(b)
        if op == "!=":
            return a.ne(b)
        if op == ">":
            r = b.lt(a)
            return (r[1], r[0]) if r else None
        if op == ">=":
            r = b.le(a)
            return (r[1], r[0]) if r else None
        raise ValueError(op)

    negation = {"<": ">=", "<=": ">", "=": "!=", "!=": "=", ">": "<=", ">=": "<"}

    def narrow(types: list[Type]):
        if len(types) != 2 or not _integers(types):
            return list(types), list(types)  # nothing known beyond the types themselves
        a, b = _ranges(types)
        out = []
        for op in (holds, negation[holds]):
            r = pair(a, b, op)
            out.append(None if r is None else [types[0].with_range(r[0]), types[1].with_range(r[1])])
        return out[0], out[1]

    return narrow


def _minmax(pick):
    def result(types: list[Type]) -> Type:
        if _integers(types) and all(t.range is not None for t in types):
            lo = pick(t.range.lo for t in types)
            hi = pick(t.range.hi for t in types)
            return INT.with_range(Interval(lo, hi))
        return NUM if not _integers(types) else INT

    return result


def _table() -> dict[str, Prim]:
    prims: list[Prim] = []

    def add(name, args=None, result=ANY, test=None, narrow=None):
        prims.append(Prim(name, tuple(args) if args is not None else None, result, test, narrow))

    for name, t in [("fixnum?", "fx"), ("flonum?", "fl"), ("bignum?", "bg"), ("number?", "num"),
                    ("pair?", "pair"), ("null?", "nil"), ("procedure?", "proc"), ("boolean?", "bool"),
                    ("string?", "str"), ("integer?", "fx | bg")]:
        hold = Type.parse(t)
        add(name, [ANY], BOOL, hold, _type_test(hold))
    for name, op in [("fx+", lambda a, b: a + b), ("fx-", lambda a, b: a - b), ("fx*", lambda a, b: a * b),
                     ("fxquotient", lambda a, b: a.quotient(b))]:
        add(name, [FX, FX], _int_op(op, FX))
    for name in ["fxremainder", "fxmodulo"]:
        add(name, [FX, FX], FX)
    for name, op in [("fx+?", lambda a, b: a + b), ("fx-?", lambda a, b: a - b), ("fx*?", lambda a, b: a * b)]:
        add(name, [FX, FX], _int_op(op, Type.of("fx", "#f")))
    for name, cmp in [("fx<", "<"), ("fx>", ">"), ("fx=", "="), ("fx<=", "<="), ("fx>=", ">=")]:
        add(name, [FX, FX], BOOL, narrow=_compare(cmp))
    add("fxzero?", [FX], BOOL, narrow=lambda ts: _compare("=")([ts[0], Type.integer(0, 0)]))
    for name in ["fl+", "fl-", "fl*", "fl/"]:
        add(name, [FL, FL], FL)
    for name in ["fl<", "fl>", "fl=", "fl<=", "fl>=", "flzero?"]:
        add(name, [FL] * (1 if name == "flzero?" else 2), BOOL)
    for name, op in [("+", lambda a, b: a + b), ("-", lambda a, b: a - b), ("*", lambda a, b: a * b)]:
        add(name, [NUM, NUM], _arith(op))
        add("##" + name, [NUM, NUM], _arith(op))
    for name in ["/", "##/"]:
        add(name, [NUM, NUM], NUM)
    add("quotient", [NUM, NUM], _arith(lambda a, b: a.quotient(b)))
    add("##quotient", [NUM, NUM], _arith(lambda a, b: a.quotient(b)))
    for name, cmp in [("<", "<"), (">", ">"), ("=", "="), ("<=", "<="), (">=", ">=")]:
        add(name, [NUM, NUM], BOOL, narrow=_compare(cmp))
        add("##" + name, [NUM, NUM], BOOL, narrow=_compare(cmp))
    for name in ["zero?", "##zero?"]:
        add(name, [NUM], BOOL, narrow=lambda ts: _compare("=")([ts[0], Type.integer(0, 0)]))
    add("abs", [NUM], lambda ts: (INT.with_range(ts[0].range.abs()) if _integers(ts) and ts[0].range is not None
                                  else (INT if _integers(ts) else NUM)))
    add("min", [NUM, NUM], _minmax(min))
    add("max", [NUM, NUM], _minmax(max))
    add("car", [PAIR], ANY)
    add("cdr", [PAIR], ANY)
    add("##car", [ANY], ANY)
    add("##cdr", [ANY], ANY)
    add("cons", [ANY, ANY], PAIR)
    for name in ["eq?", "eqv?", "equal?", "not"]:
        add(name, [ANY] * (1 if name == "not" else 2), BOOL)
    add("display", [ANY], Type.of("other"))
    add("read", [], ANY)
    add("random", [], ANY)
    return {p.name: p for p in prims}


DEFAULT_PRIMS = _table()


def prim_from_spec(name: str, spec: dict) -> Prim:
    """Build a primitive from a YAML mapping: ``{args: [fx, fx], result: "fx | #f"}`` or ``{test: pair}``."""
    if "test" in spec:
        hold = Type.parse(str(spec["test"]))
        return Prim(name, (ANY,), BOOL, hold, _type_test(hold))
    args = spec.get("args")
    return Prim(name, tuple(Type.parse(str(a)) for a in args) if args is not None else None,
                Type.parse(str(spec.get("result", "any"))))
