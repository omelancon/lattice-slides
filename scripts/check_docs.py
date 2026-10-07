"""Check that the documentation agrees with itself and with the code.

Run from anywhere: python scripts/check_docs.py
Checks: cited sections exist, cited repository paths exist, diagnostic codes in the code and in
spec section 12 match, component names mentioned are registered, CLI flags mentioned exist,
manual slides cited by id exist, and version numbers agree. It cannot judge prose: reread the
documents as docs/SKILL.md asks.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = {"README": ROOT / "README.md", "spec": ROOT / "docs/spec.md",
        "report": ROOT / "docs/design-report.md", "skill": ROOT / "docs/SKILL.md",
        "user_skill": ROOT / "docs/USER_SKILL.md", "manual": ROOT / "user_manual/manual.md"}
problems: list[str] = []


def sections(text: str) -> set[str]:
    return set(re.findall(r"^#{2,3} (\d+(?:\.\d+)?)\.? ", text, re.M))


texts = {k: p.read_text(encoding="utf-8") for k, p in DOCS.items()}
spec_secs, report_secs = sections(texts["spec"]), sections(texts["report"])
manual_ids = set(re.findall(r"\{#([\w-]+)", texts["manual"]))  # slide, detour and element ids

# 1. cited sections exist ("spec section 7.6", "report section 6", "section 3.4" inside the spec)
cite = re.compile(r"(spec|report)(?: \(?|, )?sections? ((?:\d+(?:\.\d+)?(?:,? (?:and |to )?)?)+)", re.I)
for name, text in texts.items():
    for m in cite.finditer(text):
        target = spec_secs if m.group(1).lower() == "spec" else report_secs
        for num in re.findall(r"\d+(?:\.\d+)?", m.group(2)):
            if num not in target:
                problems.append(f"{name}: cites {m.group(1)} section {num}, which does not exist")
for m in re.finditer(r"\(?section (\d+(?:\.\d+)?)\)?", texts["spec"]):
    if m.group(1) not in spec_secs:
        problems.append(f"spec: internal reference to section {m.group(1)} does not exist")

# 2. cited repository paths exist
path_re = re.compile(r"`((?:src|docs|examples|scripts|tests|user_manual)/[\w./*-]+)`")
for name, text in texts.items():
    for p in set(path_re.findall(text)):
        if "*" in p:
            if not list(ROOT.glob(p)):
                problems.append(f"{name}: path pattern {p} matches nothing")
        elif not (ROOT / p).exists():
            problems.append(f"{name}: path {p} does not exist")

# 3. diagnostic codes: emitted by the code <-> listed in spec section 12
code_text = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
emitted = set(re.findall(r'"(LT0\d\d)"', code_text))
table = set(re.findall(r"^\| (LT0\d\d) \|", texts["spec"], re.M))
for c in sorted(emitted - table):
    problems.append(f"code emits {c}, missing from spec section 12")
for c in sorted(table - emitted):
    problems.append(f"spec section 12 lists {c}, never emitted by the code")
for name, text in texts.items():
    for c in sorted(set(re.findall(r"LT0\d\d", text)) - table):
        problems.append(f"{name}: mentions {c}, not in spec section 12")

# 4. components mentioned in backticks are registered
sys.path.insert(0, str(ROOT / "src"))
from lattice.components import REGISTRY  # noqa: E402
from lattice.components.base import import_path  # noqa: E402

import_path(ROOT / "user_manual/lattice_plugins.py")  # the manual's own components

for name, text in texts.items():
    for comp in set(re.findall(r"```([a-z]+-(?:anim|steps))\b", text)) | set(re.findall(r"`([a-z]+-(?:anim|steps))`", text)):
        if comp not in REGISTRY and comp not in manual_ids:  # `badge-steps` is a manual slide
            problems.append(f"{name}: component {comp} is not registered")

# 5. CLI flags and commands mentioned exist
cli = (ROOT / "src/lattice/cli.py").read_text(encoding="utf-8")
for name, text in texts.items():
    for cmd, flag in re.findall(r"lattice (\w+)[^\n`]*?(--[a-z-]+)", text):
        if f'"{flag}"' not in cli:
            problems.append(f"{name}: `lattice {cmd} ... {flag}` is not a CLI option")
    for cmd in set(re.findall(r"`lattice (\w+)", text)):
        if f'add_parser("{cmd}"' not in cli:
            problems.append(f"{name}: `lattice {cmd}` is not a CLI command")

# 6. manual slides cited as "manual `id`" (or "manual `a`, `b` and `c`") exist in the manual
for name, text in texts.items():
    for m in re.finditer(r"\bmanual ((?:`[\w-]+`(?:,? (?:and )?)?)+)", text):
        for sid in re.findall(r"`([\w-]+)`", m.group(1)):
            if sid not in manual_ids:
                problems.append(f"{name}: cites manual slide {sid}, which does not exist")

# 7. versions agree
version = re.search(r'__version__ = "([^"]+)"', (ROOT / "src/lattice/__init__.py").read_text()).group(1)
pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
if version != pyproject:
    problems.append(f"version {version} in __init__.py but {pyproject} in pyproject.toml")
for name in ("README", "spec", "report", "manual"):
    found = set(re.findall(r"\bv?(\d+\.\d+\.\d+)\b", texts[name].split("\n## ")[0]))
    if version not in found:
        problems.append(f"{name}: the introduction does not name the current version {version}")

for p in problems:
    print("-", p)
print(f"{len(problems)} problem(s)")
sys.exit(1 if problems else 0)
