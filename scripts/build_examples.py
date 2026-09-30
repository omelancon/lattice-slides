"""Build every example deck into its own folder (examples/*/talk.html)."""
import sys
from pathlib import Path

from lattice.cli import main

root = Path(__file__).resolve().parent.parent / "examples"
status = 0
for deck in sorted(root.glob("*/talk.md")):
    status |= main(["build", str(deck), "--no-cache"])
sys.exit(status)
