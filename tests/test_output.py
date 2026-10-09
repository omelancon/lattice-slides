import json
import re

import pytest

from lattice.build import build_deck
from lattice.emit import emit_dir, emit_html
from lattice.graphs import has_graphviz

CSV = "n,algo,ms\n10,a,1\n10,b,2\n100,a,3\n100,b,9\n"


def deck_json(html):
    return json.loads(re.search(r'id="lt-deck">(.*?)</script>', html, re.S).group(1))


def data_of(html, instance):
    return json.loads(re.search(rf'id="lt-data-{re.escape(instance)}">(.*?)</script>', html, re.S).group(1))


def test_diff_steps(deck):
    root = deck({"talk.md": """
        # A
        ```diff-steps {#d lang=python}
        versions:
          - {code: "x = 1\\ny = 2"}
          - {code: "x = 1\\ny = 3\\nz = 4", label: second}
        ```
    """})
    s = build_deck(root, use_cache=False).slides["a"]
    assert s.steps == 2
    assert "lt-diff-add" in s.body_html and "lt-diff-del" in s.body_html
    assert "+2 -1" in s.body_html


def test_plain_diff_fence_is_still_highlighted(deck):
    root = deck({"talk.md": "# A\n```diff\n-a\n+b\n```\n"})
    s = build_deck(root, use_cache=False).slides["a"]
    assert 'data-lang="diff"' in s.body_html


def test_vega_shorthand_and_libraries(deck):
    root = deck({"talk.md": """
        # A
        ```plot {backend=vega data="d.csv" x=n y=ms group=algo logy=true}
        ```
    """, "d.csv": CSV})
    d = build_deck(root, use_cache=False)
    page = emit_html(d)
    spec = data_of(page, "a/c1")["spec"]
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["color"]["field"] == "algo"
    assert spec["encoding"]["y"]["scale"] == {"type": "log"}
    assert len(spec["data"]["values"]) == 4
    assert "vegaLite" in page and "Plotly" not in page[:200000]


def test_plotly_bars_are_categorical(deck):
    root = deck({"talk.md": """
        # A
        ```plot {backend=plotly data="d.csv" x=n y=ms group=algo kind=bar}
        ```
    """, "d.csv": CSV})
    d = build_deck(root, use_cache=False)
    fig = data_of(emit_html(d), "a/c1")["spec"]
    assert [t["name"] for t in fig["data"]] == ["a", "b"]
    assert fig["layout"]["xaxis"]["type"] == "category"
    assert d.requires == {"plotly"}


PLOT_SOURCE = '''
def chart(series=None, scale=1):
    names = series or ["a", "b"]
    return {"mark": "line", "data": {"values": [{"s": s, "v": scale} for s in names]}}

def fixed():
    return {"mark": "line"}

def keyed(legend, scale=1):
    return {"mark": "line", "description": f"legend {legend}"}

def titled(title="Own title"):
    return {"mark": "line", "title": title}

def drawn(ax, color="red"):
    ax.plot([1, 2], [3, 4], color=color)

def figure(dpi=50):
    import matplotlib.pyplot as plt
    return plt.figure(dpi=dpi)
'''


def test_plot_passes_extra_options_to_its_source(deck):
    """Spec 8.2: a plot with a source passes the options it does not know to the function, read as YAML."""
    pytest.importorskip("matplotlib")
    root = deck({"talk.md": """
        # A
        ```plot {#p backend=vega source="charts.py:chart" series="[b]" scale=2}
        ```

        ```plot {#q backend=vega source="charts.py:chart"}
        series: [a, c]
        ```

        ```plot {#r source="charts.py:drawn" color=blue}
        ```

        ```plot {#s source="charts.py:figure" dpi=40}
        ```

        ```plot {#t backend=vega source="charts.py:keyed" legend=false}
        ```

        ```plot {#u backend=vega source="charts.py:keyed" scale=3}
        ```
    """, "charts.py": PLOT_SOURCE})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    assert d.instances["a/p"]["data"]["spec"]["data"]["values"] == [{"s": "b", "v": 2}]
    assert [v["s"] for v in d.instances["a/q"]["data"]["spec"]["data"]["values"]] == ["a", "c"]
    assert "#0000ff" in d.slides["a"].body_html
    # `legend` is the plot's own option: a source with that parameter receives it, true by default
    assert d.instances["a/t"]["data"]["spec"]["description"] == "legend False"
    assert d.instances["a/u"]["data"]["spec"]["description"] == "legend True"


