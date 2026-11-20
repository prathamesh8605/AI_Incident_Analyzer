"""
analyzer.py
-----------
One simple function that runs the whole pipeline, so the web page and the
tests can both use it:

    raw text  ->  parse  ->  mask secrets  ->  rules  ->  AI (or fallback)  ->  report
"""

from log_parser import parse_logs, mask_sensitive_data
from rules_engine import analyze_entries
from ai_analyzer import analyze_with_ai
from rules_engine import build_rule_based_analysis
from report_builder import build_incident_summary


def run_analysis(log_text: str, use_ai: bool = True, source_name: str = "pasted logs", client=None) -> dict:
    """Run every step and return everything the interface needs to show."""
    # Hide emails, card numbers and tokens straight away.
    safe_text = mask_sensitive_data(log_text)

    entries = parse_logs(safe_text)
    if not entries:
        raise ValueError("No log lines found. Please paste or upload some logs.")

    stats = analyze_entries(entries)

    if use_ai:
        analysis = analyze_with_ai(entries, stats, client=client)
    else:
        analysis = build_rule_based_analysis(stats)
        analysis["note"] = "AI was switched off, so the rule-based analysis was used."

    summary_text = build_incident_summary(analysis, stats, source_name)

    return {"entries": entries, "stats": stats, "analysis": analysis, "summary_text": summary_text}
