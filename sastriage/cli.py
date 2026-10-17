"""Command-line entry point.

  python -m sastriage.cli baseline       score raw SAST output against ground truth
  python -m sastriage.cli make-eval-set  build the stratified evaluation set of alerts
  python -m sastriage.cli triage         run a triage system (single_call | agent)
  python -m sastriage.cli gate           apply the CI gate to a triage run
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from .contracts import LabelledFinding, TriageRecord
from .data import dedupe_per_test, label_findings, load_ground_truth, parse_spotbugs_xml
from .gate import decide
from .metrics import detection_scorecard, triage_metrics

DEFAULT_BENCH = Path("data/external/BenchmarkJava")
DEFAULT_REPORT = "results/Benchmark_1.2-findsecbugs-v1.4.6-122.xml"


def _labelled(bench: Path, report: str) -> list[LabelledFinding]:
    truth = load_ground_truth(bench)
    tool = Path(report).stem.replace("Benchmark_1.2-", "")
    return label_findings(dedupe_per_test(parse_spotbugs_xml(bench / report, tool)), truth)


def cmd_baseline(a) -> None:
    truth = load_ground_truth(a.bench)
    reports = sorted((a.bench / "results").glob("Benchmark_1.2-find*bugs*.xml")) \
        if a.all_tools else [a.bench / a.report]
    table = {}
    for rp in reports:
        tool = rp.stem.replace("Benchmark_1.2-", "")
        findings = dedupe_per_test(parse_spotbugs_xml(rp, tool))
        flagged = {(f.test_case, f.category) for f in findings}
        table[tool] = detection_scorecard(flagged, truth)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=2))
    for tool, sc in table.items():
        o = sc["overall"]
        print(f"{tool:32s} alerts={o['alerts']:5d}  alert-precision={o['alert_precision']:.3f}  "
              f"TPR={o['avg_tpr']:.3f}  FPR={o['avg_fpr']:.3f}  Youden={o['avg_youden']:.3f}")
    print(f"\nwrote {out}")


def cmd_make_eval_set(a) -> None:
    lfs = _labelled(a.bench, a.report)
    buckets = defaultdict(list)
    for lf in lfs:
        buckets[(lf.finding.category, lf.truth)].append(lf)
    rng = random.Random(a.seed)
    per = max(1, a.n // len(buckets))
    chosen = []
    for key in sorted(buckets, key=str):
        items = sorted(buckets[key], key=lambda x: x.finding.test_case)
        rng.shuffle(items)
        chosen += items[:per]
    rng.shuffle(chosen)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w") as fh:
        for lf in chosen:
            fh.write(lf.model_dump_json() + "\n")
    real = sum(lf.truth for lf in chosen)
    print(f"wrote {len(chosen)} alerts ({real} real, {len(chosen) - real} false) to {a.out}")


def cmd_triage(a) -> None:
    from .providers import make_provider
    from .triage import AgentTriage, SingleCallTriage
    provider = make_provider(a.provider, a.model)
    if a.system == "single_call":
        system = SingleCallTriage(provider, a.bench)
    else:
        system = AgentTriage(provider, a.bench, budget=a.budget,
                             allow_abstain=not a.no_abstain, min_confidence=a.min_confidence)
    items = [LabelledFinding.model_validate_json(l) for l in open(a.eval_set)][: a.limit]
    out = Path(a.out or f"results/{a.system}_{provider.model.replace('/', '_')}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with open(out, "w") as fh:
        for i, lf in enumerate(items, 1):
            r = system.triage(lf)
            records.append(r)
            fh.write(r.model_dump_json() + "\n")
            fh.flush()
            print(f"[{i}/{len(items)}] {lf.finding.test_case} {lf.finding.category:12s} "
                  f"truth={'TP' if lf.truth else 'FP'} -> {r.verdict.label.value}"
                  + (f"  ERROR {r.error}" if r.error else ""))
    m = triage_metrics(records)
    out.with_suffix(".metrics.json").write_text(json.dumps(m, indent=2))
    print(json.dumps({k: m[k] for k in ("n", "precision", "real_vuln_retention",
                                        "false_alarm_suppression", "abstention_rate",
                                        "llm_calls_mean")}, indent=2))


def cmd_gate(a) -> int:
    recs = [TriageRecord.model_validate_json(l) for l in open(a.run)]
    d = decide([r.verdict for r in recs if r.error is None], block_on_unsure=a.block_on_unsure)
    print(d.model_dump_json(indent=2))
    return 0 if d.passed else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sastriage")
    p.add_argument("--bench", type=Path, default=DEFAULT_BENCH)
    p.add_argument("--report", default=DEFAULT_REPORT)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("baseline")
    b.add_argument("--all-tools", action="store_true")
    b.add_argument("--out", default="results/baseline_raw_sast.json")

    e = sub.add_parser("make-eval-set")
    e.add_argument("--n", type=int, default=220)
    e.add_argument("--seed", type=int, default=42)
    e.add_argument("--out", default="data/eval_set.jsonl")

    t = sub.add_parser("triage")
    t.add_argument("--system", choices=["single_call", "agent"], required=True)
    t.add_argument("--provider", default="anthropic")
    t.add_argument("--model")
    t.add_argument("--eval-set", default="data/eval_set.jsonl")
    t.add_argument("--limit", type=int, default=50)
    t.add_argument("--budget", type=int, default=8)
    t.add_argument("--min-confidence", type=float, default=0.0)
    t.add_argument("--no-abstain", action="store_true")
    t.add_argument("--out")

    g = sub.add_parser("gate")
    g.add_argument("--run", required=True)
    g.add_argument("--block-on-unsure", action="store_true")

    a = p.parse_args(argv)
    if a.cmd == "gate":
        return cmd_gate(a)
    {"baseline": cmd_baseline, "make-eval-set": cmd_make_eval_set,
     "triage": cmd_triage}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
