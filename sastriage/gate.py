"""CI/CD merge gate: turns triage verdicts into a pass/fail decision.

Policy (conservative by design):
  * TP              -> blocks the merge
  * UNSURE          -> does not block, but is routed to a human reviewer
                       (set block_on_unsure=True for high-assurance branches)
  * FP              -> suppressed, with the rationale kept for audit
"""
from __future__ import annotations

from .contracts import GateDecision, Label, Verdict


def decide(verdicts: list[Verdict], block_on_unsure: bool = False) -> GateDecision:
    blocking = [v.finding_id for v in verdicts if v.label == Label.TRUE_POSITIVE]
    review = [v.finding_id for v in verdicts if v.label == Label.UNSURE]
    suppressed = [v.finding_id for v in verdicts if v.label == Label.FALSE_POSITIVE]
    if block_on_unsure:
        blocking += review
    passed = not blocking
    summary = (f"{len(blocking)} blocking, {len(review)} need review, "
               f"{len(suppressed)} suppressed as false positives")
    return GateDecision(passed=passed, blocking=blocking, needs_review=review,
                        suppressed=suppressed, summary=summary)
