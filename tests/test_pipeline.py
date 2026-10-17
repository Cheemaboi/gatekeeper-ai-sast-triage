import json
from pathlib import Path

import pytest

from sastriage.contracts import Label, LabelledFinding, TriageRecord, Verdict
from sastriage.data import (dedupe_per_test, label_findings, load_ground_truth,
                            parse_spotbugs_xml, read_source)
from sastriage.gate import decide
from sastriage.metrics import detection_scorecard, triage_metrics
from sastriage.providers import ScriptedProvider, extract_json
from sastriage.tools import RepoTools, ToolError
from sastriage.triage import AgentTriage, SingleCallTriage

BENCH = Path(__file__).parent / "fixtures" / "mini_bench"
REPORT = BENCH / "results" / "Benchmark_1.2-findsecbugs-test.xml"


@pytest.fixture
def labelled():
    truth = load_ground_truth(BENCH)
    return label_findings(dedupe_per_test(parse_spotbugs_xml(REPORT, "fsb")), truth)


def test_parser_keeps_only_in_scope_testcode_alerts():
    fs = parse_spotbugs_xml(REPORT, "fsb")
    # COOKIE_USAGE (no CWE) and the helper-class alert are dropped
    assert [f.rule for f in fs] == ["SQL_INJECTION_JDBC", "SQL_INJECTION_JDBC", "DES_USAGE"]
    assert fs[2].cwe == 327 and fs[2].category == "crypto"   # 326 -> 327 normalisation


def test_labels_follow_ground_truth_and_category(labelled):
    by_test = {lf.finding.test_case: lf.truth for lf in labelled}
    assert by_test == {"BenchmarkTest00001": True,    # real sqli
                       "BenchmarkTest00002": False,   # sqli flagged but not vulnerable
                       "BenchmarkTest00003": False}   # wrong category for this test


def test_detection_scorecard():
    truth = load_ground_truth(BENCH)
    sc = detection_scorecard({("BenchmarkTest00001", "sqli"), ("BenchmarkTest00002", "sqli")}, truth)
    sqli = sc["per_category"]["sqli"]
    assert (sqli["tp"], sqli["fp"], sqli["tpr"], sqli["fpr"]) == (1, 1, 1.0, 1.0)
    assert sc["per_category"]["xss"]["tn"] == 1


def test_tools_are_sandboxed():
    t = RepoTools(BENCH)
    assert "safe_constant" in t.find_definition("choose")
    assert "BenchmarkTest00002" in t.grep(r"Helper\.choose")
    with pytest.raises(ToolError):
        t.read_file("../../../../etc/passwd")
    with pytest.raises(ToolError):
        t.call("delete_file", {})


def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}


def test_single_call_baseline_end_to_end(labelled):
    lf = labelled[0]
    p = ScriptedProvider(['{"label": "TP", "confidence": 0.9, "rationale": "tainted"}'])
    r = SingleCallTriage(p, BENCH).triage(lf)
    assert r.error is None and r.verdict.label == Label.TRUE_POSITIVE and r.llm_calls == 1
    assert "request.getParameter" in p.calls[0][0]["content"]


def test_agent_uses_tools_then_decides(labelled):
    lf = next(x for x in labelled if x.finding.test_case == "BenchmarkTest00002")
    p = ScriptedProvider([
        '{"thought": "where does bar come from", "action": "find_definition", "args": {"symbol": "choose"}}',
        '{"thought": "constant", "action": "final", "label": "FP", "confidence": 0.85, '
        '"rationale": "Helper.choose returns a constant", "evidence": ["Helper.java:3"]}',
    ])
    r = AgentTriage(p, BENCH, budget=4).triage(lf)
    assert r.error is None
    assert r.verdict.label == Label.FALSE_POSITIVE
    assert [s.action for s in r.steps] == ["find_definition", "final"]
    assert r.steps[0].cost_units == 2
    assert "safe_constant" in p.calls[1][-1]["content"]      # observation fed back


def test_agent_low_confidence_becomes_unsure_and_no_abstain_fails_safe(labelled):
    lf = labelled[1]
    final = '{"action": "final", "label": "FP", "confidence": 0.3, "rationale": "?"}'
    r = AgentTriage(ScriptedProvider([final]), BENCH, min_confidence=0.6).triage(lf)
    assert r.verdict.label == Label.UNSURE
    r2 = AgentTriage(ScriptedProvider([final]), BENCH, min_confidence=0.6,
                     allow_abstain=False).triage(lf)
    assert r2.verdict.label == Label.TRUE_POSITIVE


def test_agent_recovers_from_bad_output_and_turn_limit(labelled):
    p = ScriptedProvider(["not json"] + ['{"action": "grep", "args": {"pattern": "x"}}'] * 3)
    r = AgentTriage(p, BENCH, max_turns=4).triage(labelled[0])
    assert r.steps[0].action == "invalid"
    assert r.verdict.label == Label.UNSURE


def test_triage_metrics_and_gate():
    def rec(fid, truth, label):
        return TriageRecord(system="x", provider="p", model="m", truth=truth,
                            verdict=Verdict(finding_id=fid, label=label, confidence=0.9,
                                            rationale=""))
    recs = [rec("a", True, Label.TRUE_POSITIVE), rec("b", True, Label.FALSE_POSITIVE),
            rec("c", False, Label.FALSE_POSITIVE), rec("d", False, Label.UNSURE)]
    m = triage_metrics(recs)
    assert m["missed_real_vulns"] == 1
    assert m["real_vuln_retention"] == 0.5
    assert m["false_alarm_suppression"] == 0.5
    assert m["abstention_rate"] == 0.25
    assert m["coverage"] == 0.75
    assert m["selective_error"] == 1 / 3
    assert round(m["confidence_brier"], 3) == 0.277
    assert round(m["confidence_ece_10bin"], 3) == 0.233
    assert m["evidence_coverage"] == 0.0
    g = decide([r.verdict for r in recs])
    assert not g.passed and g.blocking == ["a"] and g.needs_review == ["d"]
    assert decide([recs[2].verdict]).passed


def test_calibration_metrics_are_zero_for_empty_or_abstained_runs():
    assert triage_metrics([])["confidence_brier"] == 0.0
    r = TriageRecord(system="x", provider="p", model="m", truth=True,
                     verdict=Verdict(finding_id="a", label=Label.UNSURE,
                                     confidence=0.4, rationale="needs review"))
    m = triage_metrics([r])
    assert m["coverage"] == 0.0
    assert m["confidence_ece_10bin"] == 0.0
