"""Merge heuristics (thesis 2.2.3, 3.4 and appendix A): a heuristic picks the closest pair of
contexts under a distance function (algorithm 2.11)."""
from __future__ import annotations

import random
from typing import Callable

from .types import Context, Type

Distance = Callable[[Context, Context], float]

_NUM = Type.of("num")
_FX = Type.of("fx")
_FL = Type.of("fl")
_UNLIKELY = Type.of("bg")


def _names(a: Context, b: Context) -> list[str]:
    return a.vars() + [v for v in b.vars() if v not in a]


def similarity(a: Context, b: Context) -> float:
    """Hamming distance per variable, with a bias against contexts that are too broad or too
    specific (``context-distance-similarity*`` in the implementation)."""
    names = _names(a, b)
    bits = sum(a.get(n).hamming(b.get(n)) for n in names)
    if not names:
        return 0.0
    spec_a = sum(a.get(n).count() for n in names) / len(names)
    spec_b = sum(b.get(n).count() for n in names) / len(names)
    usefulness = abs(spec_a - 1) + abs(spec_b - 1)
    return bits * 1_000_000 + 999_999 / (usefulness + 1)


def arithmetic(a: Context, b: Context) -> float:
    """Merge contexts holding a possible bignum first, keep pure fixnum or flonum contexts apart
    (``context-distance-arithmetic*`` in the implementation)."""
    names = _names(a, b)
    bits = 0
    unlikely = [False, False]
    exact_fx = [False, False]
    exact_fl = [False, False]
    mixed = [False, False]
    loss = False
    for n in names:
        ts = [a.get(n), b.get(n)]
        bits += ts[0].hamming(ts[1])
        for i, t in enumerate(ts):
            if not t.is_any() and not t.intersection(_UNLIKELY).is_bottom():
                unlikely[i] = True
            if t.subset(_NUM) and t.count() > 1:
                mixed[i] = True
            if t.subset(_FX):
                exact_fx[i] = True
                if not ts[1 - i].subset(_FX):
                    loss = True
                if exact_fl[i]:
                    mixed[i] = True
            if t.subset(_FL):
                exact_fl[i] = True
                if not ts[1 - i].subset(_FL):
                    loss = True
                if exact_fx[i]:
                    mixed[i] = True
    if unlikely[0] and unlikely[1]:
        penalty = 0.1
    elif ((exact_fx[0] and not mixed[0] and (exact_fl[1] or mixed[1]))
          or (exact_fx[1] and not mixed[1] and (exact_fl[0] or mixed[0]))
          or (exact_fl[0] and not mixed[0] and (exact_fx[1] or mixed[1]))
          or (exact_fl[1] and not mixed[1] and (exact_fx[0] or mixed[0]))):
        penalty = 100
    elif loss:
        penalty = 10 if not (mixed[0] or mixed[1]) else 2
    else:
        penalty = 1
    n = len(names)
    return bits * (n * penalty) ** n if n else 0.0


def closest_pair(distance: Distance) -> Callable[[list[Context], random.Random], tuple[Context, Context]]:
    def select(contexts: list[Context], rng: random.Random) -> tuple[Context, Context]:
        best, best_d = None, float("inf")
        for i in range(len(contexts)):
            for j in range(i + 1, len(contexts)):
                d = distance(contexts[i], contexts[j])
                if d < best_d:
                    best, best_d = (contexts[i], contexts[j]), d
        return best

    return select


def random_pair(contexts: list[Context], rng: random.Random) -> tuple[Context, Context]:
    i = rng.randrange(len(contexts))
    j = rng.randrange(len(contexts) - 1)
    if j >= i:
        j += 1
    return contexts[i], contexts[j]


HEURISTICS = {
    "similarity": closest_pair(similarity),
    "arithmetic": closest_pair(arithmetic),
    "random": random_pair,
}