def test_plot_passes_its_title_to_a_source_that_takes_it(deck):
    """Spec 8.2: `title` set on the block goes to a source with a `title` parameter, which otherwise keeps
    its own default; a source without one gets the title from the plot, as before."""
    root = deck({"talk.md": """
        # A
        ```plot {#t backend=vega source="charts.py:titled" title="micro benchmarks"}
        ```

        ```plot {#u backend=vega source="charts.py:titled"}
        ```

        ```plot {#v backend=vega source="charts.py:fixed" title="Set by the plot"}
        ```
    """, "charts.py": PLOT_SOURCE})
    d = build_deck(root, use_cache=False)
    assert not d.diagnostics.items
    assert d.instances["a/t"]["data"]["spec"]["title"] == "micro benchmarks"
    assert d.instances["a/u"]["data"]["spec"]["title"] == "Own title"
    assert d.instances["a/v"]["data"]["spec"]["title"] == "Set by the plot"


@pytest.mark.parametrize("block, code", [
    ('```plot {backend=vega source="charts.py:fixed" series="[a]"}', "LT022"),  # the function takes no such option
    ('```plot {source="charts.py:drawn" ax=1}', "LT022"),  # ax is the plot's to pass
    ('```plot {backend=vega source="charts.py:fixed" legend=true}', "LT022"),  # legend set, not taken
    ('```plot {source="charts.py:drawn"}\nlegend: false', "LT022"),  # the same, in the body
    ('```plot {backend=vega data="d.csv" x=n y=ms colour=red}', "LT021"),  # no source: unknown option
])
def test_plot_rejects_options_its_source_does_not_take(deck, block, code):
    from lattice.build import check_deck

    root = deck({"talk.md": f"# A\n{block}\n```\n", "charts.py": PLOT_SOURCE, "d.csv": CSV})
    assert code in {x.code for x in check_deck(root, use_cache=False).items}


def test_matplotlib_plots_rebuild_byte_identical(deck):
    """Report section 2, goal 6: the ids matplotlib gives clip paths do not change from one build to the next."""
    pytest.importorskip("matplotlib")
    root = deck({"talk.md": """
        # A
        ```plot {data="d.csv" x=n y=ms group=algo}
        ```

        ```plot {data="d.csv" x=n y=ms group=algo}
        ```
    """, "d.csv": CSV})
    first = build_deck(root, use_cache=False).slides["a"].body_html
    second = build_deck(root, use_cache=False).slides["a"].body_html
    assert "clip-path=\"url(#" in first
    assert first == second
    ids = re.findall(r'<clipPath id="([^"]+)"', first)
    assert len(ids) == len(set(ids))  # two plots of one slide keep distinct ids


def test_component_samples_in_markdown_are_not_lexed_as_another_language(deck):
    """Spec 3.13: in a Markdown sample, an `arrow` fence is the component (a YAML body), not Pygments' Arrow
    language, whose error tokens painted the sample red; other fences are highlighted as before."""
    sample = "```arrow {to=x}\nsteps:\n  - a[1]\n  - {to: b, angle: 90}\n```\n\n```dot\ndigraph { a -> b }\n```\n"
    root = deck({"talk.md": "# A\n\n````markdown\n" + sample + "````\n"})
    html_ = build_deck(root, use_cache=False).slides["a"].body_html
    assert 'class="err"' not in html_
    assert "steps:" in html_ and "angle: 90" in html_
    assert '<span class="k">digraph</span>' in html_  # dot is not a YAML component: Graphviz still highlights it


def test_no_libraries_when_unused(deck):
    root = deck({"talk.md": "# A\nplain\n"})
    page = emit_html(build_deck(root, use_cache=False))
    assert "vegaLite" not in page and "KaTeX_Main" not in page and "Plotly" not in page


def test_images_are_embedded(deck):
    root = deck({"talk.md": "# A\n![x](img/p.svg)\n", "img/p.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>"})
    page = emit_html(build_deck(root, use_cache=False))
    assert 'src="data:image/svg+xml;base64,' in page


def test_missing_image_warns(deck):
    root = deck({"talk.md": "# A\n![x](nope.png)\n"})
    d = build_deck(root, use_cache=False)
    emit_html(d)
    assert "LT051" in {x.code for x in d.diagnostics.items}


def test_directory_output(deck, tmp_path):
    root = deck({"talk.md": """
        # A
        ![x](p.svg)
        ```diff-steps {#d}
        versions: [{code: a}, {code: b}]
        ```
    """, "p.svg": "<svg xmlns='http://www.w3.org/2000/svg'/>"})
    out = tmp_path / "out"
    index = emit_dir(build_deck(root, use_cache=False), out)
    html = index.read_text()
    dj = deck_json(html)
    assert dj["instances"]["a/d"]["url"] == "data/a_d.json"
    assert (out / "data" / "a_d.json").is_file()
    assert (out / "assets" / "lattice.js").is_file()
    assert re.search(r'src="assets/media/[0-9a-f]{10}-p\.svg"', html)


