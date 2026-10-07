"""Component rendering, caching and step compilation (spec sections 6 and 8)."""
from __future__ import annotations

import html
import json
import re
import traceback
from pathlib import Path

import yaml
from pydantic import ValidationError

from . import __version__
from .components.base import REGISTRY, ComponentError, MissingFileError, RenderContext, RenderResult, cache_key, file_hash
from .diagnostics import Diagnostics
from .model import ComponentBlock, Deck, Slide, Track
from .themes import get_theme
from .timeline import COLUMNS_TRACK, compile_steps


def _library_hash() -> str:
    """Hash of Lattice's own Python sources, so upgrading the library invalidates the cache."""
    import hashlib

    h = hashlib.sha256()
    for f in sorted(Path(__file__).parent.rglob("*.py")):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


LIB_HASH = _library_hash()


class Cache:
    def __init__(self, directory: Path, enabled: bool):
        self.dir = directory
        self.enabled = enabled

    def get(self, key: str) -> tuple[RenderResult, set[Path], list] | None:
        if not self.enabled:
            return None
        f = self.dir / f"{key}.json"
        if not f.is_file():
            return None
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            for p, h in entry["deps"].items():
                if not Path(p).is_file() or file_hash(Path(p)) != h:
                    return None
            r = entry["result"]
            result = RenderResult(r["html"], r["data"], r["positions"], r["meta"], requires=r.get("requires", []),
                                  anchors=r.get("anchors", []))
            return result, {Path(p) for p in entry["deps"]}, entry.get("warnings", [])
        except (OSError, ValueError, KeyError):
            return None

    def put(self, key: str, result: RenderResult, deps: set[Path], warnings: list | None = None) -> None:
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            entry = {"deps": {str(p): file_hash(p) for p in deps if p.is_file()},
                     "result": {"html": result.html, "data": result.data, "positions": result.positions,
                                "meta": result.meta, "requires": result.requires, "anchors": result.anchors},
                     "warnings": list(warnings or [])}
            (self.dir / f"{key}.json").write_text(json.dumps(entry), encoding="utf-8")
        except (OSError, TypeError, ValueError):
            pass


def build_options(comp_cls, block: ComponentBlock, diags: Diagnostics):
    values: dict = dict(block.attrs.kv)
    if comp_cls.body == "yaml":
        try:
            data = yaml.safe_load(block.body) if block.body.strip() else {}
        except yaml.YAMLError as e:
            diags.error("LT021", f"invalid YAML body: {e}", block.loc)
            return None
        if data is None:
            data = {}
        if not isinstance(data, dict):
            diags.error("LT021", "the block body must be a YAML mapping", block.loc)
            return None
        both = set(data) & set(values)
        if both:
            diags.error("LT036", f"option(s) given both as attribute and in the body: {', '.join(sorted(both))}",
                        block.loc)
            return None
        values.update(data)
    elif comp_cls.body == "none" and block.body.strip():
        diags.error("LT021", f"component {comp_cls.name!r} takes no body", block.loc)
        return None
    try:
        return comp_cls.Options(**values)
    except ValidationError as e:
        for err in e.errors():
            where = ".".join(str(p) for p in err["loc"]) or "options"
            diags.error("LT021", f"{comp_cls.name}: {where}: {err['msg']}", block.loc)
        return None


