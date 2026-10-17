"""Structured contracts shared by every component.

Every stage of the pipeline (data loading, triage systems, CI gate, evaluation)
exchanges these objects, so each stage can be tested and swapped independently.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Label(str, Enum):
    TRUE_POSITIVE = "TP"   # the alert points at a real vulnerability
    FALSE_POSITIVE = "FP"  # the alert is a false alarm
    UNSURE = "UNSURE"      # the system abstains; a human must review


class Finding(BaseModel):
    """One alert raised by a static analyser, normalised across tools."""

    finding_id: str
    tool: str
    rule: str                      # tool-specific rule id, e.g. SQL_INJECTION_JDBC
    cwe: int                       # normalised CWE (see data.CWE_NORMALISE)
    category: str                  # benchmark category, e.g. sqli
    file: str                      # path relative to the source root
    test_case: str                 # e.g. BenchmarkTest00001
    line_start: int
    line_end: int
    message: str = ""


class GroundTruth(BaseModel):
    test_case: str
    category: str
    cwe: int
    is_vulnerable: bool


class LabelledFinding(BaseModel):
    finding: Finding
    truth: bool                    # True if the alert is a real vulnerability


class Evidence(BaseModel):
    kind: Literal["code", "grep", "definition", "note"]
    detail: str


class Verdict(BaseModel):
    """Output contract of every triage system."""

    finding_id: str
    label: Label
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    evidence: list[Evidence] = []


class StepRecord(BaseModel):
    """One step of an agent episode (kept for trace analysis and ablations)."""

    step: int
    thought: str = ""
    action: str
    args: dict = {}
    observation: str = ""
    cost_units: int = 0


class TriageRecord(BaseModel):
    """A verdict plus everything needed to evaluate how it was produced."""

    system: str
    provider: str
    model: str
    verdict: Verdict
    truth: Optional[bool] = None
    steps: list[StepRecord] = []
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    error: Optional[str] = None


class GateDecision(BaseModel):
    """What the CI/CD gate does with a batch of verdicts."""

    passed: bool
    blocking: list[str]            # finding ids that block the merge
    needs_review: list[str]        # abstentions routed to a human
    suppressed: list[str]          # alerts judged false positives
    summary: str
