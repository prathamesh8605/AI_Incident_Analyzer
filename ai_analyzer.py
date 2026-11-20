"""
ai_analyzer.py
--------------
Step 3: ask an AI model (Claude) to read the evidence and write the analysis.

How we keep the AI honest:
  * We send it FACTS first (counts, times, services) plus the most relevant log lines.
  * We tell it to separate "evidence" (seen in the logs) from "assumptions" (guesses).
  * We ask for strict JSON so the answer is easy to check and display.
  * We check the answer afterwards. If it is broken, we fall back to the rules.
"""

import json
import os

from log_parser import LogEntry, mask_sensitive_data
from rules_engine import SEVERITY_ORDER, build_rule_based_analysis

# You can change the model without touching the code: set ANTHROPIC_MODEL.
DEFAULT_MODEL = "claude-sonnet-5-5"

# Never send huge logs to the model. We send the most useful lines only.
MAX_LOG_LINES_SENT = 150


SYSTEM_PROMPT = """You are a senior technology operations engineer helping a support engineer
investigate an application incident from logs.

Rules you must follow:
1. Use ONLY the information in the logs and statistics given. Do not invent services, numbers or events.
2. Clearly separate EVIDENCE (directly visible in the logs, mention line numbers) from ASSUMPTIONS (your reasoning or guesses).
3. Never state a guess as a confirmed fact. Use words like "likely" or "possible" for causes.
4. Severity must be one of: Critical, High, Medium, Low. Explain why in plain language.
5. Troubleshooting steps must be practical, ordered by what to check first, and relevant to this evidence.
6. Say when escalation is needed and to whom.
7. Reply with JSON only. No extra text, no markdown fences.

Use exactly this JSON shape:
{
  "summary": "2-3 sentence plain-English summary",
  "key_errors": ["short description of each important error with counts"],
  "patterns": ["repeated failures or timing patterns you can see"],
  "likely_cause": "most likely cause, worded as a possibility",
  "evidence": ["facts from the logs that support it, with line numbers"],
  "assumptions": ["things you are assuming that the logs do not prove"],
  "severity": "Critical | High | Medium | Low",
  "severity_reason": "why this severity, including likely impact",
  "troubleshooting_steps": ["step 1", "step 2"],
  "escalation": {"needed": true, "when": "when to escalate", "to": "who to escalate to"}
}"""


# ---------- Choose which log lines to send ----------

def pick_relevant_lines(entries: list[LogEntry]) -> list[LogEntry]:
    """
    Keep problem lines (FATAL/ERROR/WARN) first, then fill with normal lines
    so the model also sees what 'healthy' looked like. Order stays chronological.
    """
    problems = [e for e in entries if e.level in ("FATAL", "ERROR", "WARN")]
    others = [e for e in entries if e.level not in ("FATAL", "ERROR", "WARN")]

    chosen = problems[:MAX_LOG_LINES_SENT]
    room_left = MAX_LOG_LINES_SENT - len(chosen)
    if room_left > 0:
        chosen += others[:room_left]

    return sorted(chosen, key=lambda e: e.line_number)


def build_user_message(entries: list[LogEntry], stats: dict) -> str:
    """Write the message we send to the AI: facts first, then log lines."""
    lines = pick_relevant_lines(entries)
    log_text = "\n".join(f"[line {e.line_number}] {e.raw.strip()}" for e in lines)

    facts = {
        "total_lines": stats["total_lines"],
        "level_counts": stats["level_counts"],
        "time_range": stats["time_range"],
        "services_with_errors": stats["services_with_errors"],
        "top_repeated_errors": stats["repeated_errors"][:8],
        "detected_failure_types": [
            {k: f[k] for k in ("name", "count", "first_seen", "last_seen", "services")}
            for f in stats["findings"]
        ],
        "rule_based_severity_suggestion": stats["rules_severity"],
    }

    message = (
        "STATISTICS (computed by code, these are reliable):\n"
        + json.dumps(facts, indent=2)
        + "\n\nLOG LINES (sensitive data already masked):\n"
        + log_text
    )
    # Mask again as a safety net, in case anything slipped through.
    return mask_sensitive_data(message)


# ---------- Read and check the AI's answer ----------

REQUIRED_KEYS = ["summary", "key_errors", "patterns", "likely_cause", "evidence",
                 "assumptions", "severity", "severity_reason", "troubleshooting_steps", "escalation"]


def parse_ai_response(text: str) -> dict:
    """Turn the AI's text into a Python dictionary and check it looks right."""
    cleaned = text.strip()

    # Some models wrap JSON in ```json ... ``` even when told not to.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"AI answer is missing: {missing}")

    # Severity must be one of the four allowed words (any capitalisation).
    severity = str(data["severity"]).strip().capitalize()
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"Unexpected severity: {data['severity']}")
    data["severity"] = severity

    if not isinstance(data["escalation"], dict):
        raise ValueError("escalation must be an object")

    return data


# ---------- The main entry point ----------

def analyze_with_ai(entries: list[LogEntry], stats: dict, client=None) -> dict:
    """
    Try the AI. If anything goes wrong (no key, no internet, bad answer),
    quietly use the rule-based analysis instead and say why.

    `client` can be passed in for testing, so tests never call the real API.
    """
    fallback = build_rule_based_analysis(stats)

    if client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            fallback["note"] = "No ANTHROPIC_API_KEY found, so the rule-based analysis was used."
            return fallback
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception as error:  # library missing or setup problem
            fallback["note"] = f"Could not start the AI client ({error}). Rule-based analysis used."
            return fallback

    try:
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            max_tokens=1800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(entries, stats)}],
        )
        answer = parse_ai_response(response.content[0].text)
    except Exception as error:
        fallback["note"] = f"AI analysis failed ({error}). Rule-based analysis used instead."
        return fallback

    answer["source"] = "ai"
    answer["rules_severity"] = stats["rules_severity"]  # kept so humans can compare
    return answer
