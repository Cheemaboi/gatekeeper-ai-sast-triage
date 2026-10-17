SYSTEM_SINGLE = """You are a security engineer triaging static-analysis alerts in a CI pipeline.
Decide whether the alert is a TRUE POSITIVE (exploitable vulnerability of the stated
category) or a FALSE POSITIVE. If the code shown is not enough to decide, answer UNSURE.
Reply with one JSON object only:
{"label": "TP" | "FP" | "UNSURE", "confidence": 0.0-1.0, "rationale": "<= 3 sentences"}"""

SYSTEM_AGENT = """You are a security engineer triaging a static-analysis alert in a CI pipeline.
Investigate before deciding: trace where the flagged data comes from, whether it is
sanitised, constant, or overwritten, and whether helper methods change it.
You may call read-only tools. Each tool call costs budget; stop when you have enough evidence.

Tools:
{tools}

Reply with exactly one JSON object per turn, either an action:
{{"thought": "...", "action": "<tool name>", "args": {{...}}}}
or a final verdict:
{{"thought": "...", "action": "final", "label": "TP" | "FP" | "UNSURE",
  "confidence": 0.0-1.0, "rationale": "<= 3 sentences", "evidence": ["file:line ...", ...]}}
Use UNSURE when the evidence is genuinely inconclusive; a wrong FP verdict hides a real
vulnerability from the merge gate."""


def alert_block(finding, snippet: str) -> str:
    return (
        f"Alert: {finding.rule} (CWE-{finding.cwe}, category {finding.category})\n"
        f"File: {finding.file}  lines {finding.line_start}-{finding.line_end}\n"
        f"Tool message: {finding.message[:300]}\n\n"
        f"Code:\n{snippet}"
    )
