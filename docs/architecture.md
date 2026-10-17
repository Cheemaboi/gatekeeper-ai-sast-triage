# Architecture

```mermaid
flowchart LR
  subgraph CI["CI/CD pipeline (pull request)"]
    PR[Code change] --> SAST[SAST tool<br/>SpotBugs + FindSecBugs]
  end
  SAST -->|XML report| ING[Ingest + normalise<br/>data.py -> Finding contract]

  ING --> B0[B0 raw SAST<br/>every alert blocks]
  ING --> B1[B1 single LLM call<br/>alert + file, no tools]
  ING --> AG

  subgraph AG["Proposed: evidence-grounded triage agent (agent.py)"]
    direction TB
    PL[LLM reasoner<br/>ReAct loop] -->|action| TL["G1: Evidence-grounded context<br/>read_file / grep / find_definition"]
    TL -->|observation| PL
    PL --> ST[("G3: Resource-aware state<br/>steps, budget spent,<br/>tokens + evidence")]
    ST --> STOP["Budget policy + early stop"]
    PL --> CAL["G2: Calibrated abstention<br/>low confidence -> UNSURE"]
  end

  REPO[(Repository source)] --- TL
  B1 --> V[Verdict contract<br/>TP / FP / UNSURE + evidence]
  CAL --> V
  V --> GATE[CI gate gate.py<br/>TP blocks, UNSURE -> human,<br/>FP suppressed with rationale]
  GATE --> HUM[Human reviewer]
  V --> EVAL[Evaluation metrics.py<br/>quality, calibration, evidence,<br/>cost and latency]
  B0 --> EVAL
```

The three selected gaps are marked directly in the proposed system:

- **G1**: a verdict must be supported by repository evidence gathered with read-only tools.
- **G2**: uncertain alerts are not silently suppressed; the agent abstains and routes them to a human.
- **G3**: tool use and model calls are controlled by an explicit budget and recorded for audit and cost analysis.

The two baselines make the research comparison explicit. B0 blocks on every raw SAST alert, while B1 makes one model call with no tools. The proposed path adds adaptive tool use, evidence, abstention and budget-aware stopping before the same CI gate.
