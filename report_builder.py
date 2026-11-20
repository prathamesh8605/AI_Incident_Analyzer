"""
report_builder.py
-----------------
Step 4: turn the analysis into a short incident summary that a support
engineer can paste into Slack, email or a ticket.
"""


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- (none)"


def build_incident_summary(analysis: dict, stats: dict, source_name: str = "pasted logs") -> str:
    """Return a clear, copy-paste-ready incident summary in plain text."""
    escalation = analysis["escalation"]
    escalate_line = "YES - " if escalation.get("needed") else "Not yet - "
    escalate_line += f'{escalation.get("when", "")} (Contact: {escalation.get("to", "n/a")})'

    first, last = stats["time_range"]

    return f"""INCIDENT SUMMARY
================
Source        : {source_name}
Time window   : {first} to {last}
Severity      : {analysis["severity"].upper()}
Analysis type : {"AI-assisted" if analysis.get("source") == "ai" else "Rule-based"}

WHAT HAPPENED
{analysis["summary"]}

KEY ERRORS
{_bullets(analysis["key_errors"])}

LIKELY CAUSE (not confirmed)
{analysis["likely_cause"]}

EVIDENCE FROM LOGS
{_bullets(analysis["evidence"])}

ASSUMPTIONS (not proven by the logs)
{_bullets(analysis["assumptions"])}

WHY THIS SEVERITY
{analysis["severity_reason"]}

NEXT STEPS (check in this order)
{chr(10).join(f"{i}. {step}" for i, step in enumerate(analysis["troubleshooting_steps"], start=1))}

ESCALATION
{escalate_line}
"""