@pytest.mark.skipif(not has_graphviz(), reason="Graphviz not installed")
def test_overview_map(deck):
    root = deck({"talk.md": """
        # A
        ::: detour
        # D
        :::
        # B
    """})
    ov = deck_json(emit_html(build_deck(root, use_cache=False)))["overview"]
    assert set(ov["nodes"]) == {"a", "d", "b"}
    assert {(e["from"], e["to"], e["kind"]) for e in ov["edges"]} == {("a", "b", "next"), ("a", "d", "detour")}


def test_missing_component_file_is_lt045(deck):
    from lattice.build import check_deck

    root = deck({"talk.md": '# A\n```code {lang=python file="nope.py"}\n```\n'})
    assert "LT045" in {d.code for d in check_deck(root, use_cache=False).items}


def test_unknown_theme_warns(deck):
    root = deck({"talk.md": "---\ntheme: neon\n---\n# A\n"})
    d = build_deck(root, use_cache=False)
    assert "LT052" in {x.code for x in d.diagnostics.items}
    assert "--lt-bg:#f7f8fa" in emit_html(d)  # falls back to the default theme


ARROW_DECK = """
# A

{#why}
A paragraph to point at.

```arrow {to=why label="here"}
```

```arrow {#walk from=why curve=0.2}
steps:
  - .lt-title
  - to: why
    from: ""
    angle: 90
```

```arrow {to=nowhere}
```
"""


def test_arrow_component(deck):
    """Spec 8.9: targets, the 315 degree default, steps as positions, and LT046 for an unknown id."""
    root = deck({"talk.md": ARROW_DECK})
    d = build_deck(root, use_cache=False)
    s = d.slides["a"]
    assert [w.code for w in d.diagnostics.items] == ["LT046"] and "nowhere" in d.diagnostics.items[0].message
    one = d.instances["a/c1"]["data"]
    assert one["steps"] == [{"to": "why", "from": None, "angle": 315.0, "length": 120.0, "label": "here"}]
    walk = d.instances["a/walk"]["data"]
    assert [t["to"] for t in walk["steps"]] == [".lt-title", "why"]
    assert walk["steps"][0]["from"] == "why" and walk["steps"][0]["angle"] is None
    assert walk["steps"][1]["from"] is None and walk["steps"][1]["angle"] == 90.0
    assert walk["curve"] == 0.2
    assert s.steps == 2 and [t.id for t in s.tracks] == ["walk"]
    html = emit_html(d)
    assert 'data-component="arrow"' in html and 'Lattice.component("arrow"' in html


def test_arrow_needs_a_target(deck):
    from lattice.build import check_deck

    root = deck({"talk.md": "# A\n```arrow\n```\n"})
    assert "LT022" in {x.code for x in check_deck(root, use_cache=False).items}


def test_arrow_null_steps(deck):
    """Spec 8.9: a null step is a position without an arrow; steps that are all null are LT022."""
    from lattice.build import check_deck

    src = ("# A\n{#why}\nA paragraph.\n\n```arrow {#w}\nsteps:\n  - null\n"
           "  - {to: why, label: here}\n  - null\n```\n")
    d = build_deck(deck({"talk.md": src}), use_cache=False)
    assert not d.diagnostics.items
    steps = d.instances["a/w"]["data"]["steps"]
    assert steps[0] is None and steps[2] is None and steps[1]["to"] == "why" and steps[1]["angle"] == 315.0
    assert d.slides["a"].steps == 3
    root = deck({"talk.md": "# A\n```arrow\nsteps: [null, null]\n```\n"})
    assert "LT022" in {x.code for x in check_deck(root, use_cache=False).items}


def test_scheme_binding_sites_are_variables():
    """Pygments paints every symbol after "(" as a call; the Scheme filter restores the binding sites (spec 3.13)."""
    from pygments.token import Name

    from lattice.components.scheme import lexer_for

    src = ("(define (sum-to-n n) (let loop ((i 0) (sum 0)) (if (>= i n) sum (loop (+ i 1) (+ sum i)))))\n"
           "(lambda (x . rest) (let-values (((a b) (g x))) (do ((k 0 (+ k 1))) ((= k 3)) (case-lambda ((z) z)))))")
    types = {}
    for ttype, value in lexer_for("scheme").get_tokens(src):
        if value.strip() and value not in "()":
            types.setdefault(value, set()).add(ttype)
    assert types["i"] == {Name.Variable} and types["sum"] == {Name.Variable} and types["n"] == {Name.Variable}
    assert types["loop"] == {Name.Function} and types["sum-to-n"] == {Name.Function}
    assert types["x"] == types["rest"] == types["a"] == types["b"] == types["k"] == types["z"] == {Name.Variable}
    assert types["g"] == {Name.Function} and types["+"] == {Name.Builtin}
    assert lexer_for("no-such-language").name == "Text only" and lexer_for("python").name == "Python"


