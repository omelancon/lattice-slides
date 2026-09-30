"""Basic block versioning: the model behind the ``bbv-anim`` and ``bbv-cfg`` components.

- :mod:`types`: the type lattice and contexts
- :mod:`prims`: primitive operations and type tests
- :mod:`ir`: programs, the ``.bbv`` text syntax, liveness
- :mod:`sbbv`: Static Basic Block Versioning (thesis chapter 2)
- :mod:`lv`: Lambda Versioning (thesis chapter 3)
- :mod:`heuristics`: merge heuristics
- :mod:`trace`: events to frames
- :mod:`layout`: per-frame positions
"""
from .ir import Program, parse
from .types import Context, Type

__all__ = ["Program", "parse", "Context", "Type"]
