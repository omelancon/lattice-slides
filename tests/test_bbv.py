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
