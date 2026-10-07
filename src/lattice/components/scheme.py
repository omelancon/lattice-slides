"""Corrections to Pygments' highlighting (spec 3.13): binding sites in Scheme, and Lattice samples in Markdown.

Pygments' Scheme lexer marks every symbol that directly follows ``(`` as ``Name.Function``, with no
notion of context, so ``(let ((i 0)) ...)`` paints ``i`` as a call and ``(lambda (x) ...)`` paints
``x`` as a call. This filter walks the token stream with a stack of open lists and retypes the
symbols that a binding form introduces as ``Name.Variable``: the head of each binding of ``let``,
``let*``, ``letrec``, ``letrec*``, ``do`` and ``fluid-let``, every symbol of the formals of
``let-values`` and ``let*-values``, and the parameters of ``lambda``, ``define-values`` and each
``case-lambda`` clause. Procedure names keep the call colour: the head of ``(define (f ...))`` is
already ``Name.Function``, and the name of a named ``let`` becomes one, like the calls it answers to.
Nothing else in the stream changes.

``LatticeMarkdownLexer`` shows the YAML body of a component sample inside a Markdown block as plain text
instead of handing it to a Pygments lexer that happens to share the component's name (``arrow``).
"""
from __future__ import annotations

from dataclasses import dataclass

from pygments.filter import Filter
from pygments.lexer import Lexer
from pygments.lexers import get_lexer_by_name
from pygments.lexers.markup import MarkdownLexer
from pygments.token import Keyword, Name, Punctuation, String, Text, Whitespace
from pygments.util import ClassNotFound

# head of a form -> role of the list that follows it (after the name of a named let)
FORMS = {"let": "bindings", "let*": "bindings", "letrec": "bindings", "letrec*": "bindings", "do": "bindings",
         "fluid-let": "bindings", "let-values": "values", "let*-values": "values", "lambda": "params",
         "define-values": "params"}
NAMED = {"let"}  # forms whose second element may be a procedure name
CLAUSES = {"case-lambda"}


@dataclass
class _List:
    role: str | None = None  # form, bindings, binding, values, values-binding, params, clauses, clause
    n: int = 0  # elements seen so far
    expect_at: int = -1  # for a form: index of the list it introduces
    expect: str | None = None  # and the role of that list
    head: str = ""


def _child_role(parent: _List) -> str | None:
    if parent.role == "form" and parent.n == parent.expect_at:
        return parent.expect
    if parent.role == "bindings":
        return "binding"
    if parent.role == "values":
        return "values-binding"
    if parent.role in ("values-binding", "clause") and parent.n == 0:
        return "params"
    if parent.role == "clauses":
        return "clause"
    return None


class SchemeBindingFilter(Filter):
    def filter(self, lexer, stream):
        stack: list[_List] = []
        for ttype, value in stream:
            if ttype is Punctuation and value == "(":
                child = _List(role=_child_role(stack[-1]) if stack else None)
                if stack:
                    stack[-1].n += 1
                stack.append(child)
            elif ttype is Punctuation and value == ")":
                if stack:
                    stack.pop()
            elif value.strip() and stack:
                top = stack[-1]
                symbol = ttype in Name or ttype in Keyword
                if top.n == 0 and symbol and top.role is None:
                    if value in FORMS:
                        top.role, top.expect_at, top.expect, top.head = "form", 1, FORMS[value], value
                    elif value in CLAUSES:
                        top.role = "clauses"
                elif top.role == "form" and symbol and top.n == 1 and top.head in NAMED:
                    ttype = Name.Function  # named let: the name is a procedure, like its calls
                    top.expect_at = 2
                elif top.role == "binding" and top.n == 0 and symbol:
                    ttype = Name.Variable
                elif top.role == "params" and symbol and value != ".":
                    ttype = Name.Variable
                top.n += 1
            yield ttype, value


class LatticeMarkdownLexer(MarkdownLexer):
    """Pygments' Markdown lexer, reading the fences of a Lattice sample as Lattice does (spec 3.13).

    Pygments hands the body of a fenced block to the lexer named by its info string. In a Lattice deck a
    registered component name wins over a lexer of the same name, and a component that reads a YAML body
    shares its name with an unrelated language only by accident (``arrow`` is also a Pygments lexer, whose
    error tokens would paint the sample red). Such a body is shown as a plain block, like the samples of the
    other components and of ``timeline``.
    """

    def _handle_codeblock(self, match):
        from .base import REGISTRY  # late: the registry module imports the components that import this one

        comp = REGISTRY.get(match.group("lang").strip())
        if comp is None or comp.body != "yaml":
            yield from super()._handle_codeblock(match)
            return
        yield match.start("initial"), String.Backtick, match.group("initial")
        yield match.start("lang"), String.Backtick, match.group("lang")
        if match.group("afterlang") is not None:
            yield match.start("whitespace"), Whitespace, match.group("whitespace")
            yield match.start("extra"), Text, match.group("extra")
        yield match.start("newline"), Whitespace, match.group("newline")
        yield match.start("code"), String, match.group("code")
        yield match.start("terminator"), String.Backtick, match.group("terminator")


# The rules of the parent name its callback directly, not through the class: point them at the override (the
# lexer compiles its rules on first use, so they can be set after the class).
LatticeMarkdownLexer.tokens = {
    state: [(r[0], LatticeMarkdownLexer._handle_codeblock, *r[2:])
            if isinstance(r, tuple) and len(r) > 1 and getattr(r[1], "__name__", "") == "_handle_codeblock" else r
            for r in rules]
    for state, rules in MarkdownLexer.tokens.items()}


def lexer_for(lang: str) -> Lexer:
    """The Pygments lexer of ``lang`` (``text`` when unknown); the Scheme lexer carries the filter, and
    Markdown reads the fences of Lattice samples as Lattice does."""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return get_lexer_by_name("text")
    if lexer.name == "Scheme":
        lexer.add_filter(SchemeBindingFilter())
    elif isinstance(lexer, MarkdownLexer):
        lexer = LatticeMarkdownLexer(**lexer.options)
    return lexer
