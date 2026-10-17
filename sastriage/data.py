"""Data pipeline: OWASP Benchmark ground truth + SAST tool output -> labelled findings.

Source data (fetched by scripts/fetch_benchmark.sh, not vendored here):
  * expectedresults-1.2.csv  -- ground truth for 2,740 Java test cases
  * results/*.xml            -- SpotBugs/FindSecBugs reports shipped with the benchmark
  * src/main/java/...        -- the test-case source code the agent can inspect
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from .contracts import Finding, GroundTruth, LabelledFinding

TESTCODE_DIR = Path("src/main/java/org/owasp/benchmark/testcode")

# Benchmark category -> canonical CWE used by the OWASP scorecard
CATEGORY_CWE = {
    "cmdi": 78, "crypto": 327, "hash": 328, "ldapi": 90, "pathtraver": 22,
    "securecookie": 614, "sqli": 89, "trustbound": 501, "weakrand": 330,
    "xpathi": 643, "xss": 79,
}
CWE_CATEGORY = {v: k for k, v in CATEGORY_CWE.items()}

# Tool CWEs that the scorecard folds into a benchmark category
CWE_NORMALISE = {
    326: 327, 329: 327, 353: 327,   # DES, static IV, missing integrity -> weak crypto
    23: 22, 36: 22,                 # relative / absolute path traversal
}
# Rule types FindSecBugs emits without a cweid attribute but which are in scope
RULE_CWE = {"PADDING_ORACLE": 327}


def load_ground_truth(bench_root: Path) -> dict[str, GroundTruth]:
    truth: dict[str, GroundTruth] = {}
    with open(bench_root / "expectedresults-1.2.csv", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("#"):
                continue
            name, category, real, cwe = (c.strip() for c in row[:4])
            truth[name] = GroundTruth(test_case=name, category=category,
                                      cwe=int(cwe), is_vulnerable=real == "true")
    return truth


def _normalise_cwe(rule: str, raw: str | None) -> int | None:
    if raw is None:
        return RULE_CWE.get(rule)
    cwe = int(raw)
    return CWE_NORMALISE.get(cwe, cwe)


def parse_spotbugs_xml(xml_path: Path, tool: str) -> list[Finding]:
    """Parse a SpotBugs/FindSecBugs BugCollection into in-scope findings."""
    root = ET.parse(xml_path).getroot()
    findings: list[Finding] = []
    for i, bug in enumerate(root.findall("BugInstance")):
        cls = bug.find("Class")
        if cls is None or ".testcode.BenchmarkTest" not in cls.get("classname", ""):
            continue
        rule = bug.get("type", "")
        cwe = _normalise_cwe(rule, bug.get("cweid"))
        if cwe not in CWE_CATEGORY:          # out-of-scope / informational alert
            continue
        line = bug.find("SourceLine")
        test_case = cls.get("classname").rsplit(".", 1)[-1].split("$")[0]
        msg = bug.find("LongMessage")
        findings.append(Finding(
            finding_id=f"{tool}-{i}",
            tool=tool,
            rule=rule,
            cwe=cwe,
            category=CWE_CATEGORY[cwe],
            file=str(TESTCODE_DIR / f"{test_case}.java"),
            test_case=test_case,
            line_start=int(line.get("start", 0)) if line is not None else 0,
            line_end=int(line.get("end", 0)) if line is not None else 0,
            message=(msg.text or "") if msg is not None else "",
        ))
    return findings


def dedupe_per_test(findings: list[Finding]) -> list[Finding]:
    """Keep one alert per (test case, category): the scorecard unit of analysis."""
    seen: dict[tuple[str, str], Finding] = {}
    for f in findings:
        seen.setdefault((f.test_case, f.category), f)
    return list(seen.values())


def label_findings(findings: list[Finding],
                   truth: dict[str, GroundTruth]) -> list[LabelledFinding]:
    """An alert is a true positive iff its test case is vulnerable in that category."""
    out = []
    for f in findings:
        gt = truth.get(f.test_case)
        if gt is None:
            continue
        out.append(LabelledFinding(
            finding=f,
            truth=gt.is_vulnerable and gt.category == f.category,
        ))
    return out


def read_source(bench_root: Path, finding: Finding, context: int | None = None) -> str:
    """Return numbered source of the finding's file (optionally a window)."""
    lines = (bench_root / finding.file).read_text(errors="replace").splitlines()
    lo, hi = 1, len(lines)
    if context is not None and finding.line_start:
        lo = max(1, finding.line_start - context)
        hi = min(len(lines), finding.line_end + context)
    return "\n".join(f"{n:4d}  {lines[n - 1]}" for n in range(lo, hi + 1))