def render_slide_components(deck: Deck, slide: Slide, cache: Cache, palette: dict) -> None:
    diags = deck.diagnostics
    blocks = slide.components
    by_id = {b.id: b for b in blocks if b.id}
    for b in blocks:
        if b.id is None:
            b.id = f"c{b.index}"

    # leaders before followers (8.5)
    order: list[ComponentBlock] = []
    state: dict[int, int] = {}

    def visit(b: ComponentBlock, chain: list[str]) -> bool:
        if state.get(b.index) == 2:
            return True
        if state.get(b.index) == 1:
            diags.error("LT028", f"follow cycle: {' -> '.join(chain + [b.id])}", b.loc)
            return False
        state[b.index] = 1
        if b.follow is not None:
            leader = by_id.get(b.follow)
            if leader is None:
                diags.error("LT028", f"follow target {b.follow!r} is not a component id on this slide", b.loc)
                state[b.index] = 2
                return False
            if not visit(leader, chain + [b.id]):
                return False
        state[b.index] = 2
        order.append(b)
        return True

    for b in blocks:
        visit(b, [])

    results: dict[int, RenderResult] = {}
    keys: dict[int, str] = {}
    for b in order:
        comp_cls = REGISTRY[b.name]
        opts = build_options(comp_cls, b, diags)
        if opts is None:
            continue
        leader = by_id.get(b.follow) if b.follow else None
        if leader is not None and leader.index not in results:
            continue  # leader failed
        instance = f"{slide.id}/{b.id}"
        key = cache_key([__version__, LIB_HASH, b.name, comp_cls.version, comp_cls.__module__,
                         opts.model_dump(mode="json"), b.body, str(b.file_dir),
                         keys.get(leader.index) if leader else None, palette])
        hit = cache.get(key)
        if hit is not None:
            result, deps, warnings = hit
            for code, message in warnings:  # warnings of the render that produced the entry (8.6)
                diags.warn(code, message, b.loc)
        else:
            ctx = RenderContext(meta=deck.meta, slide_id=slide.id, instance_id=instance, root_dir=deck.root.parent,
                                file_dir=b.file_dir, palette=palette,
                                leader=results.get(leader.index) if leader else None, loc=b.loc, diags=diags,
                                frames_config=deck.meta.build.frames)
            try:
                result = comp_cls().render(b, opts, ctx)
            except MissingFileError as e:
                diags.error("LT045", f"{b.name}: {e}", b.loc)
                continue
            except ComponentError as e:
                diags.error("LT022", f"{b.name}: {e}", b.loc)
                continue
            except Exception as e:  # noqa: BLE001
                tb = traceback.format_exc(limit=-3)
                diags.error("LT022", f"{b.name} failed: {type(e).__name__}: {e}\n{tb}", b.loc)
                continue
            deps = ctx.dependencies
            if not _valid_result(result, b, diags):
                continue
            cache.put(key, result, deps, ctx.warnings)
        deck.dependencies.update(deps)
        results[b.index] = result
        keys[b.index] = key
        if leader is not None and result.positions != results[leader.index].positions:
            diags.error("LT027", f"follower {b.id!r} has {result.positions} positions, leader {leader.id!r} has "
                        f"{results[leader.index].positions}", b.loc)
        if result.positions > 1 and comp_cls.runtime is None:
            diags.error("LT047", f"{b.name} has several positions but no runtime", b.loc)

    parts = _resolve_parts(slide, blocks, results, diags)
    _check_ids(slide, blocks, results, diags)

    # substitute placeholders, register instances
    body = slide.body_html
    for b in blocks:
        r = results.get(b.index)
        inner = r.html if r else f'<div class="lt-error">{html.escape(b.name)}: render failed</div>'
        instance = f"{slide.id}/{b.id}"
        attrs = dict(b.wrapper_attrs)
        cls = " ".join(filter(None, ["lt-c", f"lt-c-{b.name}", attrs.pop("class", None)]))
        extra = "".join(f' {k}="{html.escape(str(v), quote=True)}"' for k, v in attrs.items())
        wrapper = (f'<div class="{cls}" data-component="{html.escape(b.name)}" '
                   f'data-instance="{html.escape(instance)}"{extra}>{inner}</div>')
        body = body.replace(b.placeholder, wrapper)
        if r is not None:
            deck.component_names.add(b.name)
            deck.instances[instance] = {"component": b.name, "slide": slide.id, "data": r.data,
                                        "positions": r.positions}
            deck.requires.update(REGISTRY[b.name].requires)
            deck.requires.update(r.requires)
    slide.body_html = body
    _check_arrow_targets(slide, blocks, results, diags)

    # tracks (6.1): reveal first, then components in document order
    rendered = [b for b in blocks if b.index in results]
    track_ids = {b.id for b in rendered if not b.follow and results[b.index].positions > 1}
    changed = True
    while changed:  # followers (possibly chained) whose leader is a track
        changed = False
        for b in rendered:
            if b.follow and b.id not in track_ids and b.follow in track_ids:
                track_ids.add(b.id)
                changed = True
    tracks: list[Track] = []
    if slide.reveal_count:
        tracks.append(Track("reveal", "reveal", slide.reveal_count + 1))
    for b in rendered:
        if b.id in track_ids:
            tracks.append(Track(b.id, "component", results[b.index].positions, f"{slide.id}/{b.id}", b.follow))
    if slide.column_init:  # `width` cues (spec 3.15): the columns track, whose positions compile_steps counts
        tracks.append(Track(COLUMNS_TRACK, "columns", 1))
    independent = [t for t in tracks if t.follow is None and t.positions > 1 and t.kind == "component"]
    if len(independent) + (1 if slide.reveal_count else 0) >= 2 or slide.timeline is not None:
        for t in independent:
            blk = next(x for x in rendered if x.id == t.id)
            if blk.attrs.id is None:
                diags.error("LT033", f"component {blk.name!r} needs an #id to be used in a timeline", blk.loc)
    slide.tracks = tracks
    compile_steps(slide, diags)
    _check_part_positions(slide, parts, diags)


