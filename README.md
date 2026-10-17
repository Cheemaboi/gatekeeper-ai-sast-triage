# GateKeeper AI SAST Triage

This is our Phase 1 project for checking whether an LLM can help developers review
false alarms from Java static-analysis tools in a CI/CD pipeline for.

## What is included

- OWASP Benchmark data and a small labelled evaluation set.
- B0: the normal FindSecBugs result.
- B1: one model call for each alert.
- An agent that can read files and search the repository before deciding.
- A simple CI gate: real vulnerabilities block, false alarms are suppressed, and
  uncertain cases go to a human.
- Tests suite for the parser, metrics, tools, agent and gate.

## Install and test

```bash
pip install -r requirements.txt
pytest -q
```

The OWASP Benchmark is downloaded separately because it is not included in this
repository:

```bash
bash scripts/fetch_benchmark.sh
```

## Run the baselines

```bash
python -m sastriage.cli baseline --all-tools
python -m sastriage.cli make-eval-set
```

To run B1 or the agent, set an OpenAI-compatible model first. For example, Ollama
uses `http://localhost:11434/v1` and hosted providers use their own API base URL.

```bash
set OPENAI_BASE_URL=http://localhost:11434/v1
set OPENAI_API_KEY=ollama
set TRIAGE_MODEL=qwen2.5-coder:7b

python -m sastriage.cli triage --system single_call --provider openai --limit 50
python -m sastriage.cli triage --system agent --provider openai --limit 50 --budget 4
```

Each run writes a JSONL file and a metrics file in `results/`.

## Initial results

FindSecBugs produced 2,113 alerts on OWASP Benchmark v1.2. The measured alert
precision was 0.648, with average TPR 0.968 and average FPR 0.609.

The repository also contains the Phase 1 pilot outputs:

- `results/b1_openrouter_50.metrics.json`
- `results/agent_gemini_50.metrics.json`

## Folder guide

```text
sastriage/   project code
tests/       automated tests
data/        evaluation data
results/     baseline and pilot results
docs/        architecture notes
```

OWASP Benchmark is downloaded separately under its own licence and is not
redistributed in this repository.
