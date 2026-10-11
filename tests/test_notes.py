"""Speaker notes (spec 3.14): the sidecar file, its build, the server that edits it and the presenter's editor."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from lattice import notes
from lattice.build import build_deck
from lattice.emit import deck_json
from lattice.server import NOTES_PATH, DeckState, make_handler

DECK = """
---
title: Notes
---

# One

Body of one.

::: notes
Static *one*.
:::

# Two

Body of two.

# Three

Body of three.
"""

SIDECAR = """\
Free text before the first heading is kept.

# three

Third, see [[one]].

```python
# not-a-heading
x = 1
```

# ghost

Orphan notes.

# one

Sidecar $x^2$.
"""


def codes(diags, severity=None):
    return [d.code for d in diags.items if severity is None or d.severity == severity]


# ------------------------------------------------------------------------------------------- the file
def test_parse_sections_skip_fences_and_keep_the_rest():
    sc = notes.parse(SIDECAR)
    assert sc.preamble == "Free text before the first heading is kept.\n\n"
    assert [s.id for s in sc.sections] == ["three", "ghost", "one"]
    assert "# not-a-heading" in sc.sections[0].text  # a `# word` line in a fence is code
    assert sc.sections[0].text.startswith("Third") and sc.sections[0].text.endswith("```")
    assert sc.sections[0].line == 3 and sc.sections[0].text_line == 5
    assert sc.dump() == SIDECAR
    assert notes.parse("").sections == [] and notes.parse("no headings\n").preamble == "no headings\n"
    # a heading is `# ID` alone: titles with spaces or other levels are text
    assert [s.id for s in notes.parse("# a b\n## c\n# d-1_x  \ntext\n").sections] == ["d-1_x"]


def test_set_rewrites_one_section_only():
    sc = notes.parse(SIDECAR)
    sc.set("three", "Replaced.\n\n", ["one", "two", "three"])
    out = sc.dump()
    assert out == SIDECAR.replace(SIDECAR[SIDECAR.index("Third"):SIDECAR.index("# ghost")], "Replaced.\n\n")
    # a new section goes before the first section of a later slide, else at the end
    sc.set("two", "Second.", ["one", "two", "three"])
    assert [s.id for s in sc.sections] == ["two", "three", "ghost", "one"]
    sc.set("four", "Fourth.", ["one", "two", "three", "four"])
    assert [s.id for s in sc.sections][-1] == "four"
    assert sc.dump().endswith("Sidecar $x^2$.\n\n# four\n\nFourth.\n")
    assert "kept.\n\n# two\n\nSecond.\n\n# three" in sc.dump()
    # empty notes remove the section
    sc.set("ghost", "", [])
    assert "ghost" not in sc.dump() and "Orphan" not in sc.dump()
    assert notes.parse(sc.dump()).dump() == sc.dump()


def test_set_merges_an_id_given_twice_and_starts_a_new_file():
    sc = notes.parse("# a\n\nfirst\n\n# b\n\nbee\n\n# a\n\nsecond\n")
    assert sc.text_of("a") == "first\n\nsecond"
    sc.set("a", "both", ["a", "b"])
    assert sc.dump() == "# a\n\nboth\n\n# b\n\nbee\n"
    fresh = notes.Sidecar()
    fresh.set("x", "hello", ["x"])
    assert fresh.dump() == "# x\n\nhello\n"


def test_save_is_atomic_and_removes_an_empty_file(tmp_path):
    path = tmp_path / "talk.notes.md"
    sc = notes.Sidecar()
    sc.set("x", "hello", ["x"])
    notes.save(path, sc)
    assert path.read_text() == "# x\n\nhello\n"
    assert [p.name for p in tmp_path.iterdir()] == ["talk.notes.md"]  # no temporary file left
    sc.set("x", "", ["x"])
    notes.save(path, sc)
    assert not path.exists()
    assert notes.load(path).sections == []
    assert notes.sidecar_path(tmp_path / "talk.md") == path


# ------------------------------------------------------------------------------------------- the build
def test_build_appends_sidecar_notes_after_static_ones(deck):
    root = deck({"talk.md": DECK, "talk.notes.md": SIDECAR})
    d = build_deck(root, use_cache=False)
    one = d.slides["one"].notes_html
    assert one.index("Static <em>one</em>") < one.index("Sidecar")
    assert 'class="lt-math"' in one and d.uses_math
    three = d.slides["three"].notes_html
    assert '<a class="lt-link" href="#/one/0" data-lt-link="one">One</a>' in three  # titles substituted
    assert 'class="lt-c lt-c-code"' in three and "\x00" not in three
    assert ("three", "one", "link") in [(e.source, e.target, e.kind) for e in d.edges]
    assert d.slides["two"].notes_html is None
    assert codes(d.diagnostics) == ["LT067"]  # the orphan, kept in the file
    assert "ghost" in d.diagnostics.items[0].message and str(d.diagnostics.items[0].loc) == "talk.notes.md:12:1"
    j = deck_json(d)
    assert "serve" not in j and "Sidecar" in j["slides"]["one"]["notes"]
    assert d.instances == {}
    # serve builds without them
    bare = build_deck(root, use_cache=False, sidecar=False)
    assert "Sidecar" not in bare.slides["one"].notes_html and bare.slides["three"].notes_html is None
    assert not bare.diagnostics.items


def test_sidecar_problems(deck):
    side = """\
    # one

    ::: callout
    In a container.
    :::

    ```graph-anim
    a -> b
    ```

    # one

    Again.

    # two

    [[nowhere]]
    """
    root = deck({"talk.md": DECK, "talk.notes.md": side})
    with pytest.raises(Exception) as e:
        build_deck(root, use_cache=False)
    diags = e.value.diagnostics
    assert codes(diags, "error") == ["LT011"]
    assert sorted(codes(diags, "warning")) == ["LT067", "LT068", "LT068"]
    msgs = {d.code + ":" + str(d.loc.line): d.message for d in diags.items}
    assert "container 'callout'" in msgs["LT068:3"] and "component 'graph-anim'" in msgs["LT068:7"]
    assert "given twice" in msgs["LT067:11"] and "nowhere" in msgs["LT011:15"]


def test_code_in_static_notes(deck):
    """A code block in static notes is drawn in the notes (it used to leave a placeholder); a component there
    is shown as code with LT068."""
    root = deck({"talk.md": """
        # One

        ::: notes
        ```python {highlight=1}
        x = 1
        ```

        ```graph-anim
        a -> b
        ```
        :::
        """})
    d = build_deck(root, use_cache=False)
    html = d.slides["one"].notes_html
    assert "\x00" not in html and html.count('class="lt-c lt-c-code"') == 2 and "lt-hl" in html
    assert d.instances == {} and codes(d.diagnostics) == ["LT068"]


# ------------------------------------------------------------------------------------------- the server
@pytest.fixture
def server(deck):
    root = deck({"talk.md": DECK, "talk.notes.md": SIDECAR})
    state = DeckState(root.resolve(), False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def post(base, body, headers=None):
    req = urllib.request.Request(base + NOTES_PATH, data=json.dumps(body).encode(), method="POST",
                                 headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_server_serves_the_deck_without_sidecar_notes(server):
    state, base = server
    page = urllib.request.urlopen(base + "/").read().decode()
    deck_tag = page[page.index('id="lt-deck">') + 13:]
    j = json.loads(deck_tag[:deck_tag.index("</script>")])
    assert j["serve"] == {"notes": NOTES_PATH}
    assert "Sidecar" not in j["slides"]["one"]["notes"] and "notes" not in j["slides"]["three"]
    assert "katex" in page  # math typed in the editor renders
    got = json.load(urllib.request.urlopen(base + NOTES_PATH))
    assert set(got["slides"]) == {"one", "three"}  # not the orphan
    assert got["slides"]["one"]["md"] == "Sidecar $x^2$."
    assert '<a class="lt-link" href="#/one/0" data-lt-link="one">One</a>' in got["slides"]["three"]["html"]


def test_server_saves_one_section_without_rebuilding(server):
    state, base = server
    version, notes_version = state.version, state.notes_version
    status, got = post(base, {"slide": "two", "md": "New *two* [[nope]]"})
    assert status == 200 and got["html"] == '<p>New <em>two</em> <a class="lt-link" href="#/nope/0" data-lt-link="nope">nope</a></p>\n'
    assert got["problems"] == ["link to unknown id 'nope'"]
    text = state.sidecar.read_text()
    assert text == SIDECAR.replace("# three", "# two\n\nNew *two* [[nope]]\n\n# three")
    assert not state.changed() and state.version == version  # no rebuild, no reload
    assert state.notes_version == notes_version + 1  # the pages refetch
    state.check_sidecar()
    assert state.notes_version == notes_version + 1  # its own write is not an outside edit
    # an outside edit (an editor) is noticed, and never triggers a rebuild
    time.sleep(0.02)
    state.sidecar.write_text(text.replace("Orphan notes.", "Still an orphan."))
    state.check_sidecar()
    assert state.notes_version == notes_version + 2 and not state.changed()
    assert post(base, {"slide": "two", "md": ""})[1]["html"] == ""
    assert "# two" not in state.sidecar.read_text() and "Still an orphan." in state.sidecar.read_text()


def test_server_refuses_bad_requests(server):
    state, base = server
    before = state.sidecar.read_text()
    assert post(base, {"slide": "nope", "md": "x"})[0] == 404
    assert post(base, {"slide": "one"})[0] == 400
    assert post(base, {"slide": "one", "md": "x"}, {"Content-Type": "text/plain"})[0] == 415
    assert post(base, {"slide": "one", "md": "x"},
                {"Content-Type": "application/json", "Origin": "http://evil.example"})[0] == 403
    assert state.sidecar.read_text() == before


# ------------------------------------------------------------------------------------------- the editor
def test_presenter_edits_the_sidecar_notes(server):
    """Spec 3.14 and 7.5: the presenter edits the sidecar notes in place; the audience window never reloads."""
    pw = pytest.importorskip("playwright.sync_api")
    state, base = server
    stop = threading.Event()

    def watch():  # what `serve`'s watcher does for the sidecar
        while not stop.wait(0.1):
            state.check_sidecar()

    threading.Thread(target=watch, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1600, "height": 900})
            errors = []
            audience = ctx.new_page()
            audience.on("pageerror", lambda e: errors.append(str(e)))
            audience.goto(base + "/#/one/0")
            audience.evaluate("window.__stay = 1")
            pres = ctx.new_page()
            pres.on("pageerror", lambda e: errors.append(str(e)))
            pres.goto(base + "/?presenter#/one/0")
            pres.wait_for_function("document.querySelector('.lt-pp-notes-side').textContent.includes('Sidecar')")
            # static and sidecar notes look alike: one block of notes, math rendered in both
            assert pres.inner_text(".lt-pp-notes-static").startswith("Static one")
            assert pres.locator(".lt-pp-notes-side .katex").count() == 1
            pres.click(".lt-pp-notes-edit")
            box = pres.locator(".lt-pp-notes-input")
            assert box.is_visible() and box.input_value() == "Sidecar $x^2$."
            assert pres.is_visible(".lt-pp-notes-static")  # static notes stay, not editable
            box.press("End")
            pres.keyboard.type(" More [[two]]")
            pres.keyboard.press("ArrowRight")  # typing never moves the deck
            assert pres.evaluate("Lattice.state().cur") == {"slide": "one", "step": 0}
            pres.wait_for_function("document.querySelector('.lt-pp-notes-status').textContent === 'saved'")
            assert "# one\n\nSidecar $x^2$. More [[two]]\n" in state.sidecar.read_text()
            pres.keyboard.press("Escape")
            assert box.is_hidden() and "More Two" in pres.inner_text(".lt-pp-notes-side")
            # a slide without notes: double-click to write the first ones
            pres.keyboard.press("ArrowRight")
            assert "No notes for this slide" in pres.inner_text(".lt-pp-notes")
            pres.dblclick(".lt-pp-notes")
            pres.keyboard.type("Fresh notes")
            # the slide changes while editing (from the audience window): the text is saved, the editor follows
            audience.keyboard.press("ArrowRight")
            pres.wait_for_function("Lattice.state().cur.slide === 'three'")
            assert box.input_value() == "Third, see [[one]].\n\n```python\n# not-a-heading\nx = 1\n```"
            pres.wait_for_function("document.querySelector('.lt-pp-notes-status').textContent === 'saved'")
            text = state.sidecar.read_text()
            assert text.index("# one") > text.index("# two\n\nFresh notes\n") > 0  # in deck order, before three
            box.blur()
            # an edit made in an editor reaches the open presenter view
            time.sleep(0.02)
            state.sidecar.write_text(state.sidecar.read_text().replace("Third, see", "Edited outside, see"))
            pres.wait_for_function("document.querySelector('.lt-pp-notes-side').textContent.includes('Edited outside')",
                                   timeout=5000)
            assert audience.evaluate("window.__stay") == 1  # never reloaded
            assert not audience.is_visible(".lt-pp-notes-edit")
            assert errors == []
            browser.close()
    except pw.Error as e:
        if "Executable doesn't exist" in str(e):
            pytest.skip("Chromium for Playwright is not installed")
        raise
    finally:
        stop.set()