def _check_ids(slide: Slide, blocks, results, diags: Diagnostics) -> None:
    """LT058: an id given twice on a slide. Author ids are those of the slide's own HTML (attribute
    lines, placed badges, raw HTML), of attribute lines before blocks, explicit component ids and the
    anchors a component defines (code segments, spec 8.10). Ids generated inside component HTML are not
    author ids. Two components with one id are LT007 already."""
    seen: dict[str, str] = {}

    def add(ident: str, what: str, loc) -> None:
        if ident not in seen:
            seen[ident] = what
        elif not (what == seen[ident] == "a component id"):
            diags.error("LT058", f"id {ident!r} is used twice on this slide ({seen[ident]} and {what})", loc)

    for ident in re.findall(r'\sid="([^"]+)"', slide.title_html + slide.body_html):
        add(ident, "an element id", slide.loc)
    for b in blocks:
        if b.wrapper_attrs.get("id"):
            add(b.wrapper_attrs["id"], "an element id", b.loc)
        if b.attrs.id:
            add(b.attrs.id, "a component id", b.loc)
        r = results.get(b.index)
        for a in (r.anchors if r is not None else []):
            add(a, f"a segment of {b.name} {b.id!r}", b.loc)


def _check_arrow_targets(slide: Slide, blocks, results, diags: Diagnostics) -> None:
    """LT046 when an `arrow` names an element id that no element of the slide carries; LT063 when it
    names a list item that does not exist, or puts a `bullet` anchor on an end that is not one (spec 8.9)."""
    from .components.visual import arrow_ends, arrow_targets

    arrows = [b for b in blocks if b.name == "arrow" and b.index in results]
    if not arrows:
        return
    ids = set(re.findall(r'\sid="([^"]+)"', slide.body_html + slide.title_html))
    ids |= {b.id for b in blocks if b.id}
    ids |= {a for r in results.values() for a in r.anchors}  # segments of later positions (code-morph)
    outline = None
    for b in arrows:
        data = results[b.index].data or {}
        for ref in arrow_targets(data):
            if ref not in ids:
                diags.warn("LT046", f"arrow: no element with id {ref!r} on this slide", b.loc)
        for i, end, ref, path, bullet in arrow_ends(data):
            if outline is None:
                outline = HtmlOutline(slide.title_html + slide.body_html)
            problem = _list_end_problem(outline, ref, path, bullet)
            if problem:
                diags.error("LT063", f"arrow: step {i + 1}, `{end}`: {problem}", b.loc)


