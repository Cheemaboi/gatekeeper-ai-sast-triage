"""Evaluation metrics for SAST alerts and triage systems.

Two levels are reported:
  * detection level (OWASP-scorecard style): TPR, FPR and Youden index per category
    over all test cases -- used for the raw-SAST baseline;
  * triage level: how well a system separates true from false alerts, how many
    alerts it removes, how many real vulnerabilities it wrongly suppresses,
    how often it abstains, and what it costs.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, median

from .contracts import GroundTruth, Label, LabelledFinding, TriageRecord


def _safe(n: float, d: float) -> float:
    return n / d if d else 0.0


def detection_scorecard(flagged: set[tuple[str, str]],
                        truth: dict[str, GroundTruth]) -> dict:
    """flagged = {(test_case, category)} the tool reported."""
    per = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    for name, gt in truth.items():
        hit = (name, gt.category) in flagged
        c = per[gt.category]
        if gt.is_vulnerable:
            c["tp" if hit else "fn"] += 1
        else:
            c["fp" if hit else "tn"] += 1
    rows = {}
    for cat, c in sorted(per.items()):
        tpr = _safe(c["tp"], c["tp"] + c["fn"])
        fpr = _safe(c["fp"], c["fp"] + c["tn"])
        prec = _safe(c["tp"], c["tp"] + c["fp"])
        rows[cat] = {**c, "tpr": tpr, "fpr": fpr, "precision": prec, "youden": tpr - fpr}
    overall = {
        "avg_tpr": mean(r["tpr"] for r in rows.values()),
        "avg_fpr": mean(r["fpr"] for r in rows.values()),
        "avg_youden": mean(r["youden"] for r in rows.values()),
        "alerts": sum(r["tp"] + r["fp"] for r in rows.values()),
        "alert_precision": _safe(sum(r["tp"] for r in rows.values()),
                                 sum(r["tp"] + r["fp"] for r in rows.values())),
    }
    return {"per_category": rows, "overall": overall}


def triage_metrics(records: list[TriageRecord]) -> dict:
    """Metrics for a triage system over labelled alerts.

    Positive class = "real vulnerability". A verdict of FP suppresses the alert;
    TP keeps it; UNSURE routes it to a human (kept, but counted separately).
    """
    rs = [r for r in records if r.truth is not None and r.error is None]
    tp = sum(1 for r in rs if r.truth and r.verdict.label == Label.TRUE_POSITIVE)
    fn = sum(1 for r in rs if r.truth and r.verdict.label == Label.FALSE_POSITIVE)
    fp = sum(1 for r in rs if not r.truth and r.verdict.label == Label.TRUE_POSITIVE)
    tn = sum(1 for r in rs if not r.truth and r.verdict.label == Label.FALSE_POSITIVE)
    unsure_real = sum(1 for r in rs if r.truth and r.verdict.label == Label.UNSURE)
    unsure_fake = sum(1 for r in rs if not r.truth and r.verdict.label == Label.UNSURE)
    real = tp + fn + unsure_real
    fake = fp + tn + unsure_fake
    decided = tp + fn + fp + tn
    lat = [r.latency_s for r in rs]

    # Confidence is the model's confidence in its chosen TP/FP label.  Calibration
    # is therefore evaluated as prediction-correctness calibration and excludes
    # abstentions, whose meaning is deliberately "send to a human".
    decided_records = [r for r in rs if r.verdict.label != Label.UNSURE]
    calibration = []
    for r in decided_records:
        correct = ((r.truth is True and r.verdict.label == Label.TRUE_POSITIVE) or
                   (r.truth is False and r.verdict.label == Label.FALSE_POSITIVE))
        calibration.append((r.verdict.confidence, 1.0 if correct else 0.0))
    brier = mean((confidence - correct) ** 2
                 for confidence, correct in calibration) if calibration else 0.0
    ece = 0.0
    if calibration:
        bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for confidence, correct in calibration:
            bins[min(int(confidence * 10), 9)].append((confidence, correct))
        ece = sum((len(items) / len(calibration)) *
                  abs(mean(x[0] for x in items) - mean(x[1] for x in items))
                  for items in bins.values())

    evidence_counts = [len(r.verdict.evidence) for r in rs]
    return {
        "n": len(rs),
        "errors": sum(1 for r in records if r.error),
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
                      "unsure_real": unsure_real, "unsure_fake": unsure_fake},
        # decided-only quality
        "precision": _safe(tp, tp + fp),
        "recall_decided": _safe(tp, tp + fn),
        "f1": _safe(2 * tp, 2 * tp + fp + fn),
        "accuracy_decided": _safe(tp + tn, decided),
        "coverage": _safe(decided, len(rs)),
        "selective_error": _safe(fp + fn, decided),
        "confidence_brier": brier,
        "confidence_ece_10bin": ece,
        # what matters for a CI gate
        "real_vuln_retention": _safe(tp + unsure_real, real),   # 1 - missed vulns
        "missed_real_vulns": fn,
        "false_alarm_suppression": _safe(tn, fake),
        "abstention_rate": _safe(unsure_real + unsure_fake, len(rs)),
        "human_review_load": _safe(unsure_real + unsure_fake, len(rs)),
        "alerts_remaining": tp + fp + unsure_real + unsure_fake,
        # evidence / auditability
        "evidence_coverage": _safe(sum(1 for n in evidence_counts if n > 0), len(rs)),
        "evidence_items_mean": mean(evidence_counts) if evidence_counts else 0,
        # cost / efficiency
        "llm_calls_mean": mean(r.llm_calls for r in rs) if rs else 0,
        "tool_steps_mean": mean(len(r.steps) for r in rs) if rs else 0,
        "tokens_in_total": sum(r.input_tokens for r in rs),
        "tokens_out_total": sum(r.output_tokens for r in rs),
        "latency_median_s": median(lat) if lat else 0,
    }


def raw_sast_as_triage(labelled: list[LabelledFinding]) -> dict:
    """The no-triage baseline: every alert is kept as a true positive."""
    tp = sum(1 for lf in labelled if lf.truth)
    fp = len(labelled) - tp
    return {"n": len(labelled), "precision": _safe(tp, len(labelled)),
            "real_vuln_retention": 1.0 if tp else 0.0,
            "false_alarm_suppression": 0.0, "alerts_remaining": len(labelled),
            "confusion": {"tp": tp, "fp": fp}}
