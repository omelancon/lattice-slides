"""Build every example deck into its own folder (examples/*/talk.html) and the user manual
(user_manual/manual.html)."""
import sys
from pathlib import Path

from lattice.cli import main

root = Path(__file__).resolve().parent.parent
status = 0
for deck in sorted((root / "examples").glob("*/talk.md")) + [root / "user_manual" / "manual.md"]:
    status |= main(["build", str(deck), "--no-cache"])
sys.exit(status)
