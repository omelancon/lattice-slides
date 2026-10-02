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
    # every redundant pair? test disappeared, the entry test and procedure? in B1 remain
    assert spec.tests_remaining() == 3 and spec.merges == 0
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
    """bbv.js steps 22 px out of a node before joining the lane: the box must leave that room."""
    from lattice.bbv import layout

    assert layout.MARGIN >= 24 and layout.LANE + 10 >= 0


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
    assert ai.contexts["C"] is None and ("A", "C") in ai.dead and str(ai.contexts["B"].get("x")) == "fx [1, 9]"
    # on find, abstract interpretation keeps p: any at the loop entry: the procedure? test stays
    ai = AbstractInterpreter(program("find.bbv"))
    ai.run()
    assert str(ai.contexts["A"].get("p")) == "any" and str(ai.contexts["D"].get("p")) == "proc"


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
