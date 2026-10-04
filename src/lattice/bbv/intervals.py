"""Integer intervals with the widening of thesis figure 2 and the symbolic bounds of the SBBV
paper (thesis appendix D, section 3.3).

An interval is ``[lo, hi]`` with ``lo <= hi``, bounds being integers, ``±inf`` or a *symbol*
``⟦v⟧-i``: the length of the vector held by variable ``v`` minus an offset ``i >= 0``. A vector
length is a fixnum in ``0..maxfix``, so ``⟦v⟧-i`` lies in ``-i..maxfix-i``; ``maxfix`` comes from
:func:`fixnum_bits` (61 bits by default, a 3-bit tag implementation). Widening moves a bound that
grew to the next *threshold* at or beyond it, so that ascending chains stabilize:
``{0} ∪ {1} = [0, 1]``, ``[0, 1] ∪ [1, 2] = [0, 2]``, ``[0, 2] ∪ [1, 3]`` widens to ``[0, 127]``, then
``[0, 128]``, ``[0, 2^31 - 1]``, ``[0, 2^31]``, ``[0, 2^63 - 1]``, ``[0, 2^63]``, ``[0, ∞)``.

Rules for symbols (paper, page 131, with ``vallo(⟦v⟧-i) = -i``): lower bounds drop the symbol
under addition (``(⟦v⟧-i) + j = j - i``), upper bounds keep it while the offset stays nonnegative
(``(⟦v⟧-i) + j = ⟦v⟧-(i-j)`` if ``i >= j``, an overflow otherwise). A comparison between a number
and a symbol is decided only when the symbol's numeric range settles it (``surely_le``); when it does not, the
narrowing of a comparison keeps the symbolic candidate for an upper bound and the numeric one for
a lower bound (what bound checks need), and a join keeps the symbol only when it bounds both sides.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
from math import inf

DEFAULT_FIXNUM_BITS = 61
_BITS = [DEFAULT_FIXNUM_BITS]


def fixnum_bits() -> int:
    return _BITS[-1]


def maxfix(bits: int | None = None) -> int:
    return (1 << ((bits or fixnum_bits()) - 1)) - 1


def minfix(bits: int | None = None) -> int:
    return -(1 << ((bits or fixnum_bits()) - 1))


@contextlib.contextmanager
def using_fixnum_bits(bits: int):
    """Run with another fixnum width (the ``fixnum_bits`` option of the components)."""
    _BITS.append(bits)
    try:
        yield
    finally:
        _BITS.pop()


@dataclass(frozen=True)
class Sym:
    """The bound ``⟦var⟧ - off``: the length of the vector held by ``var`` minus ``off >= 0``."""

    var: str
    off: int = 0

    def __post_init__(self):
        if self.off < 0:
            raise ValueError(f"negative offset in {self}")

    def __str__(self) -> str:
        return f"⟦{self.var}⟧" + (f"-{self.off}" if self.off else "")


Bound = int | float | Sym  # an int, ±inf, or a symbol

THESIS_THRESHOLDS = [0, 1, 2, 127, 128, 2**31 - 1, 2**31, 2**63 - 1, 2**63]
THESIS_THRESHOLDS = sorted({t for t in THESIS_THRESHOLDS} | {-t for t in THESIS_THRESHOLDS}
                           | {-129, -2**31 - 1, -2**63 - 1} | {inf, -inf})
MACHINE_THRESHOLDS = THESIS_THRESHOLDS
SIGN_THRESHOLDS = [-inf, -1, 0, 1, inf]


def thresholds_named(name: str) -> list[Bound] | None:
    if name in ("machine", "thesis"):
        return MACHINE_THRESHOLDS
    if name == "sign":
        return SIGN_THRESHOLDS
    if name == "none":
        return None
    raise ValueError(f"unknown thresholds {name!r}; use machine, sign, none or a list")


# ------------------------------------------------------------------ bounds

def is_sym(b: Bound) -> bool:
    return isinstance(b, Sym)


def lo_value(b: Bound) -> int | float:
    """The smallest value a bound can take (``-i`` for ``⟦v⟧-i``)."""
    return -b.off if isinstance(b, Sym) else b


def hi_value(b: Bound) -> int | float:
    """The largest value a bound can take (``maxfix - i`` for ``⟦v⟧-i``)."""
    return maxfix() - b.off if isinstance(b, Sym) else b


def surely_le(a: Bound, b: Bound) -> bool:
    """``a <= b`` whatever the vector lengths are."""
    if a == b:
        return True
    if isinstance(a, Sym) and isinstance(b, Sym) and a.var == b.var:
        return a.off >= b.off
    return hi_value(a) <= lo_value(b)


def surely_lt(a: Bound, b: Bound) -> bool:
    """``a < b`` whatever the vector lengths are."""
    if isinstance(a, Sym) and isinstance(b, Sym) and a.var == b.var:
        return a.off > b.off
    return hi_value(a) < lo_value(b)


def _prefer(a: Bound, b: Bound, symbolic: bool) -> Bound:
    """Between two candidates whose order is unknown: the symbolic (or numeric) one, the
    earlier variable when both are symbols."""
    sa, sb = isinstance(a, Sym), isinstance(b, Sym)
    if sa and sb:
        return a if a.var <= b.var else b
    if sa != sb:
        return a if sa == symbolic else b
    return a


def max_lo(a: Bound, b: Bound) -> Bound:
    """The tighter of two lower bounds (narrowing); the numeric candidate when unknown."""
    if surely_le(a, b):
        return b
    if surely_le(b, a):
        return a
    return _prefer(a, b, symbolic=False)


def min_hi(a: Bound, b: Bound) -> Bound:
    """The tighter of two upper bounds (narrowing); the symbolic candidate when unknown."""
    if surely_le(a, b):
        return a
    if surely_le(b, a):
        return b
    return _prefer(a, b, symbolic=True)


def join_lo(a: Bound, b: Bound) -> Bound:
    """A lower bound of both (union): the symbol survives only when it bounds both sides."""
    if surely_le(a, b):
        return a
    if surely_le(b, a):
        return b
    return min(lo_value(a), lo_value(b))


def join_hi(a: Bound, b: Bound) -> Bound:
    """An upper bound of both (union)."""
    if surely_le(a, b):
        return b
    if surely_le(b, a):
        return a
    return max(hi_value(a), hi_value(b))


def add_lo(a: Bound, b: Bound) -> Bound:
    if isinstance(a, Sym) and isinstance(b, Sym):
        return -a.off - b.off
    if isinstance(b, Sym):
        a, b = b, a
    if isinstance(a, Sym):
        return _add(-a.off, b)
    return _add(a, b)


def add_hi(a: Bound, b: Bound) -> Bound:
    if isinstance(a, Sym) and isinstance(b, Sym):
        return hi_value(a) + hi_value(b)  # overflow
    if isinstance(b, Sym):
        a, b = b, a
    if isinstance(a, Sym):
        if b in (inf, -inf):
            return b
        if b <= a.off:
            return Sym(a.var, a.off - b)
        return hi_value(a) + b  # overflow: not a fixnum any more
    return _add(a, b)


def fmt_bound(n: Bound) -> str:
    """Large bounds near a power of two print as ``2^31-1``, as in the thesis figures."""
    if isinstance(n, Sym):
        return str(n)
    if n in (inf, -inf):
        return "∞" if n > 0 else "-∞"
    if n == maxfix():
        return "maxfix"
    if 0 < maxfix() - n <= 16:  # a symbol ⟦v⟧-i widened to its value
        return f"maxfix-{maxfix() - n}"
    if n == minfix():
        return "minfix"
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a >= 256:
        for k in range(8, 130):
            p = 1 << k
            if a == p:
                return f"{sign}2^{k}"
            if a == p - 1:
                return f"{sign}2^{k}{'+' if sign else '-'}1"
            if a == p + 1:
                return f"{sign}2^{k}{'-' if sign else '+'}1"
            if p > a:
                break
    return str(n)


# ------------------------------------------------------------------ intervals

@dataclass(frozen=True)
class Interval:
    lo: Bound
    hi: Bound

    def __post_init__(self):
        if surely_lt(self.hi, self.lo):
            raise ValueError(f"empty interval [{self.lo}, {self.hi}]")

    @staticmethod
    def full() -> "Interval":
        return Interval(-inf, inf)

    @staticmethod
    def of(n: Bound) -> "Interval":
        return Interval(n, n)

    def is_full(self) -> bool:
        return self.lo == -inf and self.hi == inf

    def is_singleton(self) -> bool:
        return self.lo == self.hi and self.lo != inf and self.lo != -inf

    def symbols(self) -> set[str]:
        return {b.var for b in (self.lo, self.hi) if isinstance(b, Sym)}

    def numeric(self) -> "Interval":
        """The interval over the numeric values of its bounds (symbols widened)."""
        return Interval(lo_value(self.lo), hi_value(self.hi))

    def remap(self, mapping: dict[str, str | None]) -> "Interval":
        """Rename the vectors of the symbolic bounds; a vector mapped to ``None`` has left the
        context and its bound becomes the numeric value."""
        lo, hi = self.lo, self.hi
        if isinstance(lo, Sym):
            n = mapping.get(lo.var, lo.var)
            lo = Sym(n, lo.off) if n is not None else lo_value(lo)
        if isinstance(hi, Sym):
            n = mapping.get(hi.var, hi.var)
            hi = Sym(n, hi.off) if n is not None else hi_value(hi)
        return Interval(lo, hi)

    def contains(self, other: "Interval") -> bool:
        return surely_le(self.lo, other.lo) and surely_le(other.hi, self.hi)

    def union(self, other: "Interval") -> "Interval":
        return Interval(join_lo(self.lo, other.lo), join_hi(self.hi, other.hi))

    def intersection(self, other: "Interval") -> "Interval | None":
        return _mk(max_lo(self.lo, other.lo), min_hi(self.hi, other.hi))

    def widen(self, new: "Interval", thresholds: list[Bound] | None) -> "Interval":
        """Widening with thresholds: a numeric bound that grew moves to the next threshold beyond
        it; a symbolic upper bound that grew moves to ``⟦v⟧``; a bound that became symbolic keeps
        the symbol (that step is the jump); a bound that became numeric stops at the symbol's
        numeric value first; a symbolic lower bound that grew becomes its numeric value."""
        if thresholds is None:
            return self.union(new)
        lo, hi = join_lo(self.lo, new.lo), join_hi(self.hi, new.hi)
        if hi != self.hi:
            if isinstance(hi, Sym):
                if isinstance(self.hi, Sym) and hi.off > 0:
                    hi = Sym(hi.var, 0)
            elif not (isinstance(self.hi, Sym) or isinstance(new.hi, Sym)):
                hi = min([t for t in thresholds if t >= hi], default=inf)
        if lo != self.lo:
            if isinstance(lo, Sym):
                lo = lo_value(lo)
            elif not (isinstance(self.lo, Sym) or isinstance(new.lo, Sym)):
                lo = max([t for t in thresholds if t <= lo], default=-inf)
        return Interval(lo, hi)

    # -- arithmetic
    def __add__(self, o: "Interval") -> "Interval":
        return Interval(add_lo(self.lo, o.lo), add_hi(self.hi, o.hi))

    def __neg__(self) -> "Interval":
        return Interval(-hi_value(self.hi), -lo_value(self.lo))

    def __sub__(self, o: "Interval") -> "Interval":
        return self + (-o)

    def __mul__(self, o: "Interval") -> "Interval":
        a, b = self.numeric(), o.numeric()
        ps = [_mul(x, y) for x in (a.lo, a.hi) for y in (b.lo, b.hi)]
        return Interval(min(ps), max(ps))

    def quotient(self, o: "Interval") -> "Interval":
        """Integer division truncating toward zero, for a divisor interval not containing 0 only
        partially known: any divisor gives the conservative result."""
        a, b = self.numeric(), o.numeric()
        if b.lo <= 0 <= b.hi:
            m = max(abs(a.lo), abs(a.hi))
            return Interval(-m, m)
        qs = [_div(x, y) for x in (a.lo, a.hi) for y in (b.lo, b.hi)]
        return Interval(min(qs), max(qs))

    def abs(self) -> "Interval":
        a = self.numeric()
        if a.lo >= 0:
            return self
        if a.hi <= 0:
            return -self
        return Interval(0, max(-a.lo, a.hi))

    # -- comparison narrowing: the pair of (self, other) when the comparison holds, or None
    def lt(self, o: "Interval"):
        a = _mk(self.lo, min_hi(self.hi, add_hi(o.hi, -1)))
        b = _mk(max_lo(o.lo, add_lo(self.lo, 1)), o.hi)
        return (a, b) if a is not None and b is not None else None

    def le(self, o: "Interval"):
        a = _mk(self.lo, min_hi(self.hi, o.hi))
        b = _mk(max_lo(o.lo, self.lo), o.hi)
        return (a, b) if a is not None and b is not None else None

    def eq(self, o: "Interval"):
        both = self.intersection(o)
        return (both, both) if both is not None else None

    def ne(self, o: "Interval"):
        a, b = self, o
        if o.is_singleton():
            a = self._without(o.lo)
        if self.is_singleton():
            b = o._without(self.lo)
        return (a, b) if a is not None and b is not None else None

    def _without(self, n: Bound) -> "Interval | None":
        if self.lo == self.hi == n:
            return None
        if self.lo == n:
            return _mk(add_lo(n, 1), self.hi)
        if self.hi == n:
            return _mk(self.lo, add_hi(n, -1))
        return self

    # -- printing (thesis notation)
    def __str__(self) -> str:
        if self.is_singleton():
            return f"{{{fmt_bound(self.lo)}}}"
        lo = "(-∞" if self.lo == -inf else f"[{fmt_bound(self.lo)}"
        hi = "∞)" if self.hi == inf else f"{fmt_bound(self.hi)}]"
        return f"{lo}, {hi}"


def _mk(lo: Bound, hi: Bound) -> "Interval | None":
    return Interval(lo, hi) if not surely_lt(hi, lo) else None


def _add(a: Bound, b: Bound) -> Bound:
    if a in (inf, -inf) and b in (inf, -inf) and a != b:
        raise ValueError("inf - inf")
    return a + b


def _mul(a: Bound, b: Bound) -> Bound:
    if a == 0 or b == 0:
        return 0
    return a * b


def _div(a: Bound, b: Bound) -> Bound:
    if b in (inf, -inf):
        return 0 if a not in (inf, -inf) else (inf if (a > 0) == (b > 0) else -inf)
    if a in (inf, -inf):
        return inf if (a > 0) == (b > 0) else -inf
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q