def _resolve_parts(slide: Slide, blocks, results, diags: Diagnostics) -> list[tuple]:
    """Arrow ends written `COMP.NAME` (spec 8.9): a component of the slide names the part through its `part`
    hook, which gives the selector the runtime measures; an element name (`li.done`) keeps the end a CSS
    selector; anything else is LT063. Returns the resolved parts, for the check of their positions."""
    from .components.base import Part
    from .components.visual import arrow_parts, is_element_name

    by_id = {b.id: b for b in blocks}
    found = []
    for b in blocks:
        if b.name != "arrow" or b.index not in results:
            continue
        data = results[b.index].data or {}
        for i, end, comp, name in arrow_parts(data):
            step = data["steps"][i]
            written = f"{comp}.{name}"
            where = f"arrow: step {i + 1}, `{end}`: {written!r}"
            target = by_id.get(comp)
            if target is None:
                if is_element_name(comp):  # a CSS selector after all
                    step[end] = written
                    del step[f"{end}_name"]
                    continue
                diags.error("LT063", f"{where}: no component with the id {comp!r} on this slide", b.loc)
                continue
            if step.get(f"{end}_anchor") == "bullet":
                diags.error("LT063", f"{where}: a `bullet` anchor needs a list item, not a part of a component", b.loc)
                continue
            comp_cls = REGISTRY[target.name]
            if not callable(getattr(comp_cls, "part", None)):
                diags.error("LT063", f"{where}: component {comp!r} ({target.name}) names no parts", b.loc)
                continue
            if target.index not in results:
                continue  # its render failed, already reported
            try:
                part = comp_cls().part(results[target.index], name)
            except ComponentError as e:
                diags.error("LT063", f"{where}: {e}", b.loc)
                continue
            except Exception as e:  # noqa: BLE001
                diags.error("LT022", f"{where}: {target.name} failed to name a part: {type(e).__name__}: {e}", b.loc)
                continue
            if not isinstance(part, Part):
                diags.error("LT047", f"{target.name}: part() must return a Part", b.loc)
                continue
            step[f"{end}_part"] = part.selector
            if part.warning:
                diags.warn("LT046", f"{where}: {part.warning}", b.loc)
            found.append((b, i, end, target, part, written))
    return found


def _spans(values: list[int]) -> str:
    """[5, 6, 7, 9] gives "5 to 7, 9"."""
    out, k = [], 0
    while k < len(values):
        j = k
        while j + 1 < len(values) and values[j + 1] == values[j] + 1:
            j += 1
        out.append(str(values[k]) if j == k else f"{values[k]} to {values[j]}")
        k = j + 1
    return ", ".join(out)


def _check_part_positions(slide: Slide, parts: list[tuple], diags: Diagnostics) -> None:
    """LT046 when an arrow step points at a part drawn at none of the slide steps that show that step (spec
    8.9). A part drawn at some of them only is hidden at the others, silently."""
    if not parts or not slide.positions:
        return
    col = {t.id: k for k, t in enumerate(slide.tracks)}

    def pos(row, ident):
        k = col.get(ident)
        return row[k] if k is not None and k < len(row) else 0

    for arrow, i, end, comp, part, written in parts:
        if part.drawn is None:
            continue
        steps = [n for n, row in enumerate(slide.positions) if pos(row, arrow.id) == i]
        if not steps:
            continue  # this arrow step is never shown
        frames = sorted({pos(slide.positions[n], comp.id) for n in steps})
        if not any(0 <= f < len(part.drawn) and part.drawn[f] for f in frames):
            which = f"slide step{'s' if len(steps) > 1 else ''} {_spans(steps)}"
            diags.warn("LT046", f"arrow: step {i + 1}, `{end}`: {written!r} is drawn at none of the steps that show "
                       f"this arrow step ({which}: position{'s' if len(frames) > 1 else ''} {_spans(frames)} of "
                       f"{comp.id!r}), so the arrow never appears there", arrow.loc)


