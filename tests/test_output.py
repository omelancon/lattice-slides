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
