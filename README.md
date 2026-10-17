# sast-triage: agentic triage of SAST alerts for CI/CD security gates

Static analysis (SAST) in a CI pipeline either blocks too many merges with false alarms or
gets ignored. This repo is a technical foundation for triaging SAST alerts with an LLM agent
before they reach the merge gate, and for measuring whether that is safe.

## What runs today

| Component | File | Status |
|---|---|---|
| Data pipeline: OWASP Benchmark ground truth + SpotBugs/FindSecBugs reports -> labelled alerts | `sastriage/data.py` | working |
| Structured contracts (Finding, Verdict, TriageRecord, GateDecision) | `sastriage/contracts.py` | working |
| B0 baseline: raw SAST, scored per category (TPR/FPR/Youden) | `cli.py baseline` | working, results in `results/BASELINE.md` |
| Evaluation set: 209 stratified alerts (121 real, 88 false), seed 42 | `cli.py make-eval-set` | working, `data/eval_set.jsonl` |
| B1 baseline: one LLM call per alert, no tools | `triage/single_call.py` | working, needs an API key to produce results |
| Proposed system skeleton: budgeted ReAct agent with read-only tools, abstention, traces | `triage/agent.py`, `tools.py` | working, needs an API key to produce results |
| CI gate: TP blocks, UNSURE goes to a human, FP suppressed | `gate.py` | working |
| Providers: Anthropic, any OpenAI-compatible endpoint (OpenAI, Groq, local Ollama), scripted | `providers.py` | working |
| Tests (11) covering parsing, labelling, calibration metrics, tool sandboxing, both triage loops, gate | `tests/` | passing |

## Run it

```bash
pip install -r requirements.txt
bash scripts/fetch_benchmark.sh                     # clones OWASP Benchmark (GPL-2.0) into data/external/
pytest -q                                           # 11 tests, no network or API key needed

python -m sastriage.cli baseline --all-tools        # B0: raw SAST scorecard -> results/
python -m sastriage.cli make-eval-set               # 209-alert evaluation set -> data/eval_set.jsonl

# B1 and the agent need a model. Anthropic:
export ANTHROPIC_API_KEY=...
python -m sastriage.cli triage --system single_call --provider anthropic --limit 50
python -m sastriage.cli triage --system agent       --provider anthropic --limit 50 --budget 8

# ...or a free local model through Ollama's OpenAI-compatible API:
export OPENAI_BASE_URL=http://localhost:11434/v1 TRIAGE_MODEL=qwen2.5-coder:7b
python -m sastriage.cli triage --system agent --provider openai --limit 50

python -m sastriage.cli gate --run results/agent_<model>.jsonl   # exit code 1 = merge blocked
```

Each triage run writes one JSON line per alert (verdict, full step trace, tokens, latency)
and a `.metrics.json` with precision, real-vulnerability retention, false-alarm suppression,
coverage, confidence calibration, evidence coverage, abstention, LLM calls and tool steps.

## Initial results (B0)

FindSecBugs v1.4.6 on OWASP Benchmark v1.2: 2,113 alerts, alert precision 0.648, average
TPR 0.968, average FPR 0.609, Youden 0.360. In the injection categories about half of all
alerts are false. Full table: `results/BASELINE.md`.

## Ablation switches already in the agent

`--budget` (tool-cost budget), `--min-confidence` (low-confidence verdicts become UNSURE),
`--no-abstain` (UNSURE coerced to the safe TP), and comparing `agent` with `single_call`
(tools on/off).

## Layout

```
sastriage/   contracts.py  data.py  tools.py  providers.py  metrics.py  gate.py  cli.py
             triage/  single_call.py  agent.py  prompts.py
tests/       test_pipeline.py + fixtures/mini_bench (tiny synthetic benchmark)
results/     baseline_raw_sast.json  BASELINE.md
data/        eval_set.jsonl   (external/ is fetched, git-ignored)
docs/        architecture.md (Mermaid diagram)
.github/     tests.yml (CI for this repo)  sast-gate.example.yml (how a project would use it)
```

## Data licence

OWASP Benchmark is GPL-2.0 and is downloaded, not redistributed. `data/eval_set.jsonl`
contains alert metadata and labels only, no benchmark source code.
