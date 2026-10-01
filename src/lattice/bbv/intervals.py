"""Integer intervals with the widening of thesis figure 2.

An interval is ``[lo, hi]`` with ``lo <= hi``, bounds being integers or ``±inf``. Widening moves a
bound that grew to the next *threshold* at or beyond it, so that ascending chains stabilize:
``{0} ∪ {1} = [0, 1]``, ``[0, 1] ∪ [1, 2] = [0, 2]``, ``[0, 2] ∪ [1, 3]`` widens to ``[0, 127]``, then
``[0, 128]``, ``[0, 2^31 - 1]``, ``[0, 2^31]``, ``[0, 2^63 - 1]``, ``[0, 2^63]``, ``[0, ∞)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import inf

Bound = int | float  # an int, or ±inf

THESIS_THRESHOLDS = [0, 1, 2, 127, 128, 2**31 - 1, 2**31, 2**63 - 1, 2**63]
THESIS_THRESHOLDS = sorted({t for t in THESIS_THRESHOLDS} | {-t for t in THESIS_THRESHOLDS}
                           | {-129, -2**31 - 1, -2**63 - 1} | {inf, -inf})
SIGN_THRESHOLDS = [-inf, -1, 0, 1, inf]


def thresholds_named(name: str) -> list[Bound] | None:
    if name == "thesis":
        return THESIS_THRESHOLDS
    if name == "sign":
        return SIGN_THRESHOLDS
    if name == "none":
        return None
    raise ValueError(f"unknown thresholds {name!r}; use thesis, sign, none or a list")


@dataclass(frozen=True)
class Interval:
    lo: Bound
    hi: Bound

    def __post_init__(self):
        if self.lo > self.hi:
            raise ValueError(f"empty interval [{self.lo}, {self.hi}]")

    @staticmethod
    def full() -> "Interval":
        return Interval(-inf, inf)

    @staticmethod
    def of(n: int) -> "Interval":
        return Interval(n, n)

    def is_full(self) -> bool:
        return self.lo == -inf and self.hi == inf

    def is_singleton(self) -> bool:
        return self.lo == self.hi and self.lo != inf and self.lo != -inf

    def contains(self, other: "Interval") -> bool:
        return self.lo <= other.lo and other.hi <= self.hi

    def union(self, other: "Interval") -> "Interval":
        return Interval(min(self.lo, other.lo), max(self.hi, other.hi))

    def intersection(self, other: "Interval") -> "Interval | None":
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return Interval(lo, hi) if lo <= hi else None

    def widen(self, new: "Interval", thresholds: list[Bound] | None) -> "Interval":
        """Widening with thresholds: a bound that grew moves to the next threshold beyond it."""
        if thresholds is None:
            return self.union(new)
        lo, hi = min(self.lo, new.lo), max(self.hi, new.hi)
        if lo < self.lo:
            lo = max([t for t in thresholds if t <= lo], default=-inf)
        if hi > self.hi:
            hi = min([t for t in thresholds if t >= hi], default=inf)
        return Interval(lo, hi)

    # -- arithmetic
    def __add__(self, o: "Interval") -> "Interval":
        return Interval(_add(self.lo, o.lo), _add(self.hi, o.hi))

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __sub__(self, o: "Interval") -> "Interval":
        return self + (-o)

    def __mul__(self, o: "Interval") -> "Interval":
        ps = [_mul(a, b) for a in (self.lo, self.hi) for b in (o.lo, o.hi)]
        return Interval(min(ps), max(ps))

    def quotient(self, o: "Interval") -> "Interval":
        """Integer division truncating toward zero, for a divisor interval not containing 0 only
        partially known: any divisor gives the conservative result."""
        if o.lo <= 0 <= o.hi:
            m = max(abs(self.lo), abs(self.hi))
            return Interval(-m, m)
        qs = [_div(a, b) for a in (self.lo, self.hi) for b in (o.lo, o.hi)]
        return Interval(min(qs), max(qs))

    def abs(self) -> "Interval":
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Interval(0, max(-self.lo, self.hi))

    # -- comparison narrowing: the pair of (self, other) when the comparison holds, or None
    def lt(self, o: "Interval"):
        a = _mk(self.lo, min(self.hi, _add(o.hi, -1)))
        b = _mk(max(o.lo, _add(self.lo, 1)), o.hi)
        return (a, b) if a is not None and b is not None else None

    def le(self, o: "Interval"):
        a = _mk(self.lo, min(self.hi, o.hi))
        b = _mk(max(o.lo, self.lo), o.hi)
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

    def _without(self, n: int) -> "Interval | None":
        if self.lo == self.hi == n:
            return None
        if self.lo == n:
            return Interval(n + 1, self.hi)
        if self.hi == n:
            return Interval(self.lo, n - 1)
        return self

    # -- printing (thesis notation)
    def __str__(self) -> str:
        if self.is_singleton():
            return f"{{{fmt_bound(self.lo)}}}"
        lo = "(-∞" if self.lo == -inf else f"[{fmt_bound(self.lo)}"
        hi = "∞)" if self.hi == inf else f"{fmt_bound(self.hi)}]"
        return f"{lo}, {hi}"


def fmt_bound(n: Bound) -> str:
    """Large bounds near a power of two print as ``2^31-1``, as in the thesis figures."""
    if n in (inf, -inf):
        return "∞" if n > 0 else "-∞"
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


def _mk(lo: Bound, hi: Bound) -> "Interval | None":
    return Interval(lo, hi) if lo <= hi else None


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
