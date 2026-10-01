"""Type lattice and contexts for basic block versioning (thesis chapter 1.1 and figure 17).

A type is a set of primitive run-time types (a bit set) plus, for procedures, the set of functions
the value is known to be. A context maps variables to types and keeps equivalence classes of
variables holding the same value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from math import inf
from typing import Iterable

from .intervals import Interval

PRIMITIVE_TYPES = ["fx", "bg", "fl", "#t", "#f", "nil", "pair", "str", "proc", "other"]
_BIT = {name: 1 << i for i, name in enumerate(PRIMITIVE_TYPES)}
ALL_BITS = (1 << len(PRIMITIVE_TYPES)) - 1
_ALIASES = {
    "bool": ("#t", "#f"),
    "num": ("fx", "fl", "bg"),
    "true": ("#t",),
    "false": ("#f",),
    "null": ("nil",),
    "procedure": ("proc",),
    "string": ("str",),
}


_INT_BITS = (1 << PRIMITIVE_TYPES.index("fx")) | (1 << PRIMITIVE_TYPES.index("bg"))
_FX_BIT = 1 << PRIMITIVE_TYPES.index("fx")
_BG_BIT = 1 << PRIMITIVE_TYPES.index("bg")
_INTERVAL = re.compile(r"^(.*?)\s*(\{\s*(-?\d+)\s*\}|[\[(]\s*(-?\d+|-?∞|-?inf)\s*,\s*(-?\d+|-?∞|\+?inf)\s*[\])])\s*$")


def _bound(text: str):
    text = text.strip()
    if text in ("∞", "+inf", "inf"):
        return inf
    if text in ("-∞", "-inf"):
        return -inf
    return int(text)


@dataclass(frozen=True)
class Type:
    """A set of primitive types. ``procs`` names the functions a procedure value may be;
    ``None`` means any procedure (when the ``proc`` bit is set). ``range`` is the interval of the
    value when it is an integer (``fx`` or ``bg``); ``None`` means unknown, that is any integer."""

    bits: int
    procs: frozenset[str] | None = None
    range: Interval | None = None

    def __post_init__(self):
        # canonical form: no interval without integer bits, no interval when it is the full line
        if self.range is not None and (not self.bits & _INT_BITS or self.range.is_full()):
            object.__setattr__(self, "range", None)

    # -- constructors
    @staticmethod
    def of(*names: str) -> "Type":
        bits = 0
        for n in names:
            for m in _ALIASES.get(n, (n,)):
                if m not in _BIT:
                    raise ValueError(f"unknown type {n!r}")
                bits |= _BIT[m]
        return Type(bits)

    @staticmethod
    def any() -> "Type":
        return Type(ALL_BITS)

    @staticmethod
    def bottom() -> "Type":
        return Type(0)

    @staticmethod
    def function(name: str) -> "Type":
        return Type(_BIT["proc"], frozenset([name]))

    @staticmethod
    def integer(lo, hi) -> "Type":
        """An integer in ``[lo, hi]`` (``fx`` or ``bg`` until refined)."""
        return Type(_INT_BITS, None, Interval(lo, hi))

    @staticmethod
    def parse(text: str) -> "Type":
        """``"fx | fl"``, ``"!fx"``, ``"any"``, ``"⊥"``, ``"proc(square)"``, ``"fx [0, 100]"``, ``"fx | bg {0}"``."""
        text = text.strip()
        m = _INTERVAL.match(text)
        if m:
            base = Type.parse(m.group(1)) if m.group(1).strip() else Type.of("fx", "bg")
            rng = Interval.of(int(m.group(3))) if m.group(3) is not None else Interval(_bound(m.group(4)), _bound(m.group(5)))
            return Type(base.bits, base.procs, rng)
        if text in ("any", "⊤", "top"):
            return Type.any()
        if text in ("⊥", "bottom", "nil-type"):
            return Type.bottom()
        if text.startswith("!"):
            inner = text[1:].strip()
            if inner.startswith("(") and inner.endswith(")"):
                inner = inner[1:-1]
            return Type.parse(inner).complement()
        procs: set[str] = set()
        bits = 0
        for part in text.split("|"):
            part = part.strip()
            if part.startswith("proc(") and part.endswith(")"):
                procs.update(p.strip() for p in part[5:-1].split(",") if p.strip())
                bits |= _BIT["proc"]
            else:
                bits |= Type.of(part).bits
        return Type(bits, frozenset(procs) if procs else None)

    # -- lattice operations
    def has(self, name: str) -> bool:
        return bool(self.bits & Type.of(name).bits)

    def is_bottom(self) -> bool:
        return self.bits == 0

    def is_any(self) -> bool:
        return self.bits == ALL_BITS and self.procs is None

    def is_exactly(self, name: str) -> bool:
        return self.bits == Type.of(name).bits

    def subset(self, other: "Type") -> bool:
        if self.bits & ~other.bits:
            return False
        if self.bits & _BIT["proc"] and other.procs is not None:
            return self.procs is not None and self.procs <= other.procs
        return True

    def union(self, other: "Type") -> "Type":
        bits = self.bits | other.bits
        procs = None
        if bits & _BIT["proc"]:
            a = self.procs if self.bits & _BIT["proc"] else frozenset()
            b = other.procs if other.bits & _BIT["proc"] else frozenset()
            procs = None if a is None or b is None else a | b
        return Type(bits, procs, self._range_union(other))

    def _range_union(self, other: "Type") -> Interval | None:
        if not self.bits & _INT_BITS:
            return other.range
        if not other.bits & _INT_BITS:
            return self.range
        if self.range is None or other.range is None:
            return None
        return self.range.union(other.range)

    def widen(self, new: "Type", thresholds) -> "Type":
        """Union with widening: the bits are joined, the interval widened against ``self``."""
        joined = self.union(new)
        if self.bits & _INT_BITS and new.bits & _INT_BITS and self.range is not None and new.range is not None:
            rng = self.range.widen(new.range, thresholds)
            bits = joined.bits | (_INT_BITS if rng != joined.range else 0)  # extrapolation may leave fixnums
            return Type(bits, joined.procs, rng)
        return joined

    def intersection(self, other: "Type") -> "Type":
        bits = self.bits & other.bits
        procs = None
        if bits & _BIT["proc"]:
            if self.procs is None:
                procs = other.procs
            elif other.procs is None:
                procs = self.procs
            else:
                procs = self.procs & other.procs
                if not procs:
                    bits &= ~_BIT["proc"]
                    procs = None
        rng = None
        if bits & _INT_BITS:
            if self.range is None:
                rng = other.range
            elif other.range is None:
                rng = self.range
            else:
                rng = self.range.intersection(other.range)
                if rng is None:
                    bits &= ~_INT_BITS  # no integer satisfies both: the integer part is gone
        return Type(bits, procs, rng)

    def complement(self) -> "Type":
        # The complement of a known set of functions, or of an interval, is not representable; it is
        # widened to any procedure or any integer, which is sound.
        return Type(ALL_BITS & ~self.bits if self.procs is None else ALL_BITS & ~(self.bits & ~_BIT["proc"]))

    def with_range(self, rng: Interval | None) -> "Type":
        return Type(self.bits, self.procs, rng)

    def without_range(self) -> "Type":
        return Type(self.bits, self.procs, None)

    def refined(self, fixnum_bits: int = 62) -> "Type":
        """Let the interval decide between ``fx`` and ``bg`` (and a ``fx``-only type bound its interval)."""
        if not self.bits & _INT_BITS:
            return self
        lo, hi = -(1 << (fixnum_bits - 1)), (1 << (fixnum_bits - 1)) - 1
        fixnums = Interval(lo, hi)
        bits, rng = self.bits, self.range
        if rng is not None:
            if fixnums.contains(rng):
                bits &= ~_BG_BIT
            elif rng.intersection(fixnums) is None:
                bits &= ~_FX_BIT
        if bits & _FX_BIT and not bits & _BG_BIT and rng is not None:
            rng = fixnums.intersection(rng)
            if rng is None:
                bits &= ~_FX_BIT
        return Type(bits, self.procs, rng if bits & _INT_BITS else None)

    def count(self) -> int:
        return bin(self.bits).count("1")

    def hamming(self, other: "Type") -> int:
        return bin(self.bits ^ other.bits).count("1")

    def names(self) -> list[str]:
        return [n for n in PRIMITIVE_TYPES if self.bits & _BIT[n]]

    # -- printing (thesis notation)
    def __str__(self) -> str:
        if self.bits == 0:
            return "⊥"
        if self.is_any():
            return "any"
        present = self.names()
        missing = [n for n in PRIMITIVE_TYPES if not self.bits & _BIT[n]]
        if self.procs is not None:
            present = [f"proc({','.join(sorted(self.procs))})" if n == "proc" else n for n in present]
        elif len(missing) <= 2 and len(present) > len(missing):
            text = "!" + (missing[0] if len(missing) == 1 else "(" + " | ".join(missing) + ")")
            return text + (f" {self.range}" if self.range is not None else "")
        if present == ["#t", "#f"]:
            text = "bool"
        else:
            text = " | ".join(present)
        if self.range is not None and len(missing) > 2:
            text += f" {self.range}"
        return text

    def __repr__(self) -> str:
        return f"Type({self})"


ANY = Type.any()
BOTTOM = Type.bottom()


class Context:
    """Variables to types, plus equivalence classes (thesis figure 17).

    Immutable: every operation returns a new context. Variable order is kept for printing.
    ``rep[v]`` is the representative of ``v``'s class (the earliest variable of the class).
    """

    __slots__ = ("_types", "_rep", "_key")

    def __init__(self, types: dict[str, Type] | None = None, rep: dict[str, str] | None = None):
        self._types = dict(types or {})
        self._rep = {v: (rep or {}).get(v, v) for v in self._types}
        self._key = None

    # -- basic access
    def vars(self) -> list[str]:
        return list(self._types)

    def get(self, v: str) -> Type:
        return self._types.get(v, ANY)

    def __contains__(self, v: str) -> bool:
        return v in self._types

    def types(self) -> dict[str, Type]:
        return dict(self._types)

    def rep(self, v: str) -> str:
        return self._rep.get(v, v)

    def same(self, a: str, b: str) -> bool:
        return a in self._types and b in self._types and self._rep[a] == self._rep[b]

    def classmates(self, v: str) -> list[str]:
        r = self.rep(v)
        return [w for w in self._types if self._rep[w] == r]

    # -- identity
    def key(self):
        if self._key is None:
            self._key = tuple((v, self._types[v].bits, self._types[v].procs, self._types[v].range, self._rep[v])
                              for v in sorted(self._types))
        return self._key

    def __eq__(self, other) -> bool:
        return isinstance(other, Context) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def is_bottom(self) -> bool:
        return any(t.is_bottom() for t in self._types.values())

    # -- updates
    def _copy(self) -> "Context":
        c = Context.__new__(Context)
        c._types = dict(self._types)
        c._rep = dict(self._rep)
        c._key = None
        return c

    def set(self, v: str, t: Type) -> "Context":
        """Assign a new value to ``v``: its type becomes ``t`` and it leaves its class."""
        c = self._copy()
        c._detach(v)
        c._types[v] = t
        c._rep[v] = v
        return c

    def _detach(self, v: str) -> None:
        if v not in self._types:
            return
        mates = [w for w in self._types if self._rep[w] == self._rep[v] and w != v]
        if mates:
            new_rep = mates[0]
            for w in mates:
                self._rep[w] = new_rep

    def narrow(self, v: str, t: Type) -> "Context":
        """Intersect the type of ``v`` (and of its whole class) with ``t``."""
        c = self._copy()
        if v not in c._types:
            c._types[v] = ANY
            c._rep[v] = v
        for w in c.classmates(v):
            c._types[w] = c._types[w].intersection(t)
        return c

    def equate(self, a: str, b: str) -> "Context":
        """Record that ``a`` and ``b`` hold the same value (``a = b``)."""
        c = self._copy()
        for v in (a, b):
            if v not in c._types:
                c._types[v] = ANY
                c._rep[v] = v
        t = c._types[a].intersection(c._types[b])
        ra, rb = c._rep[a], c._rep[b]
        order = list(c._types)
        new_rep = min(ra, rb, key=order.index)
        for w in c._types:
            if c._rep[w] in (ra, rb):
                c._rep[w] = new_rep
                c._types[w] = t
        return c

    def map(self, f) -> "Context":
        """Apply ``f`` to every type (classes are kept)."""
        c = self._copy()
        for v in c._types:
            c._types[v] = f(c._types[v])
        return c

    def restrict(self, names: Iterable[str]) -> "Context":
        """Keep only ``names`` (in that order); classes are kept among the survivors."""
        keep = [n for n in names]
        c = Context.__new__(Context)
        c._types = {n: self._types.get(n, ANY) for n in keep}
        old_rep = {n: self._rep.get(n, n) for n in keep}
        first: dict[str, str] = {}
        c._rep = {}
        for n in keep:
            r = old_rep[n]
            c._rep[n] = first.setdefault(r, n)
        c._key = None
        return c

    def rename(self, mapping: dict[str, str | Type], names: Iterable[str]) -> "Context":
        """Build the context of a target block: ``mapping`` gives, for target parameters, the source
        variable (equivalences are kept) or a literal type; other ``names`` are copied."""
        keep = list(names)
        c = Context.__new__(Context)
        c._types = {}
        c._rep = {}
        source_of: dict[str, str] = {}
        for n in keep:
            src = mapping.get(n, n)
            if isinstance(src, Type):
                c._types[n] = src
            else:
                c._types[n] = self._types.get(src, ANY)
                source_of[n] = self._rep.get(src, src)
        first: dict[str, str] = {}
        for n in keep:
            if n in source_of:
                c._rep[n] = first.setdefault(source_of[n], n)
            else:
                c._rep[n] = n
        c._key = None
        return c

    def union(self, other: "Context", thresholds=None, widen: bool = False) -> "Context":
        """Union of two contexts; with ``widen``, intervals that grew are widened against ``self``
        (thesis 1.1.1). Classes are kept where both agree."""
        names = list(self._types) + [v for v in other._types if v not in self._types]
        c = Context.__new__(Context)
        if widen:
            c._types = {n: self.get(n).widen(other.get(n), thresholds) for n in names}
        else:
            c._types = {n: self.get(n).union(other.get(n)) for n in names}
        c._rep = {}
        first: dict[tuple, str] = {}
        for n in names:
            pair = (self.rep(n), other.rep(n))
            c._rep[n] = first.setdefault(pair, n) if n in self._types and n in other._types else n
        c._key = None
        return c

    def intersection(self, other: "Context") -> "Context":
        names = list(self._types) + [v for v in other._types if v not in self._types]
        c = Context.__new__(Context)
        c._types = {n: self.get(n).intersection(other.get(n)) for n in names}
        c._rep = dict(self._rep)
        for n in names:
            c._rep.setdefault(n, other.rep(n) if n in other._types else n)
        c._key = None
        # classes of ``other`` are merged into ours
        for n in names:
            if n in other._types:
                for m in other.classmates(n):
                    if m in c._types and c._rep[m] != c._rep[n]:
                        rm, rn = c._rep[m], c._rep[n]
                        order = list(c._types)
                        new_rep = min(rm, rn, key=order.index)
                        t = c._types[m].intersection(c._types[n])
                        for w in c._types:
                            if c._rep[w] in (rm, rn):
                                c._rep[w] = new_rep
                                c._types[w] = t
        return c

    # -- printing
    def lines(self) -> list[str]:
        """One line per equivalence class, in the thesis notation ``;; a/b: fx``."""
        out = []
        seen: set[str] = set()
        for v in self._types:
            r = self._rep[v]
            if r in seen:
                continue
            seen.add(r)
            mates = [w for w in self._types if self._rep[w] == r]
            out.append(f"{'/'.join(mates)}: {self._types[v]}")
        return out

    def __str__(self) -> str:
        return ", ".join(self.lines())

    def __repr__(self) -> str:
        return f"Context({self})"
