"""Basic block versioning: the type lattice, the text syntax, SBBV and ΛV on the thesis examples,
frames and layout, and the two components (spec 8.8 and 9.1)."""
from pathlib import Path

import pytest

from lattice.build import build_deck, check_deck
from lattice.bbv.ir import ProgramError, parse
from lattice.bbv.layout import layout_frames
from lattice.bbv.lv import LambdaVersioning
from lattice.bbv.rich import plain
from lattice.bbv.sbbv import Specializer
from lattice.bbv.trace import VersioningTrace
from lattice.bbv.types import Context, Type

PROGRAMS = Path(__file__).resolve().parent.parent / "examples" / "07-basic-block-versioning" / "programs"


def program(name: str):
    return parse((PROGRAMS / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------ types and contexts

def test_type_notation():
    assert str(Type.of("fx")) == "fx"
    assert str(Type.of("fx", "fl", "bg")) == "fx | bg | fl"
    assert str(Type.of("fx").complement()) == "!fx"
    assert str(Type.parse("!(fx | fl)")) == "!(fx | fl)"
    assert str(Type.parse("bool")) == "bool"
    assert Type.parse("any").is_any() and str(Type.bottom()) == "⊥"
    assert Type.parse("fx | #f").intersection(Type.of("#f").complement()) == Type.of("fx")
    assert Type.function("square").subset(Type.of("proc"))
    assert str(Type.function("square")) == "proc(square)"


def test_context_narrowing_and_classes():
    c = Context({"a": Type.any(), "b": Type.any()})
    c = c.equate("a", "b").narrow("a", Type.of("fx"))
    assert c.get("b") == Type.of("fx")  # the whole class is narrowed
    assert c.lines() == ["a/b: fx"]
    d = c.set("b", Type.of("fl"))
    assert d.lines() == ["a: fx", "b: fl"]
    u = c.union(d)
    assert u.get("b") == Type.of("fx", "fl") and u.lines() == ["a: fx", "b: fx | fl"]
    assert c.restrict(["b"]).lines() == ["b: fx"]
    assert c != d and c == Context({"a": Type.of("fx"), "b": Type.of("fx")}).equate("a", "b")


def test_intervals_widen_like_figure_2():
    from lattice.bbv.intervals import THESIS_THRESHOLDS, Interval

    chain = [Interval.of(0)]
    while True:
        prev = chain[-1]
        nxt = prev.widen(Interval(prev.lo + 1, prev.hi + 1), THESIS_THRESHOLDS)  # i ∪ (i + 1)
        if nxt == prev:
            break
        chain.append(nxt)
    assert [str(i) for i in chain] == ["{0}", "[0, 1]", "[0, 2]", "[0, 127]", "[0, 128]", "[0, 2^31-1]", "[0, 2^31]",
                                       "[0, 2^63-1]", "[0, 2^63]", "[0, ∞)"]
    assert Interval(1, 3).widen(Interval(1, 3), THESIS_THRESHOLDS) == Interval(1, 3)
    assert Interval(0, 5).widen(Interval(-1, 5), None) == Interval(-1, 5)


def test_interval_arithmetic_and_narrowing():
    from math import inf

    from lattice.bbv.intervals import Interval

    assert Interval(1, inf) * Interval(1, inf) == Interval(1, inf)
    assert Interval(1, inf) - Interval(1, 1) == Interval(0, inf)
    assert Interval(-2, 3) * Interval(-1, 4) == Interval(-8, 12)
    assert Interval(-inf, inf).lt(Interval(0, 0)) == (Interval(-inf, -1), Interval(0, 0))
    assert Interval(0, 0).lt(Interval(-inf, 0)) is None  # 0 < x never holds when x <= 0
    assert Interval(5, 5).ne(Interval(5, 5)) is None
    assert Type.parse("fx [0, 100]").refined() == Type.integer(0, 100).refined()
    assert str(Type.integer(2**70, 2**70 + 1).refined()) == "bg [2^70, 2^70+1]"
    assert Type.integer(0, 5).intersection(Type.integer(6, 9)).is_bottom()
    assert str(Type.of("fx").union(Type.integer(0, 5).refined())) == "fx"  # unknown fixnum: the interval is lost


def test_comparison_narrowing_rules():
    from lattice.bbv.prims import DEFAULT_PRIMS

    gt = DEFAULT_PRIMS[">"].narrow
    yes, no = gt([Type.of("fx", "bg"), Type.integer(0, 0)])
    assert str(yes[0]) == "fx | bg [1, ∞)" and str(no[0]) == "fx | bg (-∞, 0]"
    yes, no = gt([Type.integer(5, 9).refined(), Type.integer(10, 10)])
    assert yes is None and str(no[0]) == "fx [5, 9]"
    yes, no = DEFAULT_PRIMS["<="].narrow([Type.of("fx", "fl"), Type.of("fx")])  # a flonum may be involved
    assert yes == no == [Type.of("fx", "fl"), Type.of("fx")]


# ------------------------------------------------------------ text syntax

def test_parse_gives_blocks_their_live_variables():
    p = program("find.bbv")
    find = p.functions["find"]
    assert find.blocks["A"].params == ["p", "lst"]
    assert find.blocks["G"].params == ["p", "lst", "#res"] and find.blocks["G"].is_return
    assert find.blocks["A"].successors() == ["B", "L"]


def test_parse_errors_point_at_the_line():
    with pytest.raises(ProgramError, match="line 3.*unknown block"):
        parse("function f(x)\nA:  goto B\nB:  goto C\n")
    with pytest.raises(ProgramError, match="does not end"):
        parse("function f(x)\nA:  y = fx+(x, 1)\n")
    with pytest.raises(ProgramError, match="positional goto arguments"):
        parse("function f(x)\nA:  goto B(1)\nB:  return x\n")
    with pytest.raises(ProgramError, match="undefined variables"):
        parse("function f(x)\nA:  return y\n")
    p = parse("function f(x)\nA:  goto B(i=x)\nB(i):  return i\n")
    assert p.functions["f"].blocks["B"].params == ["x", "i"]
    p = parse("function g(n: fx | bg, m: fx [0, 100])\nA:  if >(n, m) goto B else goto C\nB:  return n\nC:  return m\n")
    assert str(p.functions["g"].param_types["m"]) == "fx [0, 100]"
    assert [str(a) for a in p.functions["g"].blocks["A"].instrs[0].args] == ["n", "m"]
    with pytest.raises(ProgramError, match="not a predicate"):
        parse("function f(x)\nA:  if car(x) goto B else goto B\nB:  return x\n")


# ------------------------------------------------------------ SBBV (thesis figure 6)

def loop_versions(spec, block):
    return [v for v in spec.final_versions() if v.block.name == block]


def test_sbbv_find_matches_figure_6():
    spec = Specializer(program("find.bbv"), limit=2)
    spec.run()
    a = sorted(loop_versions(spec, "A"), key=lambda v: v.id)
    assert [v.label for v in a] == ["A1", "A2"]
    assert str(a[0].context) == "p: any, lst: any" and str(a[1].context) == "p: proc, lst: any"
    # the loop entered from A2 checks procedure? no more: B2 turned its test into a goto
    b2 = next(v for v in loop_versions(spec, "B") if v.label == "B2")
    assert [ln.text for ln in b2.body if not ln.removed] == ["goto D"]
    assert b2.body[0].removed and "procedure?" in b2.body[0].text
    # every redundant pair? test disappeared; the entry test, procedure? in B1 and the truthiness test
    # of the call's result remain (tests_remaining counts every if left, not only type tests)
    assert spec.tests_remaining() == 4 and spec.merges == 0
    assert not any(v.block.name in ("K", "I", "M") for v in spec.final_versions())


def test_sbbv_limit_one_merges_the_loop_entry():
    spec = Specializer(program("find.bbv"), limit=1)
    spec.run()
    assert spec.merges == 1
    assert [v.label for v in loop_versions(spec, "A")] == ["A1"]
    j2 = loop_versions(spec, "J2")[0]
    assert spec.by_id[j2.edges[0].dst].label == "A1"  # the loop goes back to the generic entry


def test_sbbv_ignores_intervals_but_honours_annotations():
    prog = parse("function f(n: fx | bg)\nA:  k = 3\n    if >(n, k) goto B else goto C\nB:  return n\nC:  return k\n")
    spec = Specializer(prog, limit=2)
    spec.run()
    entry = next(v for v in spec.final_versions() if v.is_entry)
    assert str(entry.context) == "n: fx | bg"
    b = next(v for v in spec.final_versions() if v.block.name == "B")
    c = next(v for v in spec.final_versions() if v.block.name == "C")
    assert b.context.get("n").range is None and c.context.get("k") == Type.of("fx")


def test_sbbv_is_deterministic():
    a = VersioningTrace(program("find.bbv"), limit=2)
    b = VersioningTrace(program("find.bbv"), limit=2)
    assert a.frames == b.frames and a.tables == b.tables
    for heuristic in ("similarity", "arithmetic", "random"):
        c = VersioningTrace(program("find.bbv"), limit=1, heuristic=heuristic, seed=7)
        d = VersioningTrace(program("find.bbv"), limit=1, heuristic=heuristic, seed=7)
        assert c.frames == d.frames


# ------------------------------------------------------------ ΛV (thesis figures 14 and 16)

def test_lv_power4_specializes_entries_and_return_points():
    spec = LambdaVersioning(program("power4.bbv"), limit=3, entry="power4")
    spec.run()
    entries = {v.label: str(v.context) for v in spec.final_versions() if v.is_entry and v.function == "square"}
    assert "x: fl" in entries.values() and "x: any" in entries.values()
    a1 = next(v for v in spec.final_versions() if v.label == "A1")
    returns = [e for e in a1.edges if e.kind == "return"]
    assert len({e.dst for e in returns}) >= 3  # fixnum, flonum and generic return points
    # a flonum entry only reaches the flonum exit: one return point
    b_fl = next(v for v in spec.final_versions() if v.function == "power4" and v.block.name == "B"
                and v.context.get("y") == Type.of("fl"))
    assert len([e for e in b_fl.edges if e.kind == "return"]) == 1
    # exits of square are indexed once per contract
    z1 = next(v for v in spec.final_versions() if v.label == "Z1")
    assert spec.return_index[z1.id] == 2


def test_lv_fact_checks_the_argument_once():
    spec = LambdaVersioning(program("fact.bbv"), limit=2, entry="fact", heuristic="arithmetic")
    spec.run()
    fact = [v for v in spec.final_versions() if v.function == "fact"]
    entries = sorted(str(v.context) for v in fact if v.is_entry)
    assert entries == ["n: any", "n: fx"]
    fx_entry = next(v for v in fact if v.is_entry and str(v.context) == "n: fx")
    # a fixnum path exists through every block of the loop body, and its recursive call uses the
    # specialized entry: the argument's type is checked once (the overflow return points lead back
    # to the generic path, as in figure 16)
    fx = {v.block.name for v in fact if v.context.get("n") == Type.of("fx")}
    assert {"A", "B", "C", "D", "E", "F", "G"} <= fx
    e_fx = next(v for v in fact if v.block.name == "E" and str(v.context) == "n: fx, #res: fx")
    callee = spec.by_id[next(e.dst for e in e_fx.edges if e.kind == "call")]
    assert callee is fx_entry
    # the operator entries used along that path perform no type test at all
    for cs in [v for v in fact if v.call is not None and v.context.get("n") == Type.of("fx")
               and v.context.get("#res") in (Type.of("fx"), Type.any())]:
        entry = spec.by_id[cs.call.entry]
        stack, seen = [entry.id], set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            stack += [e.dst for e in spec.by_id[i].edges if e.kind in ("goto", "true", "false")]
        assert not any(ln.text.startswith("if ") and "?(" in ln.text and not ln.removed
                       for i in seen for ln in spec.by_id[i].body or []), cs.label


def test_sbbv_on_the_same_program_treats_calls_as_opaque():
    spec = Specializer(program("fact.bbv"), limit=2, entry="fact")
    spec.run()
    fact = [v for v in spec.final_versions() if v.function == "fact"]
    assert all(not v.is_entry or str(v.context) == "n: any" for v in fact)
    assert all(e.kind != "call" for v in fact for e in v.edges)


# ------------------------------------------------------------ frames and layout

def test_trace_frames_have_captions_marks_and_meta():
    t = VersioningTrace(program("find.bbv"), limit=2)
    kinds = [m["event"] for m in t.meta]
    assert kinds[0] == "start" and kinds[-1] == "done" and "specialize" in kinds
    assert t.frames[0]["nodes"]["1"]["mark"] == "new"
    spec_frame = next(f for f, m in zip(t.frames, t.meta) if m["event"] == "specialize")
    assert spec_frame["caption"].startswith("`op:specialize` `v:A1|find/A`") and spec_frame["nodes"]["1"]["mark"] == "active"
    assert plain(spec_frame["caption"]).startswith("specialize A1 · queue ")
    assert plain(next(f["caption"] for f, m in zip(t.frames, t.meta) if m["event"] == "dequeue")) == "dequeue A1 p: any · lst: any"
    assert spec_frame["panel"]["queue"] and "checks" in spec_frame["panel"]
    assert all(m.get("block", "find/A").startswith("find/") for m in t.meta)
    t1 = VersioningTrace(program("find.bbv"), limit=1)
    merge = next(f for f, m in zip(t1.frames, t1.meta) if m["event"] == "merge")
    gone_next = t1.frames[t1.frames.index(merge)]
    assert any(n.get("mark") == "gone" for n in gone_next["nodes"].values())
    assert "merge" in [n.get("mark") for n in merge["nodes"].values()] or "merged" in [n.get("mark") for n in merge["nodes"].values()]


def test_hidden_functions_and_event_filter():
    t = VersioningTrace(program("fact.bbv"), algorithm="lv", limit=2, entry="fact", heuristic="arithmetic")
    assert all(t.spec.by_id[int(v)].function == "fact" for f in t.frames for v in f["nodes"])
    call_line = t.tables["versions"]["1"]["code"][0]["text"]
    assert call_line.startswith("call =[X") and "-> B" in call_line
    few = VersioningTrace(program("fact.bbv"), algorithm="lv", limit=2, entry="fact", heuristic="arithmetic",
                          events=["merge", "done"], until=5)
    assert len(few.frames) == 5 and all(m["event"] in ("merge", "done") for m in few.meta)


def test_layout_margins_cover_back_edges():
    """The runs into a first rank (up to 0.62 of a rank gap in bbv.js, SLOT_IN) and the runs past the ends of the
    ranks (END_GAP) lie inside the margin, in that order from the rank."""
    from lattice.bbv import layout

    assert 0.62 * layout.GAP_RANK + 3 < layout.END_GAP * layout.GAP_RANK < layout.MARGIN - 5


def test_layout_keeps_versions_on_their_rank():
    t = VersioningTrace(program("find.bbv"), limit=2)
    for direction in ("TB", "LR"):
        box, positions = layout_frames(t.tables, t.frames, ["label", "context"], None, direction)
        assert box["width"] > 0 and box["height"] > 0 and box["direction"] == direction
        last = positions[-1]
        a1, a2 = last["1"], last[next(v for v in last if t.tables["versions"][v]["label"] == "A2")]
        same_rank = a1[1] == a2[1] if direction == "TB" else a1[0] == a2[0]
        assert same_rank
        for pos in positions:
            for vid, p in pos.items():
                w, h = box["sizes"][vid]
                assert 0 <= p[0] and p[0] + w <= box["width"] and 0 <= p[1] and p[1] + h <= box["height"]


# ------------------------------------------------------------ components

DECK = """
# Find {#find}
:::: columns
::: column
```bbv-cfg {#src program="find.bbv" follow=trace}
```
:::
::: column
```bbv-anim {#trace program="find.bbv" limit=2}
panel: [queue]
```
:::
::::

# Fact {#fact}
```bbv-anim {#lv program="fact.bbv" algorithm=lv entry=fact heuristic=arithmetic}
```

# Inline {#inline}
```bbv-anim {#inl limit=1}
source: |
  function f(x)
  A:  if fixnum?(x) goto B else goto C
  B:  return fx+(x, 1)
  C:  return x
```
"""


def test_components_build_and_follow(deck):
    root = deck({"talk.md": DECK,
                 "find.bbv": (PROGRAMS / "find.bbv").read_text(), "fact.bbv": (PROGRAMS / "fact.bbv").read_text()})
    d = build_deck(root, use_cache=False)
    s = d.slides["find"]
    trace = d.instances["find/trace"]
    src = d.instances["find/src"]
    assert trace["positions"] == src["positions"] == s.steps > 20
    assert src["data"]["highlight"][0] is not None and src["data"]["static"]
    assert trace["data"]["frames"]["count"] == s.steps and trace["data"]["box"]["direction"] == "TB"
    assert d.instances["fact/lv"]["positions"] > 50
    assert d.instances["inline/inl"]["positions"] >= 5
    assert "bbv-anim" in d.component_names and "bbv-cfg" in d.component_names


def test_component_reports_program_errors(deck):
    root = deck({"talk.md": '# A\n```bbv-anim {program="p.bbv"}\n```\n', "p.bbv": "function f(x)\nA:  goto Z\n"})
    diags = check_deck(root, use_cache=False)
    assert any(d.code == "LT022" and "unknown block" in d.message for d in diags.items)
    root = deck({"talk.md": '# A\n```bbv-anim {program="missing.bbv"}\n```\n'})
    assert any(d.code == "LT045" for d in check_deck(root, use_cache=False).items)


# ------------------------------------------------------------ abstract interpretation (thesis 1.1)

def test_absint_sum_to_n_matches_figures_1_and_2():
    from lattice.bbv.absint import AbstractInterpreter

    ai = AbstractInterpreter(program("sum-to-n.bbv"))
    ai.run()
    b = ai.contexts["B"]
    assert str(b.get("i")) == "fx | bg [0, ∞)" and str(b.get("acc")) == "fx | bg [0, ∞)"
    assert str(ai.after["D"].get("#res")) == "fx | bg [0, ∞)"  # a non-negative integer, as the thesis says
    chain = [(k, t) for k, t in ai.history["B.i"]]
    assert [t for _, t in chain] == ["{0}", "[0, 1]", "[0, 2]", "[0, 127]", "[0, 128]", "[0, 2^31-1]", "[0, 2^31]",
                                     "[0, 2^63-1]", "[0, 2^63]", "[0, ∞)"]
    assert [k for k, _ in chain] == ["", "∪", "∪", "∇", "∪", "∇", "∪", "∇", "∪", "∇"]  # figure 2's solid and dashed edges
    assert not ai.truncated and ai.steps < 60


def test_absint_fact_matches_figure_4():
    from lattice.bbv.absint import AbstractInterpreter

    ai = AbstractInterpreter(program("fact-loop.bbv"))
    ai.run()
    b, c, d = ai.contexts["B"], ai.contexts["C"], ai.contexts["D"]
    assert b.get("i").range is None and str(b.get("acc")) == "fx | bg [1, ∞)"
    assert str(c.get("i")) == "fx | bg [1, ∞)" and str(c.get("acc")) == "fx | bg [1, ∞)"
    assert str(d.get("acc")) == "fx | bg [1, ∞)" and str(ai.after["D"].get("#res")) == "fx | bg [1, ∞)"
    assert ai.steps == 7
    # without narrowing the loop body learns nothing about i
    ai2 = AbstractInterpreter(program("fact-loop.bbv"), narrowing=False)
    ai2.run()
    assert ai2.contexts["C"].get("i").range is None


def test_absint_dead_branches_and_types_only():
    from lattice.bbv.absint import AbstractInterpreter

    ai = AbstractInterpreter(parse("function f(x: fx [1, 9])\nA:  if >(x, 0) goto B else goto C\nB:  return x\nC:  return 0\n"))
    ai.run()
    assert ai.contexts["C"] is None and ("A", "C", "false") in ai.dead and str(ai.contexts["B"].get("x")) == "fx [1, 9]"
    # on find, abstract interpretation keeps p: any at the loop entry: the procedure? test stays
    ai = AbstractInterpreter(program("find.bbv"))
    ai.run()
    assert str(ai.contexts["A"].get("p")) == "any" and str(ai.contexts["D"].get("p")) == "proc"


def test_absint_shows_infinite_bounds_only_for_any_integer():
    from lattice.bbv.absint import value_text
    from lattice.bbv.trace import AbstractTrace

    # any integer with no interval: (-∞, ∞), as in figure 4
    assert value_text(Type.of("fx", "bg")) == "fx | bg (-∞, ∞)"
    # a fixnum is bounded and a bignum is two rays: neither is (-∞, ∞)
    assert value_text(Type.of("fx")) == "fx" and value_text(Type.of("bg")) == "bg"
    assert value_text(Type.parse("fx [0, 10]")) == "fx [0, 10]" and value_text(Type.of("fl")) == "fl"
    # fixnum? on x: any gives a fixnum with no interval on the true branch
    t = AbstractTrace(parse("function g(x)\nA:  if fixnum?(x) goto B else goto C\nB:  return x\nC:  fail\n"))
    last = t.frames[-1]["nodes"]
    lines = {t.tables["versions"][vid]["label"]: n["lines"] for vid, n in last.items()}
    assert lines["B"] == ["x: fx"] and lines["C"] == ["x: !fx"]
    assert not any("∞" in f["caption"] for f in t.frames)
    # fact: i is any integer at the loop entry and keeps its (-∞, ∞)
    fact = AbstractTrace(program("fact-loop.bbv"))
    assert "i: fx | bg (-∞, ∞)" in fact.frames[-1]["nodes"]["2"]["lines"]


def test_abstract_trace_frames():
    from lattice.bbv.trace import AbstractTrace

    t = AbstractTrace(program("sum-to-n.bbv"), history=["B.i"])
    kinds = [m["event"] for m in t.meta]
    assert kinds[0] == "start" and kinds[-1] == "done" and "propagate" in kinds and "instruction" not in kinds
    widened = next(f for f in t.frames if f["caption"].startswith("`op:widen`"))
    assert "`var:i`: `ty:fx [0, 2]` ∪ `ty:fx [1, 3]` ∇ `ty:fx [0, 127]`" in widened["caption"]
    assert any(n.get("mark") == "widened" for n in widened["nodes"].values())
    assert t.frames[-1]["panel"]["B.i"][3] == "∇ [0, 127]"
    assert all("lines" in n for f in t.frames for n in f["nodes"].values())
    assert t.frames[0]["nodes"]["2"]["state"] == "dead" and t.frames[-1]["nodes"]["2"]["state"] == "done"
    assert t.tables["versions"]["2"]["context"]  # sizing lines
    fine = AbstractTrace(program("fact-loop.bbv"), granularity="instruction", until=6)
    assert len(fine.frames) == 6 and "instruction" in [m["event"] for m in fine.meta]
    assert all(m.get("algo") for m in fine.meta)


def test_rich_markup_round_trips():
    from lattice.bbv import rich

    text = rich.join([f"{rich.op('merge')} {rich.ver('A2', 'find/A')} → {rich.ver('A1', 'find/A')}",
                      rich.context(["p: any", "lst: fx | bg [0, 127]"]), rich.tag("queued"), ""])
    assert text == ("`op:merge` `v:A2|find/A` → `v:A1|find/A` · `var:p`: `ty:any` · `var:lst`: `ty:fx | bg [0, 127]`"
                    " · `tag:queued`")
    assert rich.plain(text) == "merge A2 → A1 · p: any · lst: fx | bg [0, 127] · queued"
    assert rich.parse("x `rm:pair?(lst)` never holds") == [("", "x "), ("rm", "pair?(lst)"), ("", " never holds")]
    assert rich.plain("") == "" and rich.parse("") == []
    # instruction notes of the three algorithms carry the markup; the specialized code does not
    t = VersioningTrace(program("find.bbv"), limit=2, granularity="instruction")
    removed = next(f for f, m in zip(t.frames, t.meta) if m["event"] == "instruction" and "`rm:" in f["caption"])
    assert plain(removed["caption"]).startswith("test removed ")
    assert all("`" not in c["text"] for v in t.tables["versions"].values() for c in v["code"])


# ------------------------------------------------------------ intervals in SBBV and ΛV (paper section 3.2)

def test_sbbv_intervals_converge_by_widening_at_merges():
    spec = Specializer(program("sum-to-n.bbv"), limit=2, intervals=True)
    spec.run()
    assert not spec.truncated and spec.merges > 0
    b = sorted(loop_versions(spec, "B"), key=lambda v: v.id)
    assert str(b[0].context.get("i")) == "fx [0, 1]"  # {0} ∪ {1}, the first step of the figure 2 chain
    assert all(v.context.get("i").range is not None for v in b)
    # the second loop version was widened all the way: a plain union would never converge
    assert str(b[-1].context.get("i")).endswith("∞)")
    # the same program converges under ΛV too, and intervals stay off by default
    lv = LambdaVersioning(program("sum-to-n.bbv"), limit=2, intervals=True)
    lv.run()
    assert not lv.truncated
    off = Specializer(program("sum-to-n.bbv"), limit=2)
    off.run()
    assert all(v.context.get("i").range is None for v in loop_versions(off, "C") if v.label == "C2")


def test_sbbv_intervals_keep_annotations_and_decide_overflow_checks():
    prog = parse("function f(n: fx [0, 100])\nA:  m = fx+?(n, 1)\n    if m goto B else goto C\nB:  return m\nC:  return #f\n")
    spec = Specializer(prog, limit=2, intervals=True)
    spec.run()
    entry = next(v for v in spec.final_versions() if v.is_entry)
    assert str(entry.context) == "n: fx [0, 100]"
    assert entry.body[1].removed and entry.body[2].text == "goto B"  # m is fx [1, 101]: no overflow possible
    assert not any(v.block.name == "C" for v in spec.final_versions())
    b = next(v for v in spec.final_versions() if v.block.name == "B")
    assert str(b.context.get("m")) == "fx [1, 101]"
    big = parse("function g(n: fx)\nA:  m = fx+?(n, 1)\n    if m goto B else goto C\nB:  return m\nC:  return #f\n")
    spec = Specializer(big, limit=2, intervals=True)
    spec.run()
    assert any(v.block.name == "C" for v in spec.final_versions())  # n is any fixnum: the overflow check stays


def test_merge_caption_names_widened_variables():
    t = VersioningTrace(program("sum-to-n.bbv"), limit=2, intervals=True)
    merges = [f["caption"] for f in t.frames if "`op:merge`" in f["caption"]]
    assert any("`tag:widened`" in c for c in merges)
    assert plain(merges[0]).startswith("merge B")


# ------------------------------------------------------------ vector lengths as symbolic bounds (paper section 3.3)

def test_symbolic_bound_rules_of_the_paper():
    from math import inf

    from lattice.bbv.intervals import Interval, Sym, join_hi, join_lo, max_lo, maxfix, min_hi

    v, w = Sym("v"), Sym("w")
    v1 = Sym("v", 1)
    assert str(v1) == "⟦v⟧-1" and str(Interval(v, v)) == "{⟦v⟧}" and str(Interval(0, v1)) == "[0, ⟦v⟧-1]"
    # lower bounds drop the symbol under addition, upper bounds keep it while the offset stays nonnegative
    assert Interval(v1, v1) + Interval(3, 3) == Interval(2, maxfix() + 2)  # (⟦v⟧-1) + 3: lower 2, upper overflows
    assert Interval(v1, v1) + Interval(1, 1) == Interval(0, v)
    assert Interval(0, v1) + Interval(2, 2) == Interval(2, maxfix() + 1)  # upper bound: overflow, not a fixnum
    assert Interval(v, v) - Interval(1, 1) == Interval(-1, v1)
    assert Interval(v1, v1) + Interval(Sym("w", 2), Sym("w", 2)) == Interval(-3, 2 * maxfix() - 3)
    assert (-Interval(0, v1)) == Interval(-(maxfix() - 1), 0)
    # comparisons are decided only when the numeric range of the symbol settles them
    assert Interval(0, v1).lt(Interval(v, v)) == (Interval(0, v1), Interval(1, v))  # ⟦v⟧-1 < ⟦v⟧ always holds
    assert Interval(v, v).lt(Interval(0, v1)) is None
    with pytest.raises(ValueError):
        Interval(v, v1)  # ⟦v⟧ > ⟦v⟧-1: empty
    assert Interval(v, 0) == Interval(v, 0)  # ⟦v⟧ may be 0: not empty
    # narrowing of x < y: upper bounds prefer the symbolic candidate, lower bounds the numeric one
    assert min_hi(0, v1) == v1 and min_hi(-5, v1) == -5 and min_hi(v, v1) == v1
    assert max_lo(1, v) == 1 and max_lo(v, 1) == 1 and max_lo(-2, v) == v
    assert Interval(0, 0).lt(Interval(v, v)) == (Interval(0, v1), Interval(1, v))
    # a join keeps a symbol only when it bounds both sides
    assert join_hi(0, v) == v and join_hi(5, v1) == maxfix() - 1 and join_hi(v1, Sym("v", 3)) == v1
    assert join_lo(0, v) == 0 and join_lo(v1, Sym("v", 3)) == Sym("v", 3) and join_lo(v, w) == 0
    # widening: a symbolic upper bound that grew goes to ⟦v⟧, a symbol that became a number stops at its value
    from lattice.bbv.intervals import MACHINE_THRESHOLDS as T
    assert Interval(0, Sym("v", 3)).widen(Interval(0, Sym("v", 2)), T) == Interval(0, v)
    assert Interval(0, 0).widen(Interval(0, v), T) == Interval(0, v)  # 0 <= ⟦v⟧ always: the symbol bounds both
    assert Interval(0, v1).widen(Interval(0, 5), T) == Interval(0, maxfix() - 1)
    assert Interval(v1, v1).widen(Interval(Sym("v", 2), v1), T) == Interval(-2, v1)
    assert Interval(0, 0).widen(Interval(0, 1), T) == Interval(0, 1)
    assert Interval(0, inf).union(Interval(v, v)) == Interval(0, inf)


def test_vec_type_and_symbolic_annotations():
    assert str(Type.parse("vector")) == "vec" and Type.of("vec").subset(Type.any())
    assert str(Type.parse("fx [0, ⟦v⟧-1]")) == "fx [0, ⟦v⟧-1]" and str(Type.parse("fx {⟦v⟧}")) == "fx {⟦v⟧}"
    assert str(Type.parse("!vec")) == "!vec"
    assert Type.parse("fx | bg {⟦v⟧}").refined() == Type.parse("fx {⟦v⟧}")  # a length is a fixnum
    assert Type.parse("fx [0, ⟦v⟧-1]").symbols() == {"v"}


def test_symbols_follow_the_class_of_their_vector():
    c = Context({"v": Type.of("vec"), "i": Type.parse("fx [0, ⟦v⟧-1]")})
    assert str(c) == "v: vec, i: fx [0, ⟦v⟧-1]"
    # the vector leaves the context: the bound becomes its numeric value
    assert str(c.restrict(["i"])) == "i: fx [0, maxfix-1]"
    # renamed through a goto or a call: the symbol follows
    assert str(c.rename({"w": "v"}, ["w", "i"])) == "w: vec, i: fx [0, ⟦w⟧-1]"
    # an alias keeps the symbol alive when the vector variable is reassigned
    c2 = c.equate("w", "v")
    assert str(c2) == "v/w: vec, i: fx [0, ⟦v⟧-1]"
    assert str(c2.set("v", Type.of("fx"))) == "v: fx, i: fx [0, ⟦w⟧-1], w: vec"
    assert str(c.set("v", Type.of("pair"))) == "v: pair, i: fx [0, maxfix-1]"
    # a class that is no longer exactly a vector loses its symbols
    assert str(c.union(Context({"v": Type.of("pair"), "i": Type.parse("fx [0, ⟦v⟧-1]")}))) == "v: pair | vec, i: fx [0, maxfix-1]"
    # a union keeps a symbol that bounds both sides, drops one of a different vector
    d = Context({"v": Type.of("vec"), "i": Type.parse("fx [1, ⟦v⟧-1]")})
    assert str(c.union(d)) == "v: vec, i: fx [0, ⟦v⟧-1]"
    e = Context({"v": Type.of("vec"), "u": Type.of("vec"), "i": Type.parse("fx [0, ⟦u⟧-1]")})
    assert str(c.union(e).get("i")) == "fx [0, maxfix-1]"
    # an annotation naming a variable that is not a vector is widened at once
    assert str(Context({"i": Type.parse("fx [0, ⟦v⟧-1]")})) == "i: fx [0, maxfix-1]"
    assert str(Context({"v": Type.of("vec"), "i": Type.parse("fx [⟦v⟧-2, ⟦v⟧]")}).restrict(["i"])) == "i: fx [-2, maxfix]"


def test_contexts_of_the_same_shape_are_one_version():
    # two paths bind the vector under different names before reaching D: the symbols are named after
    # the class representative, so both reach the same version of D
    prog = parse("""
function f(p: proc)
A:  call p() -> A2
A2: if #res goto B else goto C
B:  call p() -> B2
B2: u = #res
    n = ##vector-length(u)
    goto D(v=u, m=n)
C:  call p() -> C2
C2: w = #res
    n2 = ##vector-length(w)
    goto D(v=w, m=n2)
D(v, m):  return m
""")
    spec = Specializer(prog, limit=4, intervals=True)
    spec.run()
    d = [v for v in spec.final_versions() if v.block.name == "D"]
    assert len(d) == 1 and str(d[0].context) == "p: proc, v: vec, m: fx {⟦v⟧}"
    b2 = next(v for v in spec.final_versions() if v.block.name == "B2")
    assert str(b2.context_after.get("n")) == "fx {⟦#res⟧}"  # named after the class representative
    # and a symbol of another vector is a different shape
    assert Context({"v": Type.of("vec"), "i": Type.parse("fx [0, ⟦v⟧-1]")}) != Context({"v": Type.of("vec"), "i": Type.of("fx")})


def test_vector_length_and_bound_checks():
    prog = parse("""
function get(v: vec, i: fx)
A:  n = ##vector-length(v)
    if fx>=(i, 0) goto B else goto K
B:  if fx<(i, n) goto C else goto K
C:  m = vector-length(v)
    if fx<(i, m) goto D else goto K
D:  return ##vector-ref(v, i)
K:  fail
""")
    spec = Specializer(prog, limit=2, intervals=True)
    spec.run()
    a = next(v for v in spec.final_versions() if v.block.name == "A")
    assert str(a.context_after.get("n")) == "fx {⟦v⟧}"
    b = next(v for v in spec.final_versions() if v.block.name == "B")
    assert str(b.context.get("i")) == "fx [0, ⟦v⟧-1]" or str(b.context.get("i")) == "fx [0, maxfix]"
    c = next(v for v in spec.final_versions() if v.block.name == "C")
    assert str(c.context.get("i")) == "fx [0, ⟦v⟧-1]"
    assert c.body[1].removed and c.body[2].text == "goto D"  # the second length is the same symbol: decided
    # the vector is gone (reassigned by the return): the length becomes a fixnum in 0..maxfix
    anon = parse("function h(p: proc)\nA:  call p() -> B\nB:  n = ##vector-length(#res)\n    return n\n")
    s2 = Specializer(anon, limit=2, intervals=True)
    s2.run()
    exit_ = next(v for v in s2.final_versions() if v.is_exit)
    assert str(exit_.context_after.get("n")) == "fx [0, maxfix]"


def test_findv_matches_figure_7():
    """Thesis appendix D, figure 7: all bound checks and overflow checks disappear, procedure? is
    tested once, in the first iteration."""
    for cls in (Specializer, LambdaVersioning):
        spec = cls(program("findv.bbv"), limit=2, intervals=True)
        spec.run()
        assert not spec.truncated
        findv = [v for v in spec.final_versions() if v.function == "findv"]
        kept = [(v.label, ln.text) for v in findv for ln in v.body or [] if ln.text.startswith("if ") and not ln.removed]
        tests = {t.split(" goto")[0] for _, t in kept}
        assert tests == {"if vector?(x)", "if fx<(i, len)", "if procedure?(p)", "if #res"}, kept
        assert sum(1 for _, t in kept if "procedure?" in t) == 1
        assert not any(v.block.name == "O" for v in findv)  # the overflow path is gone, K stays for procedure?
        heads = sorted(str(v.context.get("i")) for v in findv if v.block.name == "L")
        assert heads == ["fx [1, ⟦x⟧]", "fx {0}"]
        body = next(v for v in findv if v.block.name == "C2" and str(v.context.get("i")) == "fx [0, ⟦x⟧-1]")
        assert str(body.context.get("len")) == "fx [1, ⟦x⟧]"
        inc = next(v for v in findv if v.block.name == "G2")
        assert str(inc.context.get("i2")) == "fx [1, ⟦x⟧]"  # ⟦x⟧-1 + 1 cannot overflow


def test_absint_findv_fixed_point_with_symbols():
    from lattice.bbv.absint import AbstractInterpreter

    ai = AbstractInterpreter(program("findv.bbv"), "findv")
    ai.run()
    assert not ai.truncated
    assert str(ai.contexts["C2"].get("i")) == "fx [0, ⟦x⟧-1]" and str(ai.contexts["L"].get("i")) == "fx [0, ⟦x⟧]"
    assert ai.contexts["K"] is not None and ai.contexts["O"] is None  # only the procedure? failure remains


def test_lv_return_points_translate_symbols_to_the_caller():
    prog = parse("""
function last(v: vec)
A:  n = ##vector-length(v)
    j = fx-(n, 1)
    if fx>=(j, 0) goto B else goto C
B:  return j
C:  return -1

function user(x: vec, y: vec)
A:  call last(x) -> B
B:  k = #res
    call last(y) -> C
C:  return #res
""")
    spec = LambdaVersioning(prog, limit=3, entry="user", intervals=True)
    spec.run()
    b = [v for v in spec.final_versions() if v.function == "user" and v.block.name == "B"]
    assert sorted(str(v.context.get("#res")) for v in b) == ["fx [0, ⟦x⟧-1]", "fx {-1}"]
    c = [v for v in spec.final_versions() if v.function == "user" and v.block.name == "C"]
    assert {str(v.context.get("#res")) for v in c} == {"fx [0, ⟦y⟧-1]", "fx {-1}"}
    # the callee's local variable has no name in the caller: its exit contract names the parameter
    exits = {str(v.context_after.restrict(["v", "#res"])) for v in spec.final_versions() if v.function == "last" and v.is_exit}
    assert "v: vec, #res: fx [0, ⟦v⟧-1]" in exits


def test_intervals_break_ties_in_the_heuristics():
    from lattice.bbv.heuristics import arithmetic, range_distance, similarity

    fx, v = Type.of("fx"), Type.of("vec")
    a = Context({"v": v, "i": Type.parse("fx [0, ⟦v⟧-1]")})
    b = Context({"v": v, "i": Type.parse("fx [1, ⟦v⟧-1]")})
    c = Context({"v": v, "i": Type.parse("fx [0, 10]")})
    d = Context({"v": v, "i": fx})
    e = Context({"v": v, "i": Type.of("fx", "bg")})
    assert range_distance(a.get("i"), a.get("i")) == 0 and range_distance(a.get("i"), b.get("i")) == 0.25
    assert range_distance(a.get("i"), c.get("i")) == 0.75 and range_distance(a.get("i"), d.get("i")) == 0.5
    for dist in (similarity, arithmetic):
        assert dist(a, a) < dist(a, b) < dist(a, c) < dist(a, e)  # a type difference outweighs any interval difference


def test_bbv_anim_accepts_the_interval_options(deck):
    prog = (PROGRAMS / "findv.bbv").read_text(encoding="utf-8")
    root = deck({"talk.md": """# Vectors

```bbv-anim {#t program="findv.bbv" algorithm=sbbv limit=2 intervals=true thresholds=machine fixnum_bits=61}
panel: [queue, checks]
```
""", "findv.bbv": prog})
    d = build_deck(root, use_cache=False)
    data = d.instances["vectors/t"]["data"]
    assert any("⟦x⟧" in line for v in data["tables"]["versions"].values() for line in v["context"])
    assert data["frames"]["count"] > 20


# ------------------------------------------------------------ enlarging a block (spec 9.5)

def test_blocks_are_clickable_by_default_with_everything_shown(deck):
    from lattice.bbv.layout import node_size

    root = deck({"talk.md": DECK + """
# Absint {#ai}
```abstract-interp-anim {#ai program="find.bbv"}
```
""", "find.bbv": (PROGRAMS / "find.bbv").read_text(),
                 "fact.bbv": (PROGRAMS / "fact.bbv").read_text()})
    d = build_deck(root, use_cache=False)
    for inst in ("find/trace", "find/src", "fact/lv", "ai/ai"):
        data = d.instances[inst]["data"]
        zoom = data["zoom"]
        assert zoom["show"] == ["label", "context", "code", "after"]
        assert set(zoom["sizes"]) == set(data["tables"]["versions"])
        for vid, v in data["tables"]["versions"].items():
            # the enlarged block holds at least what the drawing shows, and its exit context
            w, h = zoom["sizes"][vid]
            dw, dh = data["box"]["sizes"][vid]
            assert w >= dw and h >= dh
            assert [w, h] >= list(node_size(v, zoom["show"]))
    lv = d.instances["fact/lv"]["data"]
    with_after = [vid for vid, v in lv["tables"]["versions"].items() if v["after"]]
    assert with_after
    vid = with_after[0]
    assert lv["zoom"]["sizes"][vid][1] > list(node_size(lv["tables"]["versions"][vid], ["label", "context", "code"]))[1]
    # abstract interpretation: sized on the largest entry and exit contexts over the frames
    ai = d.instances["ai/ai"]["data"]
    frames = ai["frames"]["frames"]
    for vid in ai["tables"]["versions"]:
        longest_after = max(len(f["nodes"][vid].get("after", [])) for f in frames)
        assert ai["zoom"]["sizes"][vid][1] >= 22 + 12 + 16 * (len(ai["tables"]["versions"][vid]["code"]) + longest_after)


def test_clickable_off_and_clickable_show(deck):
    find = (PROGRAMS / "find.bbv").read_text()
    root = deck({"talk.md": """
# Off {#off}
```bbv-anim {#a program="find.bbv" clickable=off}
```

# Body {#body}
```bbv-cfg {#c program="find.bbv"}
clickable: off
```

# Some {#some}
```bbv-anim {#b program="find.bbv"}
show: [label]
clickable_show: [label, code]
```
""", "find.bbv": find})
    d = build_deck(root, use_cache=False)
    assert "zoom" not in d.instances["off/a"]["data"] and "zoom" not in d.instances["body/c"]["data"]
    zoom = d.instances["some/b"]["data"]["zoom"]
    assert zoom["show"] == ["label", "code"]
    root = deck({"talk.md": '# A\n```bbv-anim {program="find.bbv"}\nclickable_show: [label, tooltip]\n```\n', "find.bbv": find})
    diags = check_deck(root, use_cache=False)
    assert any(x.code == "LT022" and "clickable_show" in x.message for x in diags.items)
    # `after` is for the enlarged block only
    root = deck({"talk.md": '# A\n```bbv-anim {program="find.bbv"}\nshow: [label, after]\n```\n', "find.bbv": find})
    assert any(x.code == "LT022" and "show" in x.message for x in check_deck(root, use_cache=False).items)


def test_clickable_options_are_not_passed_to_program_functions(deck):
    root = deck({"talk.md": '# A\n```bbv-anim {#a program="prog.py:make" clickable=off}\nclickable_show: [code]\n```\n',
                 "prog.py": "def make():\n    return 'function f(x)\\nA:  return x\\n'\n"})
    d = build_deck(root, use_cache=False)
    assert "zoom" not in d.instances["a/a"]["data"]


# ------------------------------------------------------------------ thresholds by name, predicates of prims

FINDV_AI = """function findv(v)
A:  goto L(i=0)
L:  if vector?(v) goto M else goto K
K:  fail
M:  len = ##vector-length(v)
    if >=(i, len) goto N else goto P
N:  return #f
P:  if pred(v, i) goto R else goto S
R:  return i
S:  if fixnum?(i) goto T else goto X
T:  i2 = fx+(i, 1)
    goto L(i=i2)
X:  i3 = ##+(i, 1)
    goto L(i=i3)
"""


def test_thresholds_may_name_the_fixnum_range():
    """Spec 9.6: a list of thresholds names `machine`, `sign`, `maxfix` and `minfix`; with `maxfix` the
    index of findv stays a fixnum in every block, where the machine thresholds widen past it."""
    from lattice.bbv.absint import AbstractInterpreter
    from lattice.bbv.intervals import thresholds_from

    assert thresholds_from(["sign", "maxfix", 5], 61) == [float("-inf"), -1, 0, 1, 5, 2**60 - 1, float("inf")]
    assert thresholds_from(["minfix"], 8) == [-128] and thresholds_from(["machine"]) == thresholds_from("machine")
    with pytest.raises(ValueError, match="unknown name 'maxint'"):
        thresholds_from(["maxint"])
    prog = parse(FINDV_AI, {"pred": {"args": ["any", "any"], "result": "bool"}})
    ai = AbstractInterpreter(prog, thresholds=["sign", "maxfix"])
    ai.run()
    assert str(ai.contexts["L"].get("i")) == "fx [0, maxfix]" and str(ai.contexts["M"].get("i")) == "fx [0, maxfix]"
    assert ai.contexts["X"] is None and ("S", "X", "false") in ai.dead  # the generic addition is never reached
    ai = AbstractInterpreter(prog, thresholds="machine")
    ai.run()
    assert "bg" in str(ai.contexts["M"].get("i"))  # 2^63-1 is the next machine threshold after maxfix


def test_prims_predicates_may_be_tested(deck):
    """Spec 9.5: the predicates of a `prims` option are known when the program is checked."""
    body = "prims: {pred: {args: [any, any], result: bool}}\nthresholds: [sign, maxfix]\nsource: |\n" + "".join(
        "  " + line + "\n" for line in FINDV_AI.splitlines())
    root = deck({"talk.md": f"# A\n```abstract-interp-anim {{#ai}}\n{body}```\n"})
    assert not check_deck(root, use_cache=False).items
    text = root.read_text()
    root.write_text(text.replace("[sign, maxfix]", "[sign, maxint]"))
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and "unknown name 'maxint'" in items[0].message
    root.write_text(text.replace("prims: {pred: {args: [any, any], result: bool}}\n", ""))
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT022"] and "'pred' is not a predicate" in items[0].message


FINDV_OVF = FINDV_AI.replace("""T:  i2 = fx+(i, 1)
    goto L(i=i2)
X:  i3 = ##+(i, 1)
    goto L(i=i3)
""", """T:  i2 = fx+?(i, 1)
    if i2 goto T2 else goto O
T2: goto L(i=i2)
O:  i3 = ##+(i, 1)
    goto L(i=i3)
X:  i4 = ##+(i, 1)
    goto L(i=i4)
""")


def test_without_vector_bounds():
    """Spec 9.5: with `vector_bounds` off a vector length is a number in [0, maxfix] and an annotation naming
    one is widened at the entry; the overflow check of findv still disappears with thresholds that stop
    at maxfix-1 and maxfix, but SBBV keeps the second bound check of figure 7, against another length."""
    from lattice.bbv.absint import AbstractInterpreter
    from lattice.bbv.intervals import thresholds_from

    assert thresholds_from(["maxfix-1", "minfix+2", "maxfix - 3"], 8) == [-126, 124, 126]
    with pytest.raises(ValueError, match="unknown name"):
        thresholds_from(["maxfix*2"])
    prims = {"pred": {"args": ["any", "any"], "result": "bool"}}
    assert FINDV_OVF != FINDV_AI
    for bounds, after_test in ((True, "fx [0, ⟦v⟧-1]"), (False, "fx [0, maxfix-1]")):
        ai = AbstractInterpreter(parse(FINDV_OVF, prims), thresholds=["sign", "maxfix-1", "maxfix"],
                                 vector_bounds=bounds)
        ai.run()
        assert str(ai.contexts["L"].get("i")) == "fx [0, maxfix]" and str(ai.contexts["P"].get("i")) == after_test
        assert ai.contexts["O"] is None and ("T", "O", "false") in ai.dead  # the overflow branch is never reached
    ai = AbstractInterpreter(parse(FINDV_OVF, prims), thresholds=["sign", "maxfix"], vector_bounds=False)
    ai.run()
    assert ai.contexts["O"] is not None  # P widened past maxfix-1: fx+? may overflow
    ai = AbstractInterpreter(parse("function f(v, i: fx [0, ⟦v⟧-1])\nA:  return i\n"), vector_bounds=False)
    ai.run()
    assert str(ai.contexts["A"].get("i")) == "fx [0, maxfix-1]"
    for bounds in (True, False):
        spec = Specializer(program("findv.bbv"), limit=2, intervals=True, vector_bounds=bounds)
        spec.run()
        findv = [v for v in spec.final_versions() if v.function == "findv"]
        kept = {ln.text.split(" goto")[0] for v in findv for ln in v.body or [] if ln.text.startswith("if ") and not ln.removed}
        assert ("if fx<(i, len2)" in kept) is not bounds
        assert any("⟦" in str(v.context) for v in findv) is bounds


def test_vector_bounds_option(deck):
    body = ("vector_bounds: false\nprims: {pred: {args: [any, any], result: bool}}\nthresholds: [sign, maxfix-1, maxfix]\n"
            "source: |\n" + "".join("  " + line + "\n" for line in FINDV_OVF.splitlines()))
    root = deck({"talk.md": f"# A\n```abstract-interp-anim {{#ai}}\n{body}```\n"})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    from lattice.emit import emit_html

    assert "⟦" not in instance_data(emit_html(d), "a/ai")
    root.write_text(f"# A\n```bbv-anim {{#b intervals=true vector_bounds=false}}\nprogram: programs/findv.bbv\n```\n")
    (root.parent / "programs").mkdir()
    (root.parent / "programs" / "findv.bbv").write_text((PROGRAMS / "findv.bbv").read_text(encoding="utf-8"))
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items and "⟦" not in instance_data(emit_html(d), "a/b")


def instance_data(html: str, instance: str) -> str:
    import re

    return re.search(rf'id="lt-data-{re.escape(instance)}">(.*?)</script>', html, re.S).group(1)


# ------------------------------------------------------------ parts of the drawings as arrow ends (spec 8.9, 9.5)

def _parts_deck(deck, arrow_body: str, comp: str = "bbv-cfg", extra: str = ""):
    find = (PROGRAMS / "find.bbv").read_text(encoding="utf-8")
    return deck({"talk.md": f"# A\n```{comp} {{#g program=\"find.bbv\"}}\n```\n{extra}\n```arrow {{#w}}\n{arrow_body}```\n",
                 "find.bbv": find})


def _steps(d):
    return d.instances["a/w"]["data"]["steps"]


def test_arrow_at_blocks_and_edges_of_a_cfg(deck):
    root = _parts_deck(deck, "steps: [g.A, g.find/B, g.A->L, g.A->L:false, 'g.A->B:#t', g.F->G, g.J2->A:goto]\n")
    for cache in (False, True, True):  # the second and third builds read the render results from the cache
        d = build_deck(root, use_cache=cache)
        assert not d.diagnostics.items, d.diagnostics.items
        steps = _steps(d)
        assert all(s["to"] == "g" for s in steps)
        assert steps[0]["to_part"] == '.lt-bbv-node:is([data-vid="1"]):not(.lt-gone)'  # A is the first block
        assert steps[1]["to_part"] == '.lt-bbv-node:is([data-vid="3"]):not(.lt-gone)'  # A, L, B
        edge = '.lt-bbv-edge:is([data-key="1->2:false"]):not(.lt-gone) > .lt-bbv-edge-mark'
        assert steps[2]["to_part"] == steps[3]["to_part"] == edge
        assert '[data-key="1->3:true"]' in steps[4]["to_part"]  # #t is true
        assert ":return" in steps[5]["to_part"] and ":goto" in steps[6]["to_part"]


@pytest.mark.parametrize("ref, message", [
    ("g.Z", "no block 'Z'; the blocks are A, L, B"),
    ("g.A->E", "no edge A->E in this drawing; A goes to B (true), L (false)"),
    ("g.A->L:goto", "no goto edge A->L in this drawing (its edges to L are false)"),
    ("g.L->A", "no edge leaves L"),
    ("h.A", "no component with the id 'h' on this slide"),
    ("g.A:true", "a kind (`:true`) belongs to an edge"),
    ("g.foo/A", "function 'foo' is not drawn here (drawn: find)"),
    ("g.A->L:maybe", "unknown edge kind 'maybe'"),
    ("c.x", "component 'c' (code) names no parts"),
    ("{to: g.A, to_anchor: bullet}", "a `bullet` anchor needs a list item, not a part"),
])
def test_arrow_part_errors_are_lt063(deck, ref, message):
    root = _parts_deck(deck, f"steps: [{ref}]\n", extra="```code {#c lang=python}\nx = 1\n```\n")
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT063"] and message in items[0].message, items


def test_arrow_part_from_end_and_selectors(deck):
    """Both ends may be parts; an element name keeps `li.done` a CSS selector, but a component id wins."""
    root = _parts_deck(deck, "steps:\n  - {from: g.L, to: g.B}\n  - li.done\n  - map.A\n",
                       extra="```bbv-cfg {#map program=\"find.bbv\"}\n```\n")
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    s = _steps(d)
    assert s[0]["from"] == "g" and '[data-vid="2"]' in s[0]["from_part"] and '[data-vid="3"]' in s[0]["to_part"]
    assert s[1]["to"] == "li.done" and "to_part" not in s[1] and "to_name" not in s[1]
    assert s[2]["to"] == "map" and "to_part" in s[2]


def test_arrow_part_qualified_when_functions_share_a_block(deck):
    prog = "function f(x)\nA:  call g(x) -> B\nB:  return #res\nfunction g(y)\nA:  return y\n"
    root = deck({"talk.md": "# A\n```bbv-cfg {#g program=\"p.bbv\"}\n```\n```arrow {#w}\nsteps: [g.A]\n```\n",
                 "p.bbv": prog})
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT063"] and "write f/A or g/A" in items[0].message
    root.write_text("# A\n```bbv-cfg {#g program=\"p.bbv\"}\n```\n```arrow {#w}\nsteps: [g.g/A, g.f/A->B]\n```\n")
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    assert '[data-vid="3"]' in _steps(d)[0]["to_part"] and '[data-key="1->2:return"]' in _steps(d)[1]["to_part"]


def test_arrow_part_of_several_kinds_needs_a_kind():
    from lattice.components.base import ComponentError, RenderResult
    from lattice.components.bbv import _Drawing

    versions = {v: {"label": n, "name": n, "block": f"f/{n}", "function": "f"} for v, n in (("1", "A"), ("2", "L"))}
    data = {"tables": {"versions": versions, "program": {"functions": [{"name": "f", "blocks": [
        {"name": "A"}, {"name": "L"}]}]}},
        "frames": {"format": "full", "count": 1, "frames": [
            {"nodes": {"1": {}, "2": {}}, "edges": {"1->2:true": {}, "1->2:false": {}}}]}}
    drawing = _Drawing(RenderResult("", data))
    with pytest.raises(ComponentError, match="several kinds .*write A->L:false or A->L:true"):
        drawing.part("A->L")
    assert drawing.part("A->L:#f").selector.count("data-key") == 1


def test_arrow_at_versions_of_a_run(deck):
    """bbv-anim (spec 9.5): a block names its versions, a label one version; `drawn` follows the frames."""
    root = _parts_deck(deck, "steps: [g.B, g.A2, g.A->B, g.B2]\n", comp="bbv-anim",
                       extra="```timeline\ng end\nw ..end\n```\n")
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    steps = _steps(d)
    versions = d.instances["a/g"]["data"]["tables"]["versions"]
    vid = {v["label"]: k for k, v in versions.items()}
    assert steps[0]["to_part"] == f'.lt-bbv-node:is([data-vid="{vid["B1"]}"],[data-vid="{vid["B2"]}"]):not(.lt-gone)'
    assert steps[1]["to_part"] == f'.lt-bbv-node:is([data-vid="{vid["A2"]}"]):not(.lt-gone)'
    assert f'[data-key="{vid["A1"]}->{vid["B1"]}:true"]' in steps[2]["to_part"]
    assert f'[data-key="{vid["A2"]}->{vid["B2"]}:true"]' in steps[2]["to_part"]
    from lattice.components.bbv import BbvAnim

    result = d.instances["a/g"]
    from lattice.components.base import RenderResult

    part = BbvAnim().part(RenderResult("", result["data"], result["positions"]), "B2")
    assert part.drawn is not None and not part.drawn[0] and part.drawn[-1]


def test_arrow_at_a_version_never_shown_is_lt046(deck):
    root = _parts_deck(deck, "steps: [g.B2, g.A1, g.B2]\n", comp="bbv-anim",
                       extra="```timeline\nw 1\ng ..5\nw 2, g end\n```\n")
    items = check_deck(root, use_cache=False).items
    # step 1 is shown at slide step 0 only, where the run is at frame 0: B2 does not exist yet. Step 3 is shown
    # at the last frame, where B2 is drawn. A part drawn at some of its steps only would be silent.
    assert [x.code for x in items] == ["LT046"], items
    assert "step 1" in items[0].message and "'g.B2' is drawn at none of the steps" in items[0].message
    assert "slide step 0: position 0 of 'g'" in items[0].message


def test_arrow_part_block_wins_over_a_version_label(deck):
    prog = "function f(x)\nA:  if fixnum?(x) goto B else goto B1\nB:  return x\nB1: return x\n"
    root = deck({"talk.md": "# A\n```bbv-anim {#g program=\"p.bbv\"}\n```\n```arrow {#w}\nsteps: [g.B1, g.B]\n```\n"
                            "```timeline\ng end\nw 1\n```\n", "p.bbv": prog})
    d = build_deck(root, use_cache=False)
    items = d.diagnostics.items
    assert [x.code for x in items] == ["LT046"] and "is a block and also a version of block 'B'" in items[0].message
    versions = d.instances["a/g"]["data"]["tables"]["versions"]
    block_b1 = {k for k, v in versions.items() if v["block"] == "f/B1"}
    assert _steps(d)[0]["to_part"] == f'.lt-bbv-node:is([data-vid="{block_b1.pop()}"]):not(.lt-gone)'


def test_arrow_at_blocks_of_an_analysis(deck):
    sum_to_n = (Path(__file__).resolve().parent.parent / "user_manual" / "programs" / "sum-to-n.bbv").read_text()
    root = deck({"talk.md": "# A\n```abstract-interp-anim {#ai program=\"s.bbv\"}\n```\n```arrow {#w}\n"
                            "steps: [ai.B, 'ai.B->C:#t', ai.C->B, ai.B->D]\n```\n```timeline\nw 1, ai 3\nai ..end\nw ..end\n```\n",
                 "s.bbv": sum_to_n})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    assert '[data-vid="2"]' in d.instances["a/w"]["data"]["steps"][0]["to_part"]
    from lattice.components.base import RenderResult
    from lattice.components.bbv import AbstractInterpAnim

    r = d.instances["a/ai"]
    assert AbstractInterpAnim().part(RenderResult("", r["data"], r["positions"]), "B->D").drawn is None  # fixed CFG


SAME_TARGET = "function f(x)\nA:  if fixnum?(x) goto L else goto L\nL:  return x\n"


def test_both_outcomes_to_one_block_draw_two_edges(deck):
    """`if x goto L else goto L` has a `true` and a `false` edge in every drawing (they used to be both `true`)."""
    prog = parse(SAME_TARGET)
    assert prog.function("f").blocks["A"].edges() == [("L", "true"), ("L", "false")]
    root = deck({"talk.md": "# A\n```bbv-cfg {#g program=\"p.bbv\"}\n```\n"
                            "```arrow {#w}\nsteps: ['g.A->L:#t', g.A->L:false]\n```\n", "p.bbv": SAME_TARGET})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    frame = d.instances["a/g"]["data"]["frames"]["frames"][0]
    assert sorted(frame["edges"]) == ["1->2:false", "1->2:true"]
    assert '[data-key="1->2:true"]' in _steps(d)[0]["to_part"] and '[data-key="1->2:false"]' in _steps(d)[1]["to_part"]
    # without a kind, the two edges are of several kinds
    root.write_text("# A\n```bbv-cfg {#g program=\"p.bbv\"}\n```\n```arrow {#w}\nsteps: [g.A->L]\n```\n")
    items = check_deck(root, use_cache=False).items
    assert [x.code for x in items] == ["LT063"] and "several kinds" in items[0].message


def test_both_outcomes_to_one_block_in_an_analysis_and_a_run(deck):
    from lattice.bbv.trace import AbstractTrace

    prog = parse(SAME_TARGET)
    ai = AbstractTrace(prog)
    last = ai.frames[-1]["edges"]
    assert {k.split(":")[1] for k in last} == {"true", "false"} and not any(e.get("state") == "gone" for e in last.values())
    run = VersioningTrace(parse(SAME_TARGET), algorithm="sbbv")
    kinds = {k.split(":")[1] for f in run.frames for k in f["edges"]}
    assert {"true", "false"} <= kinds


CONSTANTS = """function f(n: fx)
A:  goto B(i=0)
B:  call g(i, 1) -> C
C:  return #res
function g(x, k)
E:  return k
"""


@pytest.mark.parametrize("algorithm", ["sbbv", "lv"])
def test_constants_keep_no_singleton_without_intervals(algorithm):
    """Spec 9.5: without `intervals`, contexts hold types only; a constant bound by `goto B(i=0)` or passed to a
    call used to enter the target with its singleton (`i: fx {0}`). With intervals it keeps it."""
    cls = Specializer if algorithm == "sbbv" else LambdaVersioning
    for intervals, want_i, want_k in ((False, "fx", "fx"), (True, "fx {0}", "fx {1}")):
        spec = cls(parse(CONSTANTS), limit=2, entry="f", intervals=intervals)
        spec.run()
        b = next(v for v in spec.final_versions() if v.block.name == "B")
        assert str(b.context.get("i")) == want_i, (intervals, str(b.context))
        if algorithm == "lv":
            e = next(v for v in spec.final_versions() if v.block.name == "E" and not v.generic)
            assert str(e.context.get("k")) == want_k, (intervals, str(e.context))


# ------------------------------------------------------------ paths (spec 9.5)

POLY = """function polynomial(x)
A:  if fixnum?(x) goto B else goto D
B:  y = fx*?(x, x)
    if y goto J else goto C
C:  y = ##*(x, x)
    goto J
D:  if flonum?(x) goto E else goto F
E:  y = fl*(x, x)
    goto J
F:  y = ##*(x, x)
    goto J
J(y):  if fixnum?(y) goto K else goto M
K:  r = fx+?(y, 1)
    if r goto R else goto L
R:  return r
L:  return ##+(y, 1)
M:  if flonum?(y) goto N else goto P
N:  return fl+(y, 1.0)
P:  return ##+(y, 1)
"""


def _poly_trace(paths, **kw):
    return VersioningTrace(parse(POLY), algorithm="sbbv", limit=3, heuristic="arithmetic", paths=paths, **kw)


def _marks(t, frame):
    labels = {k: v["label"] for k, v in t.tables["versions"].items()}
    return {labels[k]: n.get("mark") for k, n in frame["nodes"].items()}


def test_path_by_input_walks_the_versions_an_input_may_reach():
    t = _poly_trace([{"input": {"x": "fl"}}, {"input": {"x": "fx"}}])
    done, fl, fx = t.frames[-3:]
    assert t.meta[-3]["event"] == "done" and [m["event"] for m in t.meta[-2:]] == ["path", "path"]
    marks = _marks(t, fl)
    assert sorted(k for k, m in marks.items() if m == "path") == ["A1", "D1", "E1", "J3", "M1", "N1"]
    assert all(m == "dim" for k, m in marks.items() if k not in ("A1", "D1", "E1", "J3", "M1", "N1"))
    assert set(fl["nodes"]) == {k for k, n in done["nodes"].items() if n.get("mark") != "gone"}
    states = {e.get("state") for e in fl["edges"].values()}
    assert states == {"path", "dim"} and sum(e.get("state") == "path" for e in fl["edges"].values()) == 5
    assert fl["panel"] == done["panel"]
    assert plain(fl["caption"]) == "path x: fl · A1 → D1 → E1 → J3 → M1 → N1 · 2 tests"
    assert t.meta[-2]["blocks"] == [f"polynomial/{b}" for b in "ADEJMN"] and t.meta[-2]["algo"] == []
    # a fixnum may overflow: the path branches, so the chips are not read as a sequence
    on = {k for k, m in _marks(t, fx).items() if m == "path"}
    assert {"A1", "B1", "C1", "J1", "J5", "M2", "P1"} <= on and not on & {"D1", "E1", "J3", "N1"}
    assert "→" not in plain(fx["caption"]) and plain(fx["caption"]).startswith("path x: fx · A1 B1")


def test_path_by_versions_and_without_dimming():
    t = _poly_trace([{"versions": ["A1", "D1", "F1"], "dim": False, "caption": "the generic way"}])
    marks = _marks(t, t.frames[-1])
    assert {k for k, m in marks.items() if m == "path"} == {"A1", "D1", "F1"}
    assert all(m is None for k, m in marks.items() if k not in ("A1", "D1", "F1"))
    assert {e.get("state") for e in t.frames[-1]["edges"].values()} == {"path", None}
    assert t.frames[-1]["caption"] == "the generic way"
    t = _poly_trace([{"versions": ["A1", "B1"]}], caption="none")
    assert t.frames[-1]["caption"] == ""


@pytest.mark.parametrize("paths, kw, message", [
    ([{"input": {"z": "fl"}}], {}, "'z' is not a parameter of polynomial (its parameters: x)"),
    ([{"input": {"x": "float"}}], {}, "cannot read the type 'float'"),
    ([{"input": {"x": "fl"}, "versions": ["A1"]}], {}, "it does not combine with input"),
    ([{"versions": ["A1"], "overflow": "never"}], {}, "it does not combine with overflow"),
    ([{}], {}, "give versions (labels), or input (parameter types) and/or reads"),
    ([{"caption": "x"}], {}, "give versions (labels), or input"),
    ([{"input": {"x": "fl"}, "color": "red"}], {}, "unknown key(s) ['color']"),
    ([{"input": ["x"]}], {}, "input maps parameters of polynomial to types"),
    ([{"reads": "fl"}], {}, "reads lists types"),
    ([{"reads": ["fl", "float"]}], {}, "reads: cannot read the type 'float'"),
    ([{"reads": ["fl"], "reads_exhausted": []}], {}, "reads_exhausted lists types"),
    ([{"reads": ["fl"], "reads_exhausted": "never"}], {}, "reads_exhausted: cannot read the type 'never'"),
    ([{"input": {"x": "fx"}, "overflow": "sometimes"}], {}, "overflow is maybe, never or always"),
    ([{"input": {"x": "fx"}, "depth": 3}], {}, "unknown key(s) ['depth']"),
    ("x", {}, "paths: a list of paths"),
    ([{"versions": ["J2"]}], {}, "'J2' is not drawn at the end of the run"),
    ([{"input": {"x": "⊥"}}], {}, "does not admit this input"),
    ([{"versions": ["A1"], "dim": "no"}], {}, "dim is true or false"),
    ([{"input": {"x": "fl"}}], {"until": 10}, "remove until"),
])
def test_path_errors(paths, kw, message):
    args = {"algorithm": "sbbv", "limit": 3, "heuristic": "arithmetic", **kw}
    with pytest.raises(ValueError) as e:
        VersioningTrace(parse(POLY), paths=paths, **args)
    assert message in str(e.value)


def test_paths_in_a_deck_with_a_follower_and_an_arrow(deck):
    root = deck({"talk.md": """# A
```bbv-cfg {#src program="p.bbv" follow=run}
show: [label]
```
```bbv-anim {#run program="p.bbv" algorithm=sbbv heuristic=arithmetic limit=3}
paths:
  - input: {x: fl}
```
```arrow {#w}
steps: [null, run.D1]
```
```timeline
run ..end-1
run end, w 1
```
""", "p.bbv": POLY})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    run = d.instances["a/run"]
    hl = d.instances["a/src"]["data"]["highlight"]
    assert len(hl) == run["positions"] and isinstance(hl[-1], list) and len(hl[-1]) == 6
    assert all(not isinstance(h, list) for h in hl[:-1])
    root.write_text(root.read_text().replace("{x: fl}", "{y: fl}"))
    items = check_deck(root, use_cache=False).items
    assert any(x.code == "LT022" and "paths[0]: input: 'y' is not a parameter" in x.message for x in items), items



# ------------------------------------------------------------ paths through calls (spec 9.5, 0.31)

# The defense's polynomial and square, called from a main() that reads its argument.
POLY_SQUARE = """function main()
M:  x = read()
    call polynomial(x) -> N
N:  return #res

function polynomial(x)
A:  call square(x) -> B
B:  y = #res
    if fixnum?(y) goto C else goto F
C:  if fixnum?(x) goto D else goto F
D:  r = fx+?(y, x)
    if r goto R else goto E
R:  return r
E:  return ##+(y, x)
F:  if flonum?(y) goto G else goto J
G:  if flonum?(x) goto H else goto J
H:  return fl+(y, x)
J:  return ##+(y, x)

function square(x)
S:  if fixnum?(x) goto T else goto V
T:  y = fx*?(x, x)
    if y goto U else goto W
U:  return y
W:  return ##*(x, x)
V:  if flonum?(x) goto X else goto Z
X:  return fl*(x, x)
Z:  return ##*(x, x)
"""

FLONUM_WAY = ["M1", "A1", "S1", "V1", "X1", "B3", "F1", "G1", "H1", "N3"]


def _lv_trace(paths, program=POLY_SQUARE, **kw):
    args = {"algorithm": "lv", "limit": 3, "heuristic": "arithmetic", "entry": "main", **kw}
    return VersioningTrace(parse(program), paths=paths, **args)


def _on(t, frame):
    labels = {k: v["label"] for k, v in t.tables["versions"].items()}
    nodes = [labels[k] for k, n in frame["nodes"].items() if n.get("mark") == "path"]
    edges = {}
    for k, e in frame["edges"].items():
        if e.get("state") == "path":
            src, rest = k.split("->", 1)
            edges[f"{labels[src]}->{labels[rest.split(':')[0]]}"] = (e["kind"], e.get("label"), e.get("lit"))
    return nodes, edges


def test_path_through_calls_by_reads():
    """The request of the defense: the flonum returned by read() goes into square through its generic
    entry, out at its flonum exit, back to polynomial's flonum return point, then to main's."""
    t = _lv_trace([{"reads": ["fl"]}])
    frame = t.frames[-1]
    nodes, edges = _on(t, frame)
    assert sorted(nodes) == sorted(FLONUM_WAY)
    assert edges == {
        "M1->A1": ("call", None, None), "A1->S1": ("call", None, None), "S1->V1": ("false", None, None),
        "V1->X1": ("true", None, None), "A1->B3": ("return", "[2]", [2]), "B3->F1": ("goto", None, None),
        "F1->G1": ("goto", None, None), "G1->H1": ("goto", None, None), "M1->N3": ("return", "[3]", [3]),
    }
    assert plain(frame["caption"]) == "path (read) → fl · " + " → ".join(FLONUM_WAY) + " · 2 tests"
    assert {n.get("mark") for n in frame["nodes"].values()} == {"path", "dim"}
    assert {e.get("state") for e in frame["edges"].values()} == {"path", "dim"}
    meta = t.meta[-1]
    assert meta["event"] == "path" and meta["function"] == "main" and meta["algo"] == []
    assert meta["blocks"] == ["main/M", "polynomial/A", "square/S", "square/V", "square/X", "polynomial/B",
                              "polynomial/F", "polynomial/G", "polynomial/H", "main/N"]


def test_path_through_calls_matches_returns_to_their_call_site():
    """A fixnum may overflow in square: both exits, then only the return points of their indices (B5 for
    [1], not for [3]), and the fixnum side of polynomial; C2's flonum test cannot fail for this path."""
    t = _lv_trace([{"reads": ["fx"]}])
    nodes, edges = _on(t, t.frames[-1])
    assert set(nodes) == {"M1", "A1", "S1", "T1", "U1", "W1", "B1", "B5", "C1", "C2", "F2", "D1", "J1", "R1", "E1",
                          "N1", "N2"}
    assert edges["A1->B5"] == ("return", "[1] [3]", [1]) and edges["A1->B1"] == ("return", "[0]", [0])
    assert edges["M1->N1"] == ("return", "[0] [2] [4]", [0, 2]) and "M1->N3" not in edges
    assert "C2->F3" not in edges and "V1" not in nodes and "F3" not in nodes
    assert plain(t.frames[-1]["caption"]) == ("path (read) → fx · M1 A1 S1 T1 U1 W1 B1 B5 C1 C2 F2 D1 J1 R1 E1 N1 N2"
                                              " · 5 tests")


def test_path_overflow():
    """overflow: never keeps the fixnum way where fx*? and fx+? do not overflow; always takes the
    overflow branches only."""
    t = _lv_trace([{"reads": ["fx"], "overflow": "never"}, {"reads": ["fx"], "overflow": "always"}])
    never, always = (_on(t, f) for f in t.frames[-2:])
    assert never[0] == ["M1", "A1", "S1", "T1", "U1", "B1", "C1", "D1", "R1", "N2"]
    assert plain(t.frames[-2]["caption"]).startswith("path (read) → fx overflow never · M1 → A1 → S1 → T1 → U1")
    assert "U1" not in always[0] and "R1" not in always[0] and {"W1", "E1"} <= set(always[0])


def test_path_by_versions_through_calls():
    """The same path written by hand: the same marks, edges and lit indices, read as one sequence."""
    t = _lv_trace([{"reads": ["fl"]}, {"versions": FLONUM_WAY}])
    walked, listed = t.frames[-2:]
    assert _on(t, walked) == _on(t, listed)
    assert plain(listed["caption"]) == "path chosen versions · " + " → ".join(FLONUM_WAY) + " · 2 tests"


def test_path_input_is_optional_and_may_be_empty():
    """A main() without parameters: no input, input: {} and reads: [] all walk every version reached."""
    t = _lv_trace([{"input": {}}, {"reads": []}, {"input": None, "reads": []}])
    done = t.frames[-4]
    drawn = {k for k, n in done["nodes"].items() if n.get("mark") != "gone"}
    for f in t.frames[-3:]:
        assert {k for k, n in f["nodes"].items() if n.get("mark") == "path"} == drawn
    assert plain(t.frames[-3]["caption"]).startswith("path the program · ")


def test_path_walks_through_hidden_functions():
    """square hidden: the walk goes through it and still returns to A1's flonum return point."""
    t = _lv_trace([{"reads": ["fl"]}], functions=["main", "polynomial"])
    nodes, edges = _on(t, t.frames[-1])
    assert nodes == ["M1", "A1", "B3", "F1", "G1", "H1", "N3"]
    assert edges["A1->B3"] == ("return", "[2]", [2]) and t.meta[-1]["blocks"][0] == "main/M"


READ_LOOP = """function main()
L:  x = read()
    if fixnum?(x) goto L else goto E
E:  return x
"""


@pytest.mark.parametrize("entry, reaches_e", [
    ({"reads": ["fx", "fx", "fl"]}, True),
    ({"reads": ["fx", "fx"], "reads_exhausted": "fx"}, False),
    ({"reads": ["fx", "fx"], "reads_exhausted": ["fx"]}, False),
    ({"reads": ["fx", "fx"], "reads_exhausted": ["fx", "fl"]}, True),
    ({"reads": ["fx", "fx"]}, True),  # then any
    ({"reads": ["fx", "fx", "fl"], "reads_exhausted": "error"}, True),
])
def test_reads_in_a_loop(entry, reaches_e):
    """The same read() takes the next type at each iteration; then reads_exhausted, repeated."""
    t = _lv_trace([entry], program=READ_LOOP)
    nodes, _ = _on(t, t.frames[-1])
    assert nodes[0] == "L1" and ("E1" in nodes) == reaches_e


def test_reads_exhausted_error():
    with pytest.raises(ValueError) as e:
        _lv_trace([{"reads": ["fx", "fx"], "reads_exhausted": "error"}], program=READ_LOOP)
    assert "paths[0]: reads_exhausted: error: the path may execute read() more than 2 times" in str(e.value)


def test_path_input_and_reads_together():
    program = """function main(n)
M:  x = read()
    if fixnum?(n) goto A else goto B
A:  if fixnum?(x) goto C else goto B
C:  return x
B:  return n
"""
    t = _lv_trace([{"input": {"n": "fx"}, "reads": ["fl"]}], program=program)
    nodes, _ = _on(t, t.frames[-1])
    assert "A1" in nodes and "C1" not in nodes and any(n.startswith("B") for n in nodes)
    assert plain(t.frames[-1]["caption"]).startswith("path n: fx (read) → fl · ")


def test_path_narrows_values_computed_on_the_way():
    """The 0.28 rule read the parameters only; the walk runs the blocks again, so y = x * x is a flonum
    for a flonum x and the fixnum side of the test on y is left out (SBBV too)."""
    program = """function f(x)
A:  y = ##*(x, x)
    if fixnum?(y) goto C else goto D
C:  return y
D:  return 0
"""
    t = VersioningTrace(parse(program), algorithm="sbbv", limit=3, paths=[{"input": {"x": "fl"}}])
    assert plain(t.frames[-1]["caption"]) == "path x: fl · A1 → D1 · 1 test"


def test_sbbv_path_follows_an_opaque_call():
    program = """function f(x)
A:  call g(x) -> B
B:  if fixnum?(#res) goto C else goto D
C:  return 1
D:  return 2

function g(x)
G:  return x
"""
    t = VersioningTrace(parse(program), algorithm="sbbv", limit=3, paths=[{"input": {"x": "fx"}}])
    nodes, edges = _on(t, t.frames[-1])
    assert nodes == ["A1", "B1", "C1", "D1"] and edges["A1->B1"][0] == "return"
    assert "G1" in {v["label"] for v in t.tables["versions"].values()}  # g is drawn, off the path


FIB = """function main()
M:  n = read()
    call fib(n) -> N
N:  return #res

function fib(n)
A:  if fixnum?(n) goto B else goto Z
B:  if fx<(n, 2) goto R else goto C
R:  return n
C:  m = fx-(n, 1)
    call fib(m) -> D
D:  a = #res
    k = fx-(n, 2)
    call fib(k) -> E
E:  b = #res
    if fixnum?(a) goto F else goto G
F:  if fixnum?(b) goto H else goto G
H:  s = fx+?(a, b)
    if s goto S else goto G
S:  return s
G:  return ##+(a, b)
Z:  fail
"""


def test_path_through_recursion():
    """Calls and returns stay matched at any depth (summaries per activation): a fixnum reaches the base
    case and both recursive calls, a flonum stops at the type test; the walk is quick."""
    import time

    t0 = time.perf_counter()
    t = _lv_trace([{"reads": ["fx"]}, {"reads": ["fl"]}, {"reads": ["fx"], "overflow": "never"}], program=FIB, limit=2)
    assert time.perf_counter() - t0 < 2
    fx, fl, never = (_on(t, f) for f in t.frames[-3:])
    assert {"M1", "A1", "B1", "R1", "C1", "N1"} <= set(fx[0]) and "Z1" not in fx[0]
    assert set(fl[0]) == {"M1", "A1", "Z1"}
    assert set(never[0]) <= set(fx[0]) and not any(n.startswith("G") for n in never[0])


def test_versions_qualified_by_function():
    program = """function main()
A:  call f(1) -> B
B:  return #res

function f(x)
A:  return x
"""
    with pytest.raises(ValueError) as e:
        _lv_trace([{"versions": ["A1"]}], program=program)
    assert "several drawn functions have a version 'A1': write main/A1 or f/A1" in str(e.value)
    t = _lv_trace([{"versions": ["main/A1", "f/A1", "B1"]}], program=program)
    nodes, edges = _on(t, t.frames[-1])
    assert sorted(nodes) == ["A1", "A1", "B1"] and edges["A1->B1"] == ("return", "[0]", [0])
    assert plain(t.frames[-1]["caption"]).startswith("path chosen versions · A1 → A1 → B1")


def test_path_with_intervals_ends_on_a_loop():
    program = """function sum(n: fx [0, 100])
A:  goto L(i=0, s=0)
L(i, s):  if fx<(i, n) goto B else goto E
B:  i = fx+?(i, 1)
    if i goto C else goto E
C:  s = fx+(s, i)
    goto L
E:  return s
"""
    t = VersioningTrace(parse(program), algorithm="sbbv", limit=3, intervals=True,
                        paths=[{"input": {"n": "fx [0, 10]"}}])
    nodes, _ = _on(t, t.frames[-1])
    assert nodes[0] == "A1" and any(n.startswith("E") for n in nodes)


def test_lv_paths_in_a_deck_with_a_follower_and_an_arrow(deck):
    root = deck({"talk.md": """# A
```bbv-cfg {#src program="p.bbv" follow=run}
show: [label]
```
```bbv-anim {#run program="p.bbv" algorithm=lv heuristic=arithmetic limit=3 entry=main}
paths:
  - reads: [fl]
    caption: "(read) returns a flonum"
  - reads: [fx]
```
```arrow {#w}
steps: [null, run.X1, run.A1->B5]
```
```timeline
run ..end-2
run end-1, w 1
run end, w 2
```
""", "p.bbv": POLY_SQUARE})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    run = d.instances["a/run"]
    hl = d.instances["a/src"]["data"]["highlight"]
    assert len(hl) == run["positions"] and isinstance(hl[-2], list) and len(hl[-2]) == 10
    root.write_text(root.read_text().replace("reads: [fx]", "reads: [fx]\n    reads_exhausted: maybe"))
    items = check_deck(root, use_cache=False).items
    assert any(x.code == "LT022" and "paths[1]: reads_exhausted: cannot read the type 'maybe'" in x.message
               for x in items), items


# ------------------------------------------------------------ bands of ranks (spec 9.5)

VECTOR_PRINT = (Path(__file__).resolve().parent.parent / "user_manual" / "programs" / "vector-print.bbv").read_text(
    encoding="utf-8")
VP_RUN = dict(algorithm="sbbv", heuristic="arithmetic", limit=2, intervals=True, vector_bounds=False,
              thresholds=[0, 1, "maxfix-1", "maxfix"])
FIB_CALL = """\
function main()
M:  n = read()
    call fib(n) -> N
N:  return #res

function fib(n)
A:  if fixnum?(n) goto B else goto C
B:  if fx<=(n, 1) goto R else goto D
C:  if ##<=(n, 1) goto R else goto D
R:  return n
D:  if fixnum?(n) goto E else goto F
E:  n1 = fx-?(n, 1)
    if n1 goto H else goto I
F:  if flonum?(n) goto G else goto I
G:  n1 = fl-(n, 1.0)
    goto H
I:  n1 = ##-(n, 1)
    goto H
H:  call fib(n1) -> J
J:  a = #res
    if fixnum?(n) goto K else goto L
K:  n2 = fx-?(n, 2)
    if n2 goto P else goto Q
L:  if flonum?(n) goto O else goto Q
O:  n2 = fl-(n, 2.0)
    goto P
Q:  n2 = ##-(n, 2)
    goto P
P:  call fib(n2) -> S
S:  b = #res
    if fixnum?(a) goto T else goto V
T:  if fixnum?(b) goto U else goto V
U:  r = fx+?(a, b)
    if r goto W else goto Z
W:  return r
V:  if flonum?(a) goto X else goto Z
X:  if flonum?(b) goto Y else goto Z
Y:  return fl+(a, b)
Z:  return ##+(a, b)
"""
FIB_RUN = dict(algorithm="lv", heuristic="arithmetic", limit=3, entry="main")
SHOW = ["label", "context", "code"]


def _graphviz():
    from lattice.graphs import has_graphviz, layout

    if not has_graphviz():
        pytest.skip("Graphviz is needed for the ranks of the request's estimates")
    return lambda g: layout(g, engine="dot", rankdir="TB", edge_labels=False)


def _run(text, run):
    return VersioningTrace(parse(text), **run)


def _live(frame, pos):
    return {vid: p for vid, p in pos.items() if frame["nodes"].get(vid, {}).get("mark") != "gone"}


def _check_bands(t, box, positions, fn):
    """No two live versions overlap in any frame, and every version stays in its band, inside its extent."""
    sizes = box["sizes"]
    rw = box["rankWrap"][fn]
    tb = box["direction"] == "TB"
    seen = {}
    for f, pos in zip(t.frames, positions):
        live = sorted(_live(f, pos).items())
        for i, (a, pa) in enumerate(live):
            for b, pb in live[i + 1:]:
                assert not (pa[0] < pb[0] + sizes[b][0] and pb[0] < pa[0] + sizes[a][0]
                            and pa[1] < pb[1] + sizes[b][1] and pb[1] < pa[1] + sizes[a][1]), (a, b)
        for vid, p in live:
            v = t.tables["versions"][vid]
            if v["function"] != fn:
                continue
            k, _, start, end = rw["blocks"][v["name"]]
            band = rw["bands"][k]
            lo, hi = (p[0], p[0] + sizes[vid][0]) if tb else (p[1], p[1] + sizes[vid][1])
            assert band["start"] - 0.1 <= lo and hi <= band["end"] + 0.1
            q = p[1] if tb else p[0]
            assert start - 0.1 <= q <= end + 0.1
            seen.setdefault(vid, set()).add(k)
    assert all(len(ks) == 1 for ks in seen.values())


def test_cut_ranks_is_contiguous_and_balanced():
    from lattice.bbv.layout import GAP_RANK, band_length, cut_ranks

    exts = [40, 40, 200, 40, 40, 40, 40, 200]
    assert cut_ranks(exts, 1) == [0]
    assert cut_ranks(exts, 99) == list(range(8))  # clamped to the number of ranks
    starts = cut_ranks(exts, 2)
    assert starts[0] == 0 and len(starts) == 2
    a, b = band_length(exts[:starts[1]]), band_length(exts[starts[1]:])
    best = min(max(band_length(exts[:j]), band_length(exts[j:])) for j in range(1, 8))
    assert max(a, b) == best
    # among cuts of the same longest band, the most even one
    assert cut_ranks([10, 10, 10, 100], 2) == [0, 3] and band_length([10, 10, 10]) == 30 + 2 * GAP_RANK


def test_one_band_is_the_layout_without_bands():
    lf = _graphviz()
    t = _run(VECTOR_PRINT, VP_RUN)
    plain_box, plain_pos = layout_frames(t.tables, t.frames, SHOW, lf, "LR", 4)
    # the request's figure for 0.31 (2753.4 x 488), with 5 more for the second lane of the tail gutter (0.33.2) and
    # 10 more margin on each side (0.33.3)
    assert (plain_box["width"], plain_box["height"]) == (2773.4, 513.0)
    for kw in ({"rank_wrap": 1}, {"rank_wraps": {"vprint": 1}}, {"rank_wrap": 1, "rank_flow": "snake"}):
        box, pos = layout_frames(t.tables, t.frames, SHOW, lf, "LR", 4, **kw)
        assert box == plain_box and pos == plain_pos and "rankWrap" not in box


@pytest.mark.parametrize("flow", ["restart", "snake"])
def test_bands_of_the_two_test_cases(flow):
    """The acceptance of the request: within 10 % of its estimates, no overlap, every version in one band."""
    lf = _graphviz()
    a = _run(VECTOR_PRINT, VP_RUN)
    box, pos = layout_frames(a.tables, a.frames, SHOW, lf, "LR", 4, rank_wrap=2, rank_flow=flow)
    assert abs(box["width"] - 1412) / 1412 < 0.1 and abs(box["height"] - 888) / 888 < 0.1
    assert len(box["rankWrap"]["vprint"]["bands"]) == 2
    _check_bands(a, box, pos, "vprint")
    b = _run(FIB_CALL, FIB_RUN)
    box, pos = layout_frames(b.tables, b.frames, SHOW, lf, "TB", 4, rank_wraps={"fib": 2}, rank_flow=flow)
    assert abs(box["width"] - 2889) / 2889 < 0.1 and abs(box["height"] - 1438) / 1438 < 0.1
    assert "main" not in box["rankWrap"] and len(box["rankWrap"]["fib"]["bands"]) == 2
    _check_bands(b, box, pos, "fib")
    flips = [band["flip"] for band in box["rankWrap"]["fib"]["bands"]]
    assert flips == ([False, True] if flow == "snake" else [False, False])


def test_snake_bands_run_backwards():
    lf = _graphviz()
    t = _run(VECTOR_PRINT, VP_RUN)
    box, _ = layout_frames(t.tables, t.frames, SHOW, lf, "TB", 4, rank_wrap=3, rank_flow="snake")
    rw = box["rankWrap"]["vprint"]
    by_band: dict[int, list] = {}
    for k, rank, start, _end in sorted(rw["blocks"].values(), key=lambda x: x[1]):
        by_band.setdefault(k, []).append(start)
    assert by_band[0] == sorted(by_band[0]) and by_band[2] == sorted(by_band[2])
    assert by_band[1] == sorted(by_band[1], reverse=True)  # its first rank at the bottom
    assert [b["flip"] for b in rw["bands"]] == [False, True, False]


def test_gutters_widen_with_their_lanes():
    from lattice.bbv.layout import BAND_GAP, FUNCTION_GAP, GUTTER_LANES, gutter_gap

    assert gutter_gap(1) == gutter_gap(2) == BAND_GAP and gutter_gap(GUTTER_LANES) <= FUNCTION_GAP
    lf = _graphviz()
    t = _run(FIB_CALL, FIB_RUN)
    box, _ = layout_frames(t.tables, t.frames, SHOW, lf, "TB", 4, rank_wraps={"fib": 3})
    rw = box["rankWrap"]["fib"]
    for k, g in enumerate(rw["gutters"]):
        assert g["lanes"] >= 1  # loops do not count toward GUTTER_LANES
        gap = rw["bands"][k + 1]["start"] - rw["bands"][k]["end"]
        assert gap == pytest.approx(gutter_gap(g["lanes"]), abs=0.2)
        assert rw["bands"][k]["end"] < g["at"] < g["at"] + (g["lanes"] - 1) * g["step"] < rw["bands"][k + 1]["start"]


def test_loops_take_the_gutter_on_the_cheaper_side():
    """Spec 9.5: a loop travels in the gutter before or after its band, the shorter runs then the fewer edges
    crossed deciding, with a hysteresis; the head gutter takes room only when its loops save enough."""
    from lattice.bbv.layout import GUTTER_STEP, LANE

    lf = _graphviz()
    t = _run(FIB_CALL, {**FIB_RUN, "entry": "fib"})
    sides: list[dict] = []
    box, pos = layout_frames(t.tables, t.frames, SHOW, lf, "LR", 4, rank_wrap="auto", fit=(1136, 430),
                             call_edges=True, sides=sides)
    assert len(sides) == len(t.frames) and len(box["rankWrap"]["fib"]["bands"]) == 2
    label = {k: v["label"] for k, v in t.tables["versions"].items()}
    named = lambda key: (label[key.split("->")[0]], label[key.split("->")[1].split(":")[0]])
    done = sides[-1]
    # the recursive call at the top of its band goes over it; the two lower ones go under it
    assert [named(k) for k in done] == [("H1", "A2")]
    fib = box["bands"]["fib"]
    assert fib["head"] == {"at": fib["start"] - LANE, "lanes": 1, "step": GUTTER_STEP}
    assert box["headers"]["fib"]["y"] < fib["head"]["at"] - GUTTER_STEP  # the name stays above the head gutter
    # no flickering: a loop changes side at most twice over the run
    changes: dict[str, int] = {}
    for a, b in zip(sides, sides[1:]):
        for k in set(a) ^ set(b):
            changes[k] = changes.get(k, 0) + 1
    assert max(changes.values(), default=0) <= 2, changes
    # vector-print without bands: two loops would go over their band for 3 frames each, not worth the room
    vp_sides: list[dict] = []
    v = _run(VECTOR_PRINT, VP_RUN)
    box, _ = layout_frames(v.tables, v.frames, SHOW, lf, "LR", 4, sides=vp_sides)
    assert "head" not in box["bands"]["vprint"] and not any(vp_sides)
    assert box["bands"]["vprint"]["tail"]["lanes"] == 2  # its loops into two targets: a lane each


def test_auto_takes_the_shape_of_the_box():
    from lattice.bbv.layout import AUTO_CAP, AUTO_TIE

    lf = _graphviz()
    a = _run(VECTOR_PRINT, VP_RUN)
    for d in ("LR", "TB"):  # the request's best rows
        box, _ = layout_frames(a.tables, a.frames, SHOW, lf, d, 4, rank_wrap="auto", fit=(1136, 480))
        assert len(box["rankWrap"]["vprint"]["bands"]) == 2
    b = _run(FIB_CALL, FIB_RUN)
    box, _ = layout_frames(b.tables, b.frames, SHOW, lf, "TB", 4, rank_wrap="auto", fit=(1136, 430))
    # the fewest bands whose scale is within AUTO_TIE of the largest (2 and 3 bands are close here: 3 drew 2.0 %
    # larger in 0.33.2, 2.9 % with the wider margin of 0.33.3)
    scales = {}
    for n in range(1, 5):
        w, h = (lambda bx: (bx["width"], bx["height"]))(layout_frames(b.tables, b.frames, SHOW, lf, "TB", 4, rank_wraps={"fib": n})[0])
        scales[n] = min(1136 / w, 430 / h, AUTO_CAP)
    best = max(scales.values())
    assert len(box["rankWrap"]["fib"]["bands"]) == min(n for n, sc in scales.items() if sc >= best * (1 - AUTO_TIE))
    assert "main" not in box["rankWrap"]
    box, _ = layout_frames(b.tables, b.frames, ["label", "context"], lf, "TB", 4, rank_wrap="auto", fit=(1136, 430))
    assert len(box["rankWrap"]["fib"]["bands"]) == 3
    tall, _ = layout_frames(a.tables, a.frames, SHOW, lf, "TB", 4, rank_wrap="auto", fit=(400, 1200))
    assert "rankWrap" not in tall  # a tall box keeps one column


BANDS_DECK = """# Bands {#b}
```bbv-anim {#run program="vp.bbv" algorithm=sbbv heuristic=arithmetic limit=2 intervals=true vector_bounds=false direction=LR rank_wrap=2}
thresholds: [0, 1, maxfix-1, maxfix]
```
```bbv-cfg {#src program="vp.bbv" follow=run direction=LR rank_wrap=2}
```
"""


def test_band_options_in_a_deck_and_a_follower_takes_the_cut(deck):
    root = deck({"talk.md": BANDS_DECK, "vp.bbv": VECTOR_PRINT})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    run, src = d.instances["b/run"]["data"]["box"], d.instances["b/src"]["data"]["box"]
    assert run["rankWrap"]["vprint"]["cut"] == src["rankWrap"]["vprint"]["cut"]
    # the same blocks in the same bands
    assert {k: v[0] for k, v in run["rankWrap"]["vprint"]["blocks"].items()} == \
        {k: v[0] for k, v in src["rankWrap"]["vprint"]["blocks"].items()}
    # a follower with another count cuts on its own extents
    other = deck({"talk.md": BANDS_DECK.replace("follow=run direction=LR rank_wrap=2", "follow=run direction=LR rank_wrap=3"),
                  "vp.bbv": VECTOR_PRINT})
    own = build_deck(other, use_cache=False).instances["b/src"]["data"]["box"]["rankWrap"]["vprint"]["cut"]
    assert len(own) == 3 and own[0] == 0


def test_band_options_errors_and_warnings(deck):
    def items(attrs, body="", program=VECTOR_PRINT, comp="bbv-anim"):
        root = deck({"talk.md": f"# A\n```{comp} {{program=\"p.bbv\" {attrs}}}\n{body}```\n", "p.bbv": program})
        return check_deck(root, use_cache=False).items

    for bad in ("rank_wrap=0", "rank_wrap=x", "rank_wrap=1.5", "rank_wrap=-2"):
        found = items(bad)
        assert any(x.code == "LT022" and "rank_wrap: expected an integer >= 1 or auto" in x.message for x in found), bad
    found = items("", "rank_wraps: {nope: 2}\n")
    assert any(x.code == "LT022" and "rank_wraps: 'nope' is not a function of the program" in x.message for x in found)
    found = items("", "rank_wraps: {vprint: none}\n")
    assert any(x.code == "LT022" and "rank_wraps: vprint: expected" in x.message for x in found)
    found = items('fit_aspect="wide" rank_wrap=auto')
    assert any(x.code == "LT022" and "fit_aspect: expected two positive numbers" in x.message for x in found)
    found = items("rank_wrap=auto", "fit_aspect: 16:9\n")  # YAML reads 16:9 as a number
    assert any(x.code == "LT022" and "quote it" in x.message for x in found)
    assert any(x.code == "LT021" for x in items("rank_flow=zigzag"))
    found = items("rank_wrap=40")
    assert any(x.code == "LT046" and "rank_wrap=40" in x.message and "clamped" in x.message for x in found)
    assert not [x for x in items("rank_wrap=4")]  # within the ranks: no warning
    found = items("", "rank_wraps: {vprint: 30}\n")
    assert any(x.code == "LT046" and "rank_wraps: vprint" in x.message for x in found)
    found = items('fit_aspect="4:3"')
    assert any(x.code == "LT046" and "fit_aspect has no effect" in x.message for x in found)
    # a global count larger than a small function only: no warning
    assert not [x for x in items("rank_wrap=3 algorithm=lv entry=main", program=FIB_CALL)]
    # the same options on the other two drawings
    assert not [x for x in items("rank_wrap=2 rank_flow=snake", comp="bbv-cfg")]
    assert not [x for x in items("rank_wrap=auto", comp="abstract-interp-anim")]


def test_auto_follows_the_deck_aspect_and_the_panel(deck):
    """The target box of `auto`: the slide's content width (by the deck's aspect) less a panel beside the drawing,
    by `height`; or `fit_aspect`."""

    def bands(front, attrs, body="", cache=False):
        root = deck({"talk.md": f"{front}# A\n```bbv-anim {{#r program=\"p.bbv\" algorithm=sbbv heuristic=arithmetic "
                                f"limit=2 intervals=true vector_bounds=false {attrs}}}\n"
                                f"thresholds: [0, 1, maxfix-1, maxfix]\n{body}```\n",
                     "p.bbv": VECTOR_PRINT})
        d = build_deck(root, use_cache=cache)
        box = d.instances["a/r"]["data"]["box"]
        return len(box.get("rankWrap", {}).get("vprint", {}).get("bands", [0]))

    _graphviz()
    assert bands("", "direction=TB rank_wrap=auto height=480") == 2
    assert bands("", 'direction=TB rank_wrap=auto height=480 fit_aspect="1:3"') == 1
    assert bands("", 'direction=LR rank_wrap=auto height=900') == 2  # 1136 px wide: 2 and 3 bands tie, 2 wins
    assert bands('---\naspect: "4:3"\n---\n', 'direction=LR rank_wrap=auto height=900') == 3  # 880 px wide
    assert bands("", 'direction=LR rank_wrap=auto height=900', "panel: [queue]\n") == 3  # the panel takes 278 px
    assert bands("", 'direction=LR rank_wrap=auto height=900 panel_at=below', "panel: [queue]\n") == 2
    # the aspect is part of the cache key
    assert bands("", 'direction=LR rank_wrap=auto height=900', cache=True) == 2
    assert bands('---\naspect: "4:3"\n---\n', 'direction=LR rank_wrap=auto height=900', cache=True) == 3


# ------------------------------------------------------------ merge heuristics: bbv-merge (spec 9.5)

TWO_VARS = [{"x": "fx", "y": "fx"}, {"x": "fl", "y": "fx"}, {"x": "fx", "y": "fl"}, {"x": "fl", "y": "fl"},
            {"x": "fx | fl", "y": "any"}, {"x": "pair", "y": "nil"}]


def _merge_run(contexts=TWO_VARS, **kw):
    from lattice.bbv.merging import MergeRun

    return MergeRun(contexts, **kw)


def _overlaps(frame, size):
    w, h = size
    pts = list(frame["pos"].values())
    return [(a, b) for i, a in enumerate(pts) for b in pts[i + 1:] if abs(a[0] - b[0]) < w and abs(a[1] - b[1]) < h]


@pytest.mark.parametrize("heuristic", ["similarity", "arithmetic"])
def test_merge_run_picks_the_closest_pair_until_the_limit_holds(heuristic):
    from lattice.bbv.heuristics import DISTANCES

    run = _merge_run(heuristic=heuristic, limit=2)
    events = [m["event"] for m in run.meta]
    n = len(run.merges)
    assert events == ["start"] + ["pick", "merge", "settle"] * (n - 1) + ["pick", "merge", "done"]
    assert len(run.frames) == 3 * n + 1
    by = run.spec.by_id
    for i, f in enumerate(run.frames):
        if run.meta[i]["event"] != "pick":
            continue
        live = [int(v) for v in f["nodes"]]
        pair = [int(v) for v, st in f["nodes"].items() if st.get("mark") == "merge"]
        d = DISTANCES[heuristic]
        best = min(d(by[a].context, by[b].context) for j, a in enumerate(live) for b in live[j + 1:])
        assert d(by[pair[0]].context, by[pair[1]].context) == best
        states = [e.get("state") for e in f["edges"].values()]
        assert states.count("merge") == 1 and states.count("dim") == len(states) - 1
        assert len(states) == len(live) * (len(live) - 1) // 2  # the complete graph
    live = [v for v, st in run.frames[-1]["nodes"].items()]
    assert len(live) <= 2 and [st.get("mark") for st in run.frames[-1]["nodes"].values()].count("merged") == 1
    assert "done" in plain(run.frames[-1]["caption"])


def test_merge_run_is_the_merge_of_sbbv():
    """The merges are those of Specializer.merge_some: the run below matches the hand computation of
    the arithmetic distance, including a union that is a context merged away earlier."""
    run = _merge_run(TWO_VARS[:5], heuristic="arithmetic", limit=2)
    captions = [plain(f["caption"]) for f in run.frames]
    assert captions[1].startswith("closest pair C2 C3 · distance 64")
    assert captions[2].startswith("merge C2 C3 → C6 · new context, the union of theirs · x: fx | fl · y: fx | fl")
    assert captions[3].startswith("limit 4 contexts for a limit of 2 · C6 in place of C2 and C3")
    assert captions[5].startswith("merge C6 → C5 · its context is their union")
    assert captions[6].endswith("C6 absorbed into C5")
    assert captions[8].startswith("merge C1 C4 → C5 · their union is C6, merged into C5 earlier")
    assert captions[9].endswith("C1 and C4 absorbed into C5")
    merge = run.frames[2]["nodes"]
    assert merge["6"] == {"state": "done", "mark": "merged", "arrive": True}
    assert merge["2"]["mark"] == merge["3"]["mark"] == "absorbed"
    assert all(merge[v]["mark"] == "dim" for v in ("1", "4", "5"))
    # the merge frame draws only the edges between the contexts left alone, dimmed
    assert sorted(run.frames[2]["edges"]) == ["1--4", "1--5", "4--5"]
    assert all(e["state"] == "dim" for e in run.frames[2]["edges"].values())
    settle = run.frames[3]
    assert all(e.get("state") == "new" for k, e in settle["edges"].items() if "6" in k.split("--"))
    assert not any(st.get("mark") for v, st in settle["nodes"].items() if v != "6")
    assert run.meta[1]["algo"] == [53, 54] and run.meta[2]["algo"] == [55, 56, 57] and run.meta[3]["algo"] == [5]


def test_merge_edge_widths_are_the_clamped_log_of_the_distance():
    import math

    run = _merge_run(heuristic="arithmetic")
    edges = [(run.dist[k], e["w"]) for f in run.frames for k, e in f["edges"].items()]
    assert all(1.0 <= w <= 7.0 for _, w in edges)
    near = min(d for d, _ in edges)
    far = max(d for d, _ in edges)
    assert dict(edges)[near] == 7.0 and dict(edges)[far] == 1.0  # thick = close
    for (d1, w1) in edges:
        for (d2, w2) in edges:
            if d1 < d2:
                assert w1 >= w2
    lo = math.log10(1 + near)
    clamped = _merge_run(heuristic="arithmetic", log_range=(lo, lo + 0.5), edge_width=(2.0, 4.0))
    widths = {e["w"] for f in clamped.frames for e in f["edges"].values()}
    assert min(widths) == 2.0 and max(widths) == 4.0
    assert sum(1 for f in clamped.frames for e in f["edges"].values() if e["w"] == 2.0) > len(widths)


@pytest.mark.parametrize("placement", ["circle", "distance"])
@pytest.mark.parametrize("heuristic", ["similarity", "arithmetic"])
def test_merge_placements_never_overlap(placement, heuristic):
    run = _merge_run(heuristic=heuristic, placement=placement, limit=1)
    for i, f in enumerate(run.frames):
        if run.meta[i]["event"] == "merge":  # the pair meets: those left alone stay apart
            live = {v: p for v, p in f["pos"].items() if f["nodes"][v].get("mark") == "dim"}
            assert not _overlaps({"pos": live}, run.size)
        else:
            assert not _overlaps(f, run.size), (i, f["pos"])
        for p in f["pos"].values():
            assert 0 <= p[0] and p[0] + run.size[0] <= run.box["width"] + 0.1
            assert 0 <= p[1] and p[1] + run.size[1] <= run.box["height"] + 0.1
    if placement == "distance":  # one place per context for the whole run, but where a pair meets
        places = {}
        for i, f in enumerate(run.frames):
            for v, p in f["pos"].items():
                if run.meta[i]["event"] != "merge" or f["nodes"][v].get("mark") == "dim":
                    assert places.setdefault(v, p) == p


@pytest.mark.parametrize("placement", ["circle", "distance"])
def test_merge_frames_meet_then_settle(placement):
    """The pair meets on the context that remains, or halfway when the result is new; the others stay; the
    settle frame is the layout of the contexts left."""
    run = _merge_run(heuristic="arithmetic", placement=placement)
    for i, m in enumerate(run.meta):
        if m["event"] != "merge":
            continue
        pick, merge, settle = run.frames[i - 1], run.frames[i], run.frames[i + 1]
        into = next(v for v, st in merge["nodes"].items() if st.get("mark") == "merged")
        pair = [v for v, st in pick["nodes"].items() if st.get("mark") == "merge"]
        if into in pick["pos"]:
            meet = pick["pos"][into]
        else:
            meet = [round((pick["pos"][pair[0]][k] + pick["pos"][pair[1]][k]) / 2, 1) for k in (0, 1)]
        assert all(merge["pos"][v] == meet for v in pair + [into]), (i, merge["pos"])
        for v, st in merge["nodes"].items():
            if st.get("mark") == "dim":
                assert merge["pos"][v] == pick["pos"][v]
        assert set(settle["nodes"]) == {v for v, st in merge["nodes"].items() if st.get("mark") != "absorbed"}
    if placement == "circle":  # back to even spacing: a new result moves from where its pair met
        into = str(run.merges[0]["into"])
        assert run.frames[3]["pos"][into] != run.frames[2]["pos"][into]


def test_merge_random_draws_no_distance():
    run = _merge_run(heuristic="random", seed=7)
    assert all(not f["edges"] for f in run.frames)
    assert "distance" not in run.frames[1]["panel"]
    assert plain(run.frames[1]["caption"]).startswith("random pair")
    again = _merge_run(heuristic="random", seed=7)
    assert [f["caption"] for f in again.frames] == [f["caption"] for f in run.frames]


def test_merge_code_is_the_block_specialized_per_context():
    run = _merge_run([{"p": "proc", "lst": "pair"}, {"p": "proc", "lst": "nil"}, {"p": "any", "lst": "pair"}],
                     program=program("find.bbv"), block="A", limit=1, show=["label", "context", "code"])
    versions = run.tables()["versions"]
    assert [v["label"] for v in versions.values()][:3] == ["A1", "A2", "A3"]
    first = versions["1"]["code"]
    assert first[0]["removed"] and first[1]["text"] == "goto B"
    merged = [v for vid, v in versions.items() if int(vid) > 3]
    assert merged and not merged[0]["code"][0].get("removed")  # nil | pair: the test stays
    assert run.meta[0]["block"] == "find/A"


MERGE_DECK = """
# M {#m}

```bbv-merge {#h limit=2 heuristic=arithmetic%s}
contexts:
  - {x: fx, y: fx}
  - {x: fl, y: fx}
  - {x: fx, y: fl}
  - context: {x: fl, y: fl}
    label: Q
%s
```
%s
"""


def _merge_deck(deck, attrs="", body="", after="", files=None):
    return deck({"talk.md": MERGE_DECK % (attrs, body, after), **(files or {})})


def test_bbv_merge_component_builds(deck):
    root = _merge_deck(deck, " colors=context", "panel: [contexts, limit, merges, distance]",
                       "```code {#algo lang=text file=\"lattice:bbv/pseudocode/sbbv.txt\" follow=h meta=algo}\n```\n")
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    inst = d.instances["m/h"]
    data = inst["data"]
    assert data["kind"] == "merge" and inst["positions"] == data["frames"]["count"] == 3 * 2 + 1
    sizes = {tuple(s) for s in data["box"]["sizes"].values()}
    assert len(sizes) == 1  # every node has the same shape
    labels = [v["label"] for v in data["tables"]["versions"].values()]
    assert labels[:4] == ["C1", "C2", "C3", "Q"]
    colors = data["colors"]
    assert len(colors) == len(labels)  # a colour per context, merged ones mixed from their pair
    assert "bbv-merge" in d.component_names


@pytest.mark.parametrize("attrs, body, message", [
    ("", "contexts: null", "contexts: list the contexts"),
    (' heuristic=random edges=all', "", "edges: the random heuristic has no distance to draw"),
    (' heuristic=random distance_magnitude=true', "", "distance_magnitude: the random heuristic has no distance"),
    (' heuristic=random', "panel: [distance]", "random has no distance"),
    (' heuristic=random placement=distance', "", "placement=distance needs a heuristic with a distance"),
    (' edge_width="[3, 1]"', "", "edge_width: expected two increasing numbers"),
    (' log_range=wide', "", "log_range: expected two increasing numbers"),
    ("", "show: [label, code]", "show: code needs a program"),
    (' block=A', "", "block names a block of program or source"),
    (' name="9x"', "", "name: '9x' is not a block name"),
    (' fit_aspect=wide', "", "fit_aspect: expected two positive numbers W:H"),
])
def test_bbv_merge_option_errors(deck, attrs, body, message):
    contexts = "" if body.startswith("contexts:") else "contexts: [{x: fx}, {x: fl}, {x: bg}]\n"
    text = f"# M {{#m}}\n\n```bbv-merge {{#h{attrs}}}\n{contexts}{body}\n```\n"
    items = check_deck(deck({"talk.md": text}), use_cache=False).items
    assert any(message in x.message for x in items), items


@pytest.mark.parametrize("contexts, message", [
    ("[{x: fx}]", "a list of at least two contexts"),
    ("[{x: fx}, {x: fx}]", "contexts[1] is the same context as contexts[0]"),
    ("[{x: fx}, {x: blob}]", "contexts[1]: x: cannot read the type 'blob'"),
    ("[{x: fx}, 3]", "contexts[1]: a context is a mapping"),
    ("[{x: fx}, {x: fl}, {context: {x: bg}, label: C1}]", "label C1 names two contexts"),
])
def test_bbv_merge_context_errors(deck, contexts, message):
    root = deck({"talk.md": f"# M\n\n```bbv-merge {{#h}}\ncontexts: {contexts}\n```\n"})
    items = check_deck(root, use_cache=False).items
    assert any(message in x.message for x in items), items


def test_bbv_merge_with_a_program(deck):
    find = (PROGRAMS / "find.bbv").read_text(encoding="utf-8")
    ok = '# M\n\n```bbv-merge {#h program="find.bbv" block=A limit=1}\ncontexts: [{p: proc, lst: pair}, {p: any, lst: nil}]\n```\n'
    d = build_deck(deck({"talk.md": ok, "find.bbv": find}), use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    assert d.instances["m/h"]["data"]["show"] == ["label", "context", "code"]
    for body, message in [("block=Z", "block: no block 'Z'"), ("block=A name=K", "name labels the contexts"),
                          ("", "block: name the block")]:
        bad = ok.replace("block=A", body).replace("{p: proc, lst: pair}", "{p: proc, q: pair}")
        items = check_deck(deck({"talk.md": bad, "find.bbv": find}), use_cache=False).items
        assert any(message in x.message for x in items), (body, items)
    bad = ok.replace("{p: proc, lst: pair}", "{p: proc, q: pair}")
    items = check_deck(deck({"talk.md": bad, "find.bbv": find}), use_cache=False).items
    assert any("q is not a parameter of block find/A" in x.message for x in items), items


def test_bbv_merge_within_the_limit_warns(deck):
    root = deck({"talk.md": "# M\n\n```bbv-merge {#h limit=3}\ncontexts: [{x: fx}, {x: fl}]\n```\n"})
    d = build_deck(root, use_cache=False)
    assert d.instances["m/h"]["positions"] == 2
    assert [x.code for x in d.diagnostics.items] == ["LT046"]
    assert "nothing to merge" in d.diagnostics.items[0].message


def test_arrow_at_contexts_and_edges_of_a_merge(deck):
    timeline = "```timeline\nh 1..end, w 1..end\n```\n"
    root = _merge_deck(deck, after="```arrow {#w}\nsteps: [h.C1--C2, h.Q, h.C1, null, null, null, null]\n```\n" + timeline)
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items, d.diagnostics.items
    steps = d.instances["m/w"]["data"]["steps"]
    assert steps[2]["to_part"] == '.lt-bbv-node[data-vid="1"]:not(.lt-gone):not(.mk-absorbed)'
    assert steps[0]["to_part"] == '.lt-bbv-dist[data-key="1--2"]:not(.lt-gone) > .lt-bbv-edge-mark'
    for ref, message in [("h.C9", "no context 'C9'"), ("h.C1--C9", "no context 'C9'")]:
        bad = _merge_deck(deck, after=f"```arrow {{#w}}\nsteps: [{ref}]\n```\n")
        items = check_deck(bad, use_cache=False).items
        assert any(x.code == "LT063" and message in x.message for x in items), items


def test_an_absorbed_context_is_not_a_part_to_point_at(deck):
    from lattice.components.base import RenderResult
    from lattice.components.bbv import BbvMerge

    d = build_deck(_merge_deck(deck), use_cache=False)
    inst = d.instances["m/h"]
    result = RenderResult("", inst["data"], inst["positions"])
    frame = inst["data"]["frames"]["frames"][2]
    absorbed = [v for v, st in frame["nodes"].items() if st.get("mark") == "absorbed"]
    label = inst["data"]["tables"]["versions"][absorbed[0]]["label"]
    part = BbvMerge().part(result, label)
    assert part.drawn[1] and not part.drawn[2]  # picked, then absorbed


def test_distance_magnitude_changes_only_what_is_shown():
    import math

    raw = _merge_run(heuristic="similarity")
    mag = _merge_run(heuristic="similarity", magnitude=True)
    assert [f["pos"] for f in raw.frames] == [f["pos"] for f in mag.frames]  # same merges, same layout
    for fr, fm in zip(raw.frames, mag.frames):
        assert {k: e["w"] for k, e in fr["edges"].items()} == {k: e["w"] for k, e in fm["edges"].items()}
        for k, e in fm["edges"].items():
            assert e["d"] == f"{math.log10(raw.dist[k]):.2f}"
    a, b = (int(v) for v, st in mag.frames[1]["nodes"].items() if st.get("mark") == "merge")
    shown = f"{math.log10(raw._d(a, b)):.2f}"
    assert f"log₁₀ distance {shown}" in plain(mag.frames[1]["caption"])
    assert mag.frames[1]["panel"]["distance"] == shown
    from lattice.bbv.merging import magnitude
    assert magnitude(0) == "-∞" and magnitude(1000) == "3.00"


# ------------------------------------------------------------ constant folding (ΛV, spec 9.5)

INCR = """function main()
M:  call incr(0) -> N
N:  return #res

function incr(x)
A:  if fixnum?(x) goto B else goto C
B:  r = fx+?(x, 1)
    if r goto R else goto D
R:  return r
C:  if flonum?(x) goto F else goto D
F:  return fl+(x, 1.0)
D:  return ##+(x, 1)
"""


def fold_trace(source: str = INCR, **kw):
    opts = dict(algorithm="lv", limit=3, heuristic="arithmetic", entry="main", intervals=True, fold=True)
    opts.update(kw)
    return VersioningTrace(parse(source), **opts)


def labels_of(t: VersioningTrace, frame: dict) -> set[str]:
    return {t.tables["versions"][vid]["label"] for vid, n in frame["nodes"].items() if n.get("mark") != "gone"}


def test_fold_replaces_a_call_by_its_constant_result():
    """incr(0) returns exactly 1 and incr has no side effect: once A1, B1 and R1 are specialized, three
    frames (the region, the call site and its return point, the fold) replace the call by `#res = 1`,
    and the versions only that call reached become unreachable; the generic entry is still queued."""
    t = fold_trace()
    events = [m["event"] for m in t.meta]
    i = events.index("fold-pure")
    assert events[i:i + 3] == ["fold-pure", "fold-site", "fold"]
    assert events.index("exit") < i < events.index("generic-entries")
    pure, site, fold = t.frames[i:i + 3]
    marked = lambda f, mark: {t.tables["versions"][v]["label"] for v, n in f["nodes"].items() if n.get("mark") == mark}
    assert marked(pure, "path") == {"A1", "B1", "R1"}
    assert marked(site, "path") == {"M1", "N1"}
    assert marked(fold, "gone") == {"A1", "B1", "R1"} and marked(fold, "new") == {"M1"}
    assert "the call is replaced by" in plain(fold["caption"]) and "#res = 1" in plain(fold["caption"])
    assert "receives #res: fx {1} only" in plain(site["caption"])
    assert labels_of(t, t.frames[-1]) == {"M1", "N1", "A2", "B2", "C1", "R2", "D1", "F1", "D2"}
    m1 = next(vid for vid, v in t.tables["versions"].items() if v["label"] == "M1")
    v = t.tables["versions"][m1]
    assert [c["text"] for c in v["code"]] == ["#res = 1", "goto N"]
    assert [c["text"] for c in v["alt"]] == ["call incr[A1](0) -> N"]
    assert all(f["nodes"][m1].get("alt") for f in t.frames[1:i + 2] if m1 in f["nodes"])
    assert not any(f["nodes"][m1].get("alt") for f in t.frames[i + 2:])
    assert t.spec.folds == 1


def test_no_fold_without_the_option_or_with_side_effects_or_without_a_constant():
    assert "fold" not in [m["event"] for m in fold_trace(fold=False).meta]
    effect = INCR.replace("R:  return r", "R:  t = display(r)\n    return r")
    assert "fold" not in [m["event"] for m in fold_trace(effect).meta]
    assert "fold" not in [m["event"] for m in fold_trace(intervals=False).meta]  # fx, not fx {1}
    unknown = INCR.replace("call incr(0) -> N", "call incr(y) -> N").replace("M:  ", "M:  y = read()\n    ", 1)
    assert "fold" not in [m["event"] for m in fold_trace(unknown).meta]  # any input: several results
    one = """function main()
M:  y = read()
    call one(y) -> N
N:  return #res

function one(y)
A:  %s
    return 1
"""
    assert "fold" in [m["event"] for m in fold_trace(one % "t = ##car(y)").meta]  # ##car never raises
    assert "fold" not in [m["event"] for m in fold_trace(one % "t = car(y)").meta]  # car of any may raise


def test_fold_of_a_boolean_and_errors():
    source = """function main()
M:  call positive(3) -> N
N:  return #res

function positive(x)
A:  if fx>(x, 0) goto B else goto C
B:  return #t
C:  return #f
"""
    t = fold_trace(source)
    m1 = next(vid for vid, v in t.tables["versions"].items() if v["label"] == "M1")
    assert [c["text"] for c in t.tables["versions"][m1]["code"]] == ["#res = #t", "goto N"]
    with pytest.raises(ValueError, match="needs algorithm=lv"):
        VersioningTrace(parse(INCR), algorithm="sbbv", fold=True)


def test_a_path_goes_through_a_folded_call():
    t = fold_trace(paths=[{"input": {}}])
    path = t.frames[-1]
    on = {t.tables["versions"][v]["label"] for v, n in path["nodes"].items() if n.get("mark") == "path"}
    assert on == {"M1", "N1"}
    assert any(k.endswith(":goto") and e.get("state") == "path" for k, e in path["edges"].items())


def test_fold_in_a_deck_sizes_the_box_for_both_codes(tmp_path):
    """The box of a folded call site has room for its code before and after the fold (the drawing
    never rescales), and an enlarged block is sized the same way."""
    from lattice.bbv.layout import node_size

    (tmp_path / "incr.bbv").write_text(INCR)
    src = tmp_path / "talk.md"
    src.write_text("""# A {#a}

```bbv-anim {#run program="incr.bbv" algorithm=lv limit=3 entry=main intervals=true fold=true}
show: [label, code]
```
""")
    data = build_deck(src, use_cache=False).instances["a/run"]["data"]
    versions = data["tables"]["versions"]
    m1 = next(vid for vid, v in versions.items() if v["label"] == "M1")
    v = versions[m1]
    before = node_size({**v, "code": v["alt"], "alt": None}, ["label", "code"])
    after = node_size({**v, "alt": None}, ["label", "code"])
    assert tuple(data["box"]["sizes"][m1]) == node_size(v, ["label", "code"])
    assert data["box"]["sizes"][m1][0] == max(before[0], after[0]) and data["box"]["sizes"][m1][1] == max(before[1], after[1])
    assert data["zoom"]["sizes"][m1][0] >= max(before[0], after[0])