def _list_end_problem(outline: "HtmlOutline", ref: str, path: list[int] | None, bullet: bool) -> str | None:
    """Why an arrow end that names a list item, or that has a `bullet` anchor, cannot be resolved."""
    written = ref + "".join(f"[{n}]" for n in path or [])
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", ref):  # a CSS selector: the build cannot see what it names
        return f"a `bullet` anchor needs a list item written LIST[N], not the selector {ref!r}"
    el = outline.by_id.get(ref)
    if path is None:  # a bare id with a bullet anchor
        if el is None:
            return f"a `bullet` anchor needs a list item, and no element has the id {ref!r} on this slide"
        if el.tag in ("ul", "ol"):
            return f"a `bullet` anchor needs one item of the list {ref!r}: write {ref}[N]"
        if el.tag != "li":
            return f"a `bullet` anchor needs a list item, and {ref!r} is a <{el.tag}>"
        return None
    if el is None:
        return f"{written!r}: no list with the id {ref!r} on this slide"
    for depth, n in enumerate(path):
        where = ref + "".join(f"[{k}]" for k in path[:depth])
        if depth and (el := next((c for c in el.children if c.tag in ("ul", "ol")), None)) is None:
            return f"{written!r}: item {where!r} has no nested list"
        if el.tag not in ("ul", "ol"):
            return f"{written!r}: {ref!r} is a <{el.tag}>, not a list"
        items = [c for c in el.children if c.tag == "li"]
        if abs(n) > len(items):
            count = f"{len(items)} item" + ("" if len(items) == 1 else "s")
            return f"{written!r}: the list {where!r} has {count}" if not depth else \
                f"{written!r}: the list nested in {where!r} has {count}"
        el = items[n - 1 if n > 0 else n]
    return None


class _Node:
    __slots__ = ("tag", "children")

    def __init__(self, tag: str):
        self.tag = tag
        self.children: list[_Node] = []


class HtmlOutline:
    """The element tree of a slide's HTML, reduced to tags and children, with its elements by id: enough
    to check at build time what an arrow points at (spec 8.9)."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
            "track", "wbr"}

    def __init__(self, text: str):
        from html.parser import HTMLParser

        self.by_id: dict[str, _Node] = {}
        root = _Node("#root")
        stack = [root]
        outline = self

        class Parser(HTMLParser):
            def handle_starttag(self, tag, attrs, closed=False):
                node = _Node(tag)
                stack[-1].children.append(node)
                ident = dict(attrs).get("id")
                if ident:
                    outline.by_id.setdefault(ident, node)
                if not closed and tag not in HtmlOutline.VOID:
                    stack.append(node)

            def handle_startendtag(self, tag, attrs):
                self.handle_starttag(tag, attrs, closed=True)

            def handle_endtag(self, tag):
                for k in range(len(stack) - 1, 0, -1):  # close up to the matching element, if it is open
                    if stack[k].tag == tag:
                        del stack[k:]
                        break

        p = Parser(convert_charrefs=True)
        p.feed(text)
        p.close()


def _valid_result(result, block, diags) -> bool:
    if not isinstance(result, RenderResult):
        diags.error("LT047", f"{block.name}: render() must return a RenderResult", block.loc)
        return False
    if result.positions < 1:
        diags.error("LT047", f"{block.name}: positions must be at least 1", block.loc)
        return False
    if result.meta is not None and len(result.meta) != result.positions:
        diags.error("LT047", f"{block.name}: meta must have one entry per position", block.loc)
        return False
    try:
        json.dumps(result.data)
    except (TypeError, ValueError) as e:
        diags.error("LT047", f"{block.name}: data is not JSON-serializable: {e}", block.loc)
        return False
    return True


def render_components(deck: Deck, use_cache: bool = True) -> None:
    palette = get_theme(deck.meta.theme)["palette"]
    cache = Cache(deck.root.parent / ".lattice-cache", use_cache and deck.meta.build.cache)
    for slide in deck.slides.values():
        render_slide_components(deck, slide, cache, palette)
