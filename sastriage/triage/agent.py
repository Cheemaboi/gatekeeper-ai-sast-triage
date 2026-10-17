"""Proposed system skeleton: a budgeted ReAct-style triage agent.

The loop is deliberately small and fully traced so that ablations are easy:
  * tools on/off          -> compare with SingleCallTriage
  * budget sweep          -> --budget
  * abstention on/off     -> --no-abstain (UNSURE is coerced to the safer TP)
  * confidence threshold  -> verdicts below --min-confidence become UNSURE
"""
from __future__ import annotations

import time
from pathlib import Path

from ..contracts import Evidence, Label, LabelledFinding, StepRecord, TriageRecord, Verdict
from ..data import read_source
from ..providers import Provider, extract_json
from ..tools import RepoTools, ToolError
from .prompts import SYSTEM_AGENT, alert_block


class AgentTriage:
    name = "agent"

    def __init__(self, provider: Provider, bench_root: Path, budget: int = 8,
                 max_turns: int = 10, allow_abstain: bool = True,
                 min_confidence: float = 0.0):
        self.provider = provider
        self.root = bench_root
        self.tools = RepoTools(bench_root)
        self.budget = budget
        self.max_turns = max_turns
        self.allow_abstain = allow_abstain
        self.min_confidence = min_confidence
        self.system = SYSTEM_AGENT.format(tools=RepoTools.describe())

    def _finalise(self, f, out: dict) -> Verdict:
        label = Label(out.get("label", "UNSURE"))
        conf = float(out.get("confidence", 0.5))
        if label != Label.UNSURE and conf < self.min_confidence:
            label = Label.UNSURE
        if label == Label.UNSURE and not self.allow_abstain:
            label = Label.TRUE_POSITIVE      # fail safe: keep the alert
        ev = [Evidence(kind="code", detail=str(e)[:300]) for e in out.get("evidence", [])][:10]
        return Verdict(finding_id=f.finding_id, label=label, confidence=conf,
                       rationale=str(out.get("rationale", ""))[:600], evidence=ev)

    def triage(self, lf: LabelledFinding) -> TriageRecord:
        f = lf.finding
        rec = TriageRecord(system=self.name, provider=self.provider.name,
                           model=self.provider.model, truth=lf.truth,
                           verdict=Verdict(finding_id=f.finding_id, label=Label.UNSURE,
                                           confidence=0.0, rationale="budget exhausted"))
        # the agent starts with a window around the alert, not the whole file
        snippet = read_source(self.root, f, context=15)
        messages = [{"role": "user", "content": alert_block(f, snippet)
                     + f"\n\nBudget remaining: {self.budget}"}]
        spent, t0 = 0, time.time()
        try:
            for turn in range(1, self.max_turns + 1):
                c = self.provider.complete(self.system, messages)
                rec.llm_calls += 1
                rec.input_tokens += c.input_tokens
                rec.output_tokens += c.output_tokens
                messages.append({"role": "assistant", "content": c.text})
                try:
                    out = extract_json(c.text)
                except ValueError as e:
                    obs = f"ERROR: {e}. Reply with one JSON object."
                    rec.steps.append(StepRecord(step=turn, action="invalid", observation=obs))
                    messages.append({"role": "user", "content": obs})
                    continue
                action = out.get("action", "")
                if action == "final":
                    rec.verdict = self._finalise(f, out)
                    rec.steps.append(StepRecord(step=turn, thought=str(out.get("thought", "")),
                                                action="final"))
                    break
                args = out.get("args", {}) or {}
                try:
                    obs, cost = self.tools.call(action, args)
                except (ToolError, TypeError) as e:
                    obs, cost = f"TOOL ERROR: {e}", 0
                spent += cost
                rec.steps.append(StepRecord(step=turn, thought=str(out.get("thought", ""))[:400],
                                            action=action, args=args,
                                            observation=obs[:400], cost_units=cost))
                left = self.budget - spent
                note = (f"\n\nBudget remaining: {left}" if left > 0 else
                        "\n\nBudget exhausted: give your final verdict now.")
                messages.append({"role": "user", "content": f"Observation:\n{obs}{note}"})
            else:
                rec.verdict = self._finalise(f, {"label": "UNSURE", "confidence": 0.0,
                                                 "rationale": "turn limit reached"})
        except Exception as e:
            rec.error = f"{type(e).__name__}: {e}"
        rec.latency_s = time.time() - t0
        return rec
