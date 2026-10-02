"""The Deck model (spec section 4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .attrs import Attrs
from .diagnostics import Diagnostics, SourceLoc


# ---------------------------------------------------------------- front matter
class FramesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_full_bytes: int = 2 * 1024 * 1024
    keyframe_interval: int = 16


class BuildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cache: bool = True
    output: Literal["single", "dir"] = "single"
    frames: FramesConfig = Field(default_factory=FramesConfig)


DEFAULT_TRANSITIONS = {"next": "slide", "branch": "slide", "detour": "zoom", "link": "fade"}

DEFAULT_KEYS: dict[str, list[str]] = {
    "next": ["ArrowRight", " ", "PageDown"],
    "prev": ["ArrowLeft", "PageUp"],
    "skip-forward": ["Shift+ArrowRight"],
    "skip-back": ["Shift+ArrowLeft"],
    "last-step": ["End"],
    "skip-detour": ["Shift+ArrowDown"],
    "enter-detour": ["ArrowDown"],
    "return": ["ArrowUp", "Backspace"],
    "overview": ["o"],
    "goto": ["g"],
    "presenter": ["p"],
    "tour": ["t"],
    "home": ["Home"],
}


class FrontMatter(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str | None = None
    author: str | None = None
    date: str | None = None
    theme: str = "default"
    aspect: Literal["16:9", "16:10", "4:3"] = "16:9"
    start: str | None = None
    plugins: list[str] = Field(default_factory=list)
    keys: dict[str, str | list[str]] = Field(default_factory=dict)
    transitions: dict[str, str] = Field(default_factory=dict)
    tours: dict[str, list[str] | Literal["main"]] = Field(default_factory=dict)
    build: BuildConfig = Field(default_factory=BuildConfig)


# ---------------------------------------------------------------- blocks
@dataclass
class ComponentBlock:
    name: str
    attrs: Attrs
    body: str
    loc: SourceLoc
    file_dir: Path
    index: int  # 1-based index among components of the slide
    id: str | None = None  # component id (attrs.id or generated)
    follow: str | None = None
    wrapper_attrs: dict[str, str] = field(default_factory=dict)

    @property
    def placeholder(self) -> str:
        return f"\x00C{self.index}\x00"


@dataclass
class BranchOption:
    target: str
    label_html: str | None  # None: use target title
    description_html: str | None
    key: str | None
    loc: SourceLoc


@dataclass
class Branch:
    options: list[BranchOption]
    layout: str = "menu"
    loc: SourceLoc | None = None


@dataclass
class TimelineAssign:
    track: str
    kind: Literal["abs", "rel", "range", "end"]
    a: int = 0
    b: int | None = None  # range end; None means "end"


@dataclass
class TimelineLine:
    assigns: list[TimelineAssign]
    loc: SourceLoc
    detour: str | None = None  # a detour step (spec 6.4): the line is `detour ID [blocking]` and has no assigns
    blocking: bool = False


@dataclass
class Track:
    id: str
    kind: Literal["reveal", "component"]
    positions: int
    instance: str | None = None
    follow: str | None = None


@dataclass
class Detour:
    key_obj: int  # internal identity used before ids are assigned
    origin: "Slide"
    attrs: Attrs
    loc: SourceLoc
    index_in_origin: int
    slides: list["Slide"] = field(default_factory=list)
    id: str = ""
    label: str = ""
    key: str | None = None
    badge: bool = True
    badge_mode: Literal["step", "next"] | None = None  # `badge=step|next`: shown according to the detour step (spec 3.9)
    badges: list[tuple[str | None, SourceLoc]] = field(default_factory=list)  # rendered badges: (mode, location)
    at: int | None = None  # `at=N`: entered as a detour step after step N of the origin (spec 6.4)
    blocking: bool = False  # a blocking detour step cannot be rolled over by a multi-step move


@dataclass
class Slide:
    raw_title: str
    attrs: Attrs
    loc: SourceLoc
    file_index: int
    scope: Detour | None  # None = root scope
    offpath: bool
    path: Path = Path(".")  # absolute path of the source file
    groups: list[Any] = field(default_factory=list)  # token groups or ("detour", Detour)
    detours: list[Detour] = field(default_factory=list)
    id: str = ""
    untitled: bool = False
    title_html: str = ""
    title_text: str = ""
    next_spec: str | None = None  # explicit target, "back", "none" or None (implicit)
    layout: str = "default"
    transition: str | None = None
    pdf_steps: str | list | None = None  # steps printed by the PDF export (spec 11.5); None: the default
    data: dict[str, str] = field(default_factory=dict)
    # built from the body
    body_html: str = ""
    components: list[ComponentBlock] = field(default_factory=list)
    reveal_count: int = 0
    branch: Branch | None = None
    links: list[str] = field(default_factory=list)
    notes_html: str | None = None
    timeline: list[TimelineLine] | None = None
    timeline_loc: SourceLoc | None = None
    uses_math: bool = False
    # resolved
    next: str | None = None  # slide id, "back" or None
    tracks: list[Track] = field(default_factory=list)
    positions: list[list[int]] = field(default_factory=lambda: [[]])
    step_detours: dict[int, dict] = field(default_factory=dict)  # step -> {"id", "blocking"} (spec 6.4)

    @property
    def scope_id(self) -> str:
        return self.scope.id if self.scope is not None else "root"

    @property
    def steps(self) -> int:
        return len(self.positions)


@dataclass
class Edge:
    source: str
    target: str
    kind: Literal["next", "branch", "detour", "link"]
    key: str | None = None
    implicit: bool = False


@dataclass
class Deck:
    root: Path
    meta: FrontMatter
    slides: dict[str, Slide]
    detours: dict[str, Detour]
    diagnostics: Diagnostics
    files: list[Path] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    start: str = ""
    main_path: list[str] = field(default_factory=list)
    tours: dict[str, list[str]] = field(default_factory=dict)
    instances: dict[str, dict] = field(default_factory=dict)
    component_names: set[str] = field(default_factory=set)
    dependencies: set[Path] = field(default_factory=set)
    uses_math: bool = False
    requires: set[str] = field(default_factory=set)
