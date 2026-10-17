# GitHub authorship and submission handoff

The repository intentionally has no commits. Do not create three commits with invented authors: each member should make a real contribution while signed in to their own GitHub account.

## Suggested ownership

1. **Group head (22I-1319):** commit the data pipeline, contracts, raw-SAST baseline and initial README.
2. **Agent/evaluation member:** pull the first commit, then commit the single-call baseline, agent, tools, gate, metrics and tests.
3. **Documentation/CI member:** pull the first two commits, then commit the architecture, workflow files, evidence screenshots and report source.

Each person should configure their real identity before committing:

```bash
git config user.name "Real Name"
git config user.email "verified-email@example.com"
```

After all three contributions are pushed, the group head should make the repository public, add the supervisor as a collaborator if required, copy the public URL into the report, rebuild the PDF, and submit `Phase1_G3-10_22I-1319.pdf`.

## Model run required before submission

The planned local model is `qwen2.5-coder:7b` through Ollama. After Ollama is installed and the model is pulled:

```powershell
$env:OPENAI_BASE_URL = "http://localhost:11434/v1"
$env:OPENAI_API_KEY = "ollama"
$env:TRIAGE_MODEL = "qwen2.5-coder:7b"
python -m sastriage.cli triage --system single_call --provider openai --limit 50 --out results/b1_qwen_50.jsonl
python -m sastriage.cli triage --system agent --provider openai --limit 50 --budget 8 --min-confidence 0.70 --out results/agent_qwen_50.jsonl
```

Do not report these results until both commands finish and their `.metrics.json` files exist.