def test_columns_that_change_width_in_the_output(deck):
    """Spec 10.4 and 11.2: columns named by a width cue (or collapsed by their attribute) are marked and
    wrapped; every other column renders as before 0.24."""
    root = deck({"talk.md": """
        # A
        ::: columns {gap=24px duration=450}
        ::: column {#l}
        left
        :::
        ::: column {#r width=2fr .wide}
        right
        :::
        :::
        ::: columns
        ::: column {width=1fr}
        untouched
        :::
        ::: column
        also
        :::
        :::
        ```timeline
        width l=0
        width l=300px r=1fr
        ```

        # B
        ::: columns
        ::: column {width=3fr}
        x
        :::
        ::: column {#z width=0}
        y
        :::
        :::
    """})
    html = emit_html(build_deck(root, use_cache=False))
    assert "\x00" not in html
    assert ('<div class="lt-columns" style="gap:24px;--lt-gap:24px" data-lt-cols="" data-lt-duration="450">'
            '<div class="lt-column" id="l" data-lt-col="l" data-lt-flex=""><div class="lt-column-in">') in html
    assert ('<div class="lt-column wide" id="r" style="flex:2 1 0" data-lt-col="r" data-lt-flex="2 1 0">'
            '<div class="lt-column-in">') in html
    # a `columns` none of whose columns change is exactly as before
    assert ('<div class="lt-columns"><div class="lt-column" style="flex:1 1 0"><p>untouched</p>\n</div>'
            '<div class="lt-column"><p>also</p>\n</div></div>') in html
    # a column collapsed from step 0 is marked even without a width cue: hidden, inert, its gap given back
    assert ('<div class="lt-column lt-col-shut" id="z" style="flex:0 0 0px" data-lt-col="z" data-lt-flex="0 0 0px" '
            'inert><div class="lt-column-in">') in html
    a, b = deck_json(html)["slides"]["a"], deck_json(html)["slides"]["b"]
    assert a["tracks"] == [{"id": "@columns", "kind": "columns"}]
    assert a["positions"] == [[0], [1], [2]]
    assert a["columns"] == [{"l": "1 1 0", "r": "2 1 0"}, {"l": "0 0 0px", "r": "2 1 0"},
                            {"l": "0 0 300px", "r": "1 1 0"}]
    assert "columns" not in b and b["tracks"] == []


def test_panel_at_marks_the_animation_root(deck):
    """Spec 8.8: `panel_at` (`auto`, `right`, `below`) is a class on the root of the animation components;
    `auto`, the default, adds nothing, so decks render as before."""
    root = deck({"talk.md": """
        # A
        ```graph-anim {#g source="t.py:walk" panel_at=below}
        edges: ["A B"]
        ```
        ```array-anim {#a source="t.py:arr" panel_at=right}
        values: [2, 1]
        ```
        ```abstract-interp-anim {#ai panel_at=below}
        source: |
          function f(n)
          A:  return n
        ```
        ```bbv-anim {#bb panel_at=right}
        source: |
          function f(n)
          A:  return n
        ```
        ```array-anim {#d source="t.py:arr"}
        values: [2, 1]
        ```
        ```timeline
        g end, a end
        ```
    """, "t.py": """
        from lattice import ArrayTrace, GraphTrace

        def walk(g):
            t = GraphTrace(g)
            for n in sorted(g):
                t.frame(nodes={n: "active"})
            return t

        def arr(values):
            t = ArrayTrace(values)
            t.frame(caption="start")
            t.frame(marks={0: "compare"})
            return t
    """})
    body = build_deck(root, use_cache=False).slides["a"].body_html
    assert '<div class="lt-graph-anim lt-panel-below"></div>' in body
    assert '<div class="lt-array-anim lt-panel-right"></div>' in body
    assert '<div class="lt-bbv-anim lt-bbv-absint lt-panel-below"></div>' in body
    assert '<div class="lt-bbv-anim lt-panel-right"></div>' in body
    assert '<div class="lt-array-anim"></div>' in body  # auto


def test_panel_at_rejects_other_values(deck):
    from lattice.build import check_deck

    root = deck({"talk.md": "# A\n```bbv-anim {panel_at=left}\nsource: |\n  function f(n)\n  A:  return n\n```\n"})
    assert "LT021" in {d.code for d in check_deck(root, use_cache=False).items}
