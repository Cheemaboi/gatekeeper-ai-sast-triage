"""Tools the triage agent can call while investigating an alert.

All tools are read-only and confined to the benchmark source tree, so an agent
cannot modify the repository it is judging. Each call has a budget cost so the
evaluation can measure tool efficiency.
"""
from __future__ import annotations

import re
from pathlib import Path

MAX_OBS_CHARS = 4000


class ToolError(Exception):
    pass


class RepoTools:
    COST = {"read_file": 1, "grep": 1, "find_definition": 2}

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe_path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root)) or not p.is_file():
            raise ToolError(f"no such file inside the repository: {rel}")
        return p

    def read_file(self, path: str, start: int = 1, end: int = 200) -> str:
        lines = self._safe_path(path).read_text(errors="replace").splitlines()
        start, end = max(1, int(start)), min(len(lines), int(end))
        out = "\n".join(f"{n:4d}  {lines[n - 1]}" for n in range(start, end + 1))
        return out[:MAX_OBS_CHARS]

    def grep(self, pattern: str, path_glob: str = "src/main/java/**/*.java",
             max_hits: int = 20) -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"bad regex: {e}") from e
        hits = []
        for p in sorted(self.root.glob(path_glob)):
            for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{p.relative_to(self.root)}:{n}: {line.strip()}")
                    if len(hits) >= max_hits:
                        return "\n".join(hits) + "\n[truncated]"
        return "\n".join(hits) or "(no matches)"

    def find_definition(self, symbol: str) -> str:
        """Locate a class or method definition (e.g. a helper the test calls)."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
            raise ToolError("symbol must be a plain Java identifier")
        rx = re.compile(rf"(class|interface)\s+{symbol}\b|\b{symbol}\s*\([^;]*\)\s*(throws[^{{]*)?\{{")
        for p in sorted(self.root.glob("src/main/java/**/*.java")):
            lines = p.read_text(errors="replace").splitlines()
            for n, line in enumerate(lines, 1):
                if rx.search(line):
                    rel = str(p.relative_to(self.root))
                    return f"{rel}:{n}\n" + self.read_file(rel, n, n + 40)
        return f"(definition of {symbol} not found)"

    def call(self, name: str, args: dict) -> tuple[str, int]:
        if name not in self.COST:
            raise ToolError(f"unknown tool {name!r}")
        return getattr(self, name)(**args), self.COST[name]

    @staticmethod
    def describe() -> str:
        return (
            "read_file(path, start=1, end=200): numbered lines of a repository file\n"
            "grep(pattern, path_glob='src/main/java/**/*.java'): regex search, max 20 hits\n"
            "find_definition(symbol): source of a class or method definition"
        )
