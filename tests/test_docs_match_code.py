"""The documents must not claim anything the tree contradicts.

A 32-agent adversarial review found 25 such claims in one pass. Eleven of them
were mechanical — a version string, a count, a tool name, an identifier that had
been renamed — and every one would have been caught by grepping the docs against
the code. The other fourteen needed judgement and still do.

So this is the cheap half, run in the same loop as the tests, because the
expensive half only happens when someone remembers to ask for it.

WHAT IT DELIBERATELY DOES NOT CHECK
-----------------------------------
Historical statements. docs/PROGRESS.md is a log: an entry saying "we were on
mcp 1.27" was true when written and must stay. Only documents that describe the
PRESENT are checked, and PROGRESS is exempt below its first session heading.
"""
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, "src")

ROOT = Path(__file__).resolve().parents[1]

# Documents that describe the present. Anything not listed is unchecked on purpose.
CURRENT = [
    "README.md", "CLAUDE.md",
    "docs/ARCHITECTURE.md", "docs/PRODUCT.md", "docs/PRODUCT-FEEDBACK.md",
    "docs/SUBMISSION.md", "docs/design-brief.html", "docs/SPIKE.md",
    "docs/diagrams/system.architecture.json",
]

failures: list[str] = []


def check(label, ok, detail=""):
    print(f"  [{'ok  ' if ok else 'FAIL'}] {label}{('  ' + detail) if detail else ''}")
    if not ok:
        failures.append(f"{label}: {detail}")


def docs():
    for rel in CURRENT:
        p = ROOT / rel
        if p.exists():
            yield rel, p.read_text(encoding="utf-8")


def test_no_retired_identifiers():
    """Names the code no longer uses. Each was renamed and left behind in prose."""
    retired = {
        "FastMCP": "renamed MCPServer in mcp 2.x",
        "SimulatedSource": "replaced by ScenarioSource",
        "start_service": "the tool is start_recipe",
    }
    for rel, text in docs():
        for name, why in retired.items():
            # A forward reference ("becomes X if...") is legitimate.
            hits = [m for m in re.finditer(re.escape(name), text)
                    if "Becomes" not in text[max(0, m.start() - 60):m.start()]
                    and "was the 1.x name" not in text[m.start():m.start() + 120]
                    and "no longer exists" not in text[max(0, m.start() - 90):m.start() + 90]]
            check(f"{rel} free of {name!r}", not hits, why if hits else "")


def test_mcp_version_matches_pyproject():
    spec = tomllib.loads((ROOT / "pyproject.toml").read_text())
    pin = next(d for d in spec["project"]["dependencies"] if d.startswith("mcp"))
    major = re.search(r">=(\d+)\.", pin).group(1)
    for rel, text in docs():
        wrong = re.findall(r"`?mcp`? (\d+)\.\d+", text)
        bad = sorted({v for v in wrong if v != major})
        check(f"{rel} names mcp {major}.x", not bad,
              f"also names mcp {bad} but pyproject pins {pin}" if bad else "")


def test_tool_names_are_real():
    """Every `tool_name` in the docs must exist on the server, or be marked planned."""
    import asyncio

    from mise.server import mcp
    real = {t.name for t in asyncio.run(mcp.list_tools())}
    planned = {"whats_next", "start_service"}
    for rel, text in docs():
        named = set(re.findall(r"`(\w+_\w+)`\b", text)) | set(
            re.findall(r"<code>(\w+_\w+)</code>", text))
        # Verb-first, so a data field like `label_doneness` is not mistaken for a tool.
        suspects = {n for n in named
                    if n.split("_")[0] in {"start", "check", "advance", "record", "panel",
                                           "whats"}}
        unknown = suspects - real - planned
        check(f"{rel} names only real tools", not unknown, f"unknown: {sorted(unknown)}")


def test_counts_are_right():
    n_tests = len(list((ROOT / "tests").glob("test_*.py")))
    n_friction = (ROOT / "docs/FRICTION.md").read_text().count("\n## ")
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
    for rel, text in docs():
        low = text.lower()
        for n, w in words.items():
            if n == n_tests:
                continue
            for phrase in (f"{w} test suites", f"{n} test suites"):
                check(f"{rel}: no wrong test-suite count ({phrase})",
                      phrase not in low, f"tests/ holds {n_tests}")
            if n != n_friction:
                for phrase in (f"{w} banked friction", f"{n} banked friction"):
                    check(f"{rel}: no wrong friction count ({phrase})",
                          phrase not in low, f"FRICTION.md has {n_friction}")


def test_referenced_files_exist():
    """A doc pointing at a path that is gone sends a reader nowhere."""
    pat = re.compile(r"`((?:src|docs|tests|evals|infra|ui|policies)/[\w./-]+)`")
    for rel, text in docs():
        missing = sorted({m for m in pat.findall(text)
                          if not (ROOT / m).exists() and not m.endswith("/")})
        check(f"{rel} references only real paths", not missing, f"missing: {missing}")


def test_progress_log_is_exempt_but_current_docs_are_not():
    """Guard the guard: PROGRESS must stay unchecked, or history gets rewritten."""
    check("docs/PROGRESS.md is exempt", "docs/PROGRESS.md" not in CURRENT,
          "a log must preserve what was true when written")


for f in (test_no_retired_identifiers, test_mcp_version_matches_pyproject,
          test_tool_names_are_real, test_counts_are_right,
          test_referenced_files_exist,
          test_progress_log_is_exempt_but_current_docs_are_not):
    f()

if failures:
    print(f"\n{len(failures)} doc claim(s) the tree contradicts:")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("\nall docs match the code")
