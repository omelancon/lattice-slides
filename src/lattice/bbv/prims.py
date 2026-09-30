"""Primitive operations known to the specializer: argument requirements, result types and
type tests (the ``fixnum?``, ``fx*?``, ``##*`` family of the thesis)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .types import Type

Result = Type | Callable[[list[Type]], Type]


@dataclass(frozen=True)
class Prim:
    name: str
    args: tuple[Type, ...] | None = None  # required argument types (the call fails otherwise)
    result: Result = Type.any()
    test: Type | None = None  # for type predicates: the type of the argument when the test holds

    def result_type(self, arg_types: list[Type]) -> Type:
        if callable(self.result):
            return self.result(arg_types)
        return self.result


def _arith(arg_types: list[Type]) -> Type:
    """Generic arithmetic: two fixnums may overflow to a bignum, two flonums stay flonums."""
    if all(t.is_exactly("fx") for t in arg_types):
        return Type.of("fx", "bg")
    if all(t.is_exactly("fl") for t in arg_types):
        return Type.of("fl")
    return Type.of("num")


FX, FL, NUM, BOOL, PAIR, ANY = (Type.of("fx"), Type.of("fl"), Type.of("num"), Type.of("bool"), Type.of("pair"),
                                Type.any())


def _table() -> dict[str, Prim]:
    prims: list[Prim] = []

    def add(name, args=None, result=ANY, test=None):
        prims.append(Prim(name, tuple(args) if args is not None else None, result, test))

    for name, t in [("fixnum?", "fx"), ("flonum?", "fl"), ("bignum?", "bg"), ("number?", "num"),
                    ("pair?", "pair"), ("null?", "nil"), ("procedure?", "proc"), ("boolean?", "bool"),
                    ("string?", "str"), ("integer?", "fx | bg")]:
        add(name, [ANY], BOOL, Type.parse(t))
    for name in ["fx+", "fx-", "fx*", "fxquotient", "fxremainder", "fxmodulo"]:
        add(name, [FX, FX], FX)
    for name in ["fx+?", "fx-?", "fx*?"]:
        add(name, [FX, FX], Type.of("fx", "#f"))
    for name in ["fx<", "fx>", "fx=", "fx<=", "fx>=", "fxzero?"]:
        add(name, [FX] * (1 if name == "fxzero?" else 2), BOOL)
    for name in ["fl+", "fl-", "fl*", "fl/"]:
        add(name, [FL, FL], FL)
    for name in ["fl<", "fl>", "fl=", "fl<=", "fl>=", "flzero?"]:
        add(name, [FL] * (1 if name == "flzero?" else 2), BOOL)
    for name in ["+", "-", "*", "##+", "##-", "##*"]:
        add(name, [NUM, NUM], _arith)
    for name in ["/", "##/"]:
        add(name, [NUM, NUM], NUM)
    for name in ["<", ">", "=", "<=", ">=", "##<", "##>", "##=", "##<=", "##>=", "zero?", "##zero?"]:
        add(name, [NUM] * (1 if "zero" in name else 2), BOOL)
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
        return Prim(name, (ANY,), BOOL, Type.parse(str(spec["test"])))
    args = spec.get("args")
    return Prim(name, tuple(Type.parse(str(a)) for a in args) if args is not None else None,
                Type.parse(str(spec.get("result", "any"))))
