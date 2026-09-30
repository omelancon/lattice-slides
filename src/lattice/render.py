"""Component rendering, caching and step compilation (spec sections 6 and 8)."""
from __future__ import annotations

import html
import json
import traceback
from pathlib import Path

import yaml
from pydantic import ValidationError

from . import __version__
from .components.base import REGISTRY, ComponentError, MissingFileError, RenderContext, RenderResult, cache_key, file_hash
from .diagnostics import Diagnostics
from .model import ComponentBlock, Deck, Slide, Track
from .themes import get_theme
from .timeline import compile_steps


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

    def get(self, key: str) -> tuple[RenderResult, set[Path]] | None:
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
            result = RenderResult(r["html"], r["data"], r["positions"], r["meta"], requires=r.get("requires", []))
            return result, {Path(p) for p in entry["deps"]}
        except (OSError, ValueError, KeyError):
            return None

    def put(self, key: str, result: RenderResult, deps: set[Path]) -> None:
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            entry = {"deps": {str(p): file_hash(p) for p in deps if p.is_file()},
                     "result": {"html": result.html, "data": result.data, "positions": result.positions,
                                "meta": result.meta, "requires": result.requires}}
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
            result, deps = hit
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
            cache.put(key, result, deps)
        deck.dependencies.update(deps)
        results[b.index] = result
        keys[b.index] = key
        if leader is not None and result.positions != results[leader.index].positions:
            diags.error("LT027", f"follower {b.id!r} has {result.positions} positions, leader {leader.id!r} has "
                        f"{results[leader.index].positions}", b.loc)
        if result.positions > 1 and comp_cls.runtime is None:
            diags.error("LT047", f"{b.name} has several positions but no runtime", b.loc)

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
    independent = [t for t in tracks if t.follow is None and t.positions > 1 and t.kind == "component"]
    if len(independent) + (1 if slide.reveal_count else 0) >= 2 or slide.timeline is not None:
        for t in independent:
            blk = next(x for x in rendered if x.id == t.id)
            if blk.attrs.id is None:
                diags.error("LT033", f"component {blk.name!r} needs an #id to be used in a timeline", blk.loc)
    slide.tracks = tracks
    compile_steps(slide, diags)


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
