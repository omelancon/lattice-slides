"""Diagnostics: errors and warnings with codes and source locations (spec section 12)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceLoc:
    file: Path
    line: int = 1
    col: int = 1

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"


@dataclass
class Diagnostic:
    code: str
    severity: str  # "error" | "warning"
    message: str
    loc: SourceLoc | None = None

    def format(self) -> str:
        where = f"{self.loc}: " if self.loc else ""
        return f"{where}{self.severity} {self.code}: {self.message}"


class BuildError(Exception):
    """Raised when a build stops because of errors."""

    def __init__(self, diagnostics: "Diagnostics"):
        self.diagnostics = diagnostics
        super().__init__("\n".join(d.format() for d in diagnostics.items if d.severity == "error"))


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, loc: SourceLoc | None = None) -> None:
        self.items.append(Diagnostic(code, "error", message, loc))

    def warn(self, code: str, message: str, loc: SourceLoc | None = None) -> None:
        self.items.append(Diagnostic(code, "warning", message, loc))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "warning"]

    def has_errors(self) -> bool:
        return any(d.severity == "error" for d in self.items)

    def raise_if_errors(self) -> None:
        if self.has_errors():
            raise BuildError(self)

    def format(self) -> str:
        return "\n".join(d.format() for d in self.items)
