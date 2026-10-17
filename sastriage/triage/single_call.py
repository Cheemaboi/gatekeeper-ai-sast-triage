"""Baseline B1: one LLM call per alert, no tools (non-agentic)."""
from __future__ import annotations

from pathlib import Path

from ..contracts import Label, LabelledFinding, TriageRecord, Verdict
from ..data import read_source
from ..providers import Provider, extract_json
from .prompts import SYSTEM_SINGLE, alert_block


class SingleCallTriage:
    name = "single_call"

    def __init__(self, provider: Provider, bench_root: Path, context_lines: int | None = None):
        self.provider = provider
        self.root = bench_root
        self.context_lines = context_lines   # None = whole file (test cases are short)

    def triage(self, lf: LabelledFinding) -> TriageRecord:
        f = lf.finding
        snippet = read_source(self.root, f, self.context_lines)
        rec = TriageRecord(system=self.name, provider=self.provider.name,
                           model=self.provider.model, truth=lf.truth,
                           verdict=Verdict(finding_id=f.finding_id, label=Label.UNSURE,
                                           confidence=0.0, rationale=""))
        try:
            c = self.provider.complete(SYSTEM_SINGLE, [{"role": "user",
                                                        "content": alert_block(f, snippet)}])
            rec.llm_calls, rec.input_tokens, rec.output_tokens = 1, c.input_tokens, c.output_tokens
            rec.latency_s = c.latency_s
            out = extract_json(c.text)
            rec.verdict = Verdict(finding_id=f.finding_id, label=Label(out["label"]),
                                  confidence=float(out.get("confidence", 0.5)),
                                  rationale=str(out.get("rationale", ""))[:600])
        except Exception as e:  # malformed output counts as an error, not a verdict
            rec.error = f"{type(e).__name__}: {e}"
        return rec
