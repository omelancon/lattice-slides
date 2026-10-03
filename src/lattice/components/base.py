"""Component contract, Python side (spec section 8)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from ..diagnostics import SourceLoc


class ComponentError(Exception):
    """Raise from ``render`` to report a clean error at the block's location."""


class MissingFileError(ComponentError):
    """A file referenced by a block does not exist (reported as LT045)."""


class NoOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass
class Asset:
    name: str
    data: bytes
    mime: str


@dataclass
class RenderResult:
    html: str
    data: Any = None
    positions: int = 1
    meta: list[dict] | None = None
    assets: list[Asset] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # shared libraries for this instance only
    anchors: list[str] = field(default_factory=list)   # element ids this instance defines for authors (8.10)


class Component:
    name: ClassVar[str] = ""
    version: ClassVar[str] = "1"
    Options: ClassVar[type[BaseModel]] = NoOptions
    body: ClassVar[Literal["yaml", "text", "none"]] = "yaml"
    runtime: ClassVar[str | None] = None  # file name in lattice/runtime/components or an absolute path
    css: ClassVar[list[str]] = []
    requires: ClassVar[list[str]] = []

    def render(self, block, opts: BaseModel, ctx: "RenderContext") -> RenderResult:  # pragma: no cover
        raise NotImplementedError


REGISTRY: dict[str, type[Component]] = {}


class RegistryError(Exception):
    pass


def register(name: str) -> Callable[[type[Component]], type[Component]]:
    def deco(cls: type[Component]) -> type[Component]:
        prev = REGISTRY.get(name)
        if prev is not None and prev is not cls and (
            (prev.__module__, prev.__qualname__) != (cls.__module__, cls.__qualname__)
        ):
            raise RegistryError(f"component {name!r} registered twice")
        cls.name = name
        REGISTRY[name] = cls
        return cls

    return deco


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_MODULE_CACHE: dict[tuple[Path, float], Any] = {}


def import_path(path: Path):
    """Import a Python file by path (reloaded when its mtime changes)."""
    key = (path, path.stat().st_mtime)
    if key in _MODULE_CACHE:
        return _MODULE_CACHE[key]
    mod_name = "lattice_user_" + hashlib.md5(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    added = str(path.parent)
    sys.path.insert(0, added)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(added)
        except ValueError:
            pass
    _MODULE_CACHE[key] = module
    return module


class RenderContext:
    def __init__(self, *, meta, slide_id: str, instance_id: str, root_dir: Path, file_dir: Path,
                 palette: dict[str, str], leader: RenderResult | None, loc: SourceLoc, diags, frames_config):
        self.meta = meta
        self.slide_id = slide_id
        self.instance_id = instance_id
        self.root_dir = root_dir
        self.file_dir = file_dir
        self.palette = palette
        self.leader = leader
        self.loc = loc
        self._diags = diags
        self.frames_config = frames_config
        self.dependencies: set[Path] = set()
        self.warnings: list[tuple[str, str]] = []
        self.seed = int(hashlib.sha256(instance_id.encode()).hexdigest()[:8], 16)

    # -- files
    def path(self, p: str | Path) -> Path:
        full = (self.file_dir / p).resolve()
        if not full.exists():
            raise MissingFileError(f"file not found: {p}")
        self.dependencies.add(full)
        return full

    def depends(self, p: str | Path) -> None:
        self.dependencies.add(self.path(p))

    def call(self, ref: str, *args, **kwargs):
        if ":" not in ref:
            raise ComponentError(f"expected 'file.py:function', got {ref!r}")
        file, func = ref.rsplit(":", 1)
        module = import_path(self.path(file))
        fn = getattr(module, func, None)
        if fn is None:
            raise ComponentError(f"{file} has no function {func!r}")
        return fn(*args, **kwargs)

    # -- graphs
    def load_graph(self, p: str | Path):
        from ..graphs import load_graph

        return load_graph(self.path(p))

    def layout(self, graph, engine: str = "dot", **kw):
        from ..graphs import layout

        return layout(graph, engine=engine, seed=self.seed, **kw)

    # -- diagnostics
    def warn(self, message: str, code: str = "LT046") -> None:
        """A warning at the block's location (LT046; built-in components pass their own code). Warnings are
        kept with a cached result and reported again when it is reused (spec 8.6)."""
        self.warnings.append((code, message))
        self._diags.warn(code, message, self.loc)


def cache_key(parts: list[Any]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()
