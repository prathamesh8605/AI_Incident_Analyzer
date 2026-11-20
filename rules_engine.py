"""
rules_engine.py
---------------
Step 2: look at the parsed entries and find out WHAT happened using plain,
explainable rules (no AI here).

Why have rules when we also use AI?
  1. They give the AI hard facts (counts, times, services) so it does not guess.
  2. They act as a safety net: the tool still works with no internet or API key.
  3. They give us a second opinion to compare against the AI's severity.
"""

from collections import Counter, defaultdict

from log_parser import LogEntry, normalize_message


# ---------- Known failure types ----------
# Each rule says: "if the message contains these words, it is this kind of problem".

FAILURE_RULES = [
    {
        "name": "Timeout",
        "category": "timeout",
        "keywords": ["timeout", "timed out", "deadline exceeded"],
        "meaning": "A service waited too long for another service to answer.",
    },
    {
        "name": "Database connection failure",
        "category": "database",
        "keywords": ["connection pool", "could not acquire", "too many connections",
                     "database connection", "db connection", "connection refused to db",
                     "jdbc", "deadlock"],
        "meaning": "The application could not get or keep a connection to the database.",
    },
    {
        "name": "Memory pressure",
        "category": "memory",
        "keywords": ["outofmemory", "out of memory", "heap space", "oom", "memory usage"],
        "meaning": "The application is running out of memory.",
    },
    {
        "name": "Authentication failure",
        "category": "auth",
        "keywords": ["unauthorized", "401", "invalid token", "authentication failed", "login failed"],
        "meaning": "Requests are being rejected because identity checks failed.",
    },
    {
        "name": "Network / dependency unreachable",
        "category": "network",
        "keywords": ["connection refused", "connection reset", "unreachable", "dns", "no route to host",
                     "502", "503", "bad gateway", "service unavailable"],
        "meaning": "One service could not reach another service or an external dependency.",
    },
    {
        "name": "Disk / storage problem",
        "category": "disk",
        "keywords": ["no space left", "disk full", "read-only file system"],
        "meaning": "The server is running out of disk space or cannot write to disk.",
    },
]

# Services where a failure hurts customers or money directly.
BUSINESS_CRITICAL_WORDS = ["payment", "checkout", "order", "auth", "login", "billing", "transaction"]

# What a support engineer should check first for each failure type.
TROUBLESHOOTING_STEPS = {
    "database": [
        "Check database health: is it up, and what are its active connections vs. the configured maximum?",
        "Look for long-running or blocked queries and locks that may be holding connections.",
        "Review the application connection pool settings (max size, wait timeout) and recent changes to them.",
    ],
    "timeout": [
        "Find which downstream service or external API is slow, and check its status page or dashboard.",
        "Compare response times now against normal levels to see when the slowdown began.",
        "Check whether timeout and retry settings are causing extra load (retry storms).",
    ],
    "memory": [
        "Check memory graphs for the affected service and look for a steady climb (possible leak).",
        "Check whether a recent deployment or traffic increase lines up with the first memory warning.",
        "Restart the affected instance only after capturing a heap dump or logs for later analysis.",
    ],
    "auth": [
        "Check whether tokens or certificates recently expired or were rotated.",
        "Confirm the identity provider is reachable and its clock is in sync.",
    ],
    "network": [
        "Check whether the target service is running and passing health checks.",
        "Verify DNS, firewall and load balancer settings for recent changes.",
    ],
    "disk": [
        "Check disk usage on the affected server and find what is growing (logs, temp files, backups).",
        "Free up space safely (rotate or archive logs) and confirm services can write again.",
    ],
}

SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]


# ---------- Small helpers ----------

def _is_business_critical(service: str, message: str) -> bool:
    text = f"{service} {message}".lower()
    return any(word in text for word in BUSINESS_CRITICAL_WORDS)


def _matches_rule(message: str, rule: dict) -> bool:
    text = message.lower()
    return any(keyword in text for keyword in rule["keywords"])


# ---------- Main function: analyse the entries ----------

def analyze_entries(entries: list[LogEntry]) -> dict:
    """Return a dictionary of facts about the logs (counts, patterns, severity)."""

    level_counts = Counter(entry.level for entry in entries)

    # We care about problems: errors, fatals, and warnings.
    problem_entries = [e for e in entries if e.level in ("FATAL", "ERROR", "WARN")]
    error_entries = [e for e in entries if e.level in ("FATAL", "ERROR")]

    # --- Time range of the whole log ---
    times = [e.time for e in entries if e.time]
    time_range = (min(times), max(times)) if times else ("unknown", "unknown")

    # --- Which services are having errors? ---
    services_with_errors = Counter(e.service for e in error_entries if e.service)

    # --- Repeated error messages (same message, different numbers) ---
    grouped = defaultdict(list)
    for entry in error_entries:
        grouped[normalize_message(entry.message)].append(entry)

    repeated_errors = []
    for pattern, items in sorted(grouped.items(), key=lambda pair: -len(pair[1])):
        repeated_errors.append({
            "pattern": pattern,
            "count": len(items),
            "first_seen": items[0].time,
            "last_seen": items[-1].time,
            "services": sorted({i.service for i in items if i.service}),
            "example_line": items[0].line_number,
        })

    # --- Known failure types (timeouts, database, memory, ...) ---
    findings = []
    for rule in FAILURE_RULES:
        matched = [e for e in problem_entries if _matches_rule(e.message, rule)]
        if not matched:
            continue
        findings.append({
            "name": rule["name"],
            "category": rule["category"],
            "meaning": rule["meaning"],
            "count": len(matched),
            "first_seen": matched[0].time,
            "last_seen": matched[-1].time,
            "services": sorted({m.service for m in matched if m.service}),
            "example_line": matched[0].line_number,
            "example_text": matched[0].message,
        })
    findings.sort(key=lambda f: -f["count"])

    severity, reasons = decide_severity(entries, error_entries, findings, services_with_errors)

    return {
        "total_lines": len(entries),
        "level_counts": dict(level_counts),
        "error_count": len(error_entries),
        "time_range": time_range,
        "services_with_errors": dict(services_with_errors),
        "repeated_errors": repeated_errors,
        "findings": findings,
        "rules_severity": severity,
        "rules_severity_reasons": reasons,
    }


# ---------- Severity: simple, explainable scoring ----------

def decide_severity(entries, error_entries, findings, services_with_errors):
    """
    Decide Critical / High / Medium / Low using clear rules we can explain out loud.

    Critical : a FATAL message, OR a business-critical service is failing
               together with 2+ different kinds of failures (widespread impact).
    High     : a business-critical service has repeated errors (3 or more).
    Medium   : the same error repeats 3+ times in a less critical area, or many warnings.
    Low      : only a few isolated errors or warnings.
    """
    reasons = []

    fatal_count = sum(1 for e in entries if e.level == "FATAL")
    critical_errors = [e for e in error_entries if _is_business_critical(e.service, e.message)]
    failure_kinds = {f["category"] for f in findings}
    warn_count = sum(1 for e in entries if e.level == "WARN")

    most_repeated = 0
    grouped = Counter(normalize_message(e.message) for e in error_entries)
    if grouped:
        most_repeated = max(grouped.values())

    # --- Critical ---
    if fatal_count > 0:
        reasons.append(f"{fatal_count} FATAL message(s) found, which usually means a service could not continue.")
        return "Critical", reasons
    if len(critical_errors) >= 3 and len(failure_kinds) >= 2:
        reasons.append(f"{len(critical_errors)} errors in business-critical services (payment/order/auth).")
        reasons.append(f"{len(failure_kinds)} different failure types at once, suggesting wide impact.")
        return "Critical", reasons

    # --- High ---
    if len(critical_errors) >= 3:
        reasons.append(f"{len(critical_errors)} repeated errors in business-critical services.")
        return "High", reasons

    # --- Medium ---
    if most_repeated >= 3:
        reasons.append(f"The same error repeated {most_repeated} times, but not in a clearly business-critical service.")
        return "Medium", reasons
    if warn_count >= 5:
        reasons.append(f"{warn_count} warnings found; no hard failures yet but worth watching.")
        return "Medium", reasons

    # --- Low ---
    reasons.append("Only a few isolated errors or warnings; no repeated failure pattern found.")
    return "Low", reasons


# ---------- Rule-based hypothesis, steps and escalation ----------

def build_rule_based_analysis(stats: dict) -> dict:
    """
    Produce a full analysis (same shape as the AI's answer) using only rules.
    Used when no AI key is available, or when the AI call fails.
    """
    findings = stats["findings"]
    severity = stats["rules_severity"]

    # --- Key errors and patterns ---
    key_errors = [
        f'{r["count"]}x "{r["pattern"]}" (first at {r["first_seen"] or "?"}, line {r["example_line"]})'
        for r in stats["repeated_errors"][:5]
    ]
    patterns = [
        f'{f["name"]}: {f["count"]} occurrence(s), first {f["first_seen"] or "?"}, last {f["last_seen"] or "?"}'
        for f in findings
    ]

    # Put failure types in time order: what started first is the best suspect.
    in_time_order = sorted(findings, key=lambda f: f["first_seen"] or "9999")

    # --- Likely cause: the failure type that started EARLIEST is the best suspect ---
    evidence, assumptions = [], []
    if findings:
        earliest = in_time_order[0]
        likely_cause = (
            f'Possible root cause: {earliest["name"].lower()}. {earliest["meaning"]} '
            f'It appears earliest in the logs, so other failures may be side effects of it.'
        )
        for f in in_time_order[:4]:
            evidence.append(f'Line {f["example_line"]}: "{f["example_text"]}" ({f["count"]} matching log {"entry" if f["count"] == 1 else "entries"})')
        assumptions.append("Assumed the earliest failure type is the trigger; logs alone cannot prove cause and effect.")
        assumptions.append("Assumed the logs cover the whole incident window and no lines were removed.")
        if len(findings) > 1:
            assumptions.append("Other failure types may be symptoms of the first one, not separate problems.")
    else:
        likely_cause = "No known failure pattern was found. More logs or context are needed."
        assumptions.append("The issue may be outside the supplied logs.")

    # --- Troubleshooting steps: root cause first, no duplicates, at most 6 ---
    steps = []
    for f in in_time_order:
        for step in TROUBLESHOOTING_STEPS.get(f["category"], [])[:2]:
            if step not in steps:
                steps.append(step)
    steps = steps[:6]
    if not steps:
        steps = ["Collect more logs around the time of the reported problem.",
                 "Ask the reporter what they saw and when it started."]

    # --- Escalation advice ---
    if severity in ("Critical", "High"):
        escalation = {
            "needed": True,
            "when": "Escalate now if customers are affected or the errors are still increasing.",
            "to": "On-call engineering / incident manager",
        }
    else:
        escalation = {
            "needed": False,
            "when": "Escalate if the errors keep repeating after basic checks, or if customers report problems.",
            "to": "Application support team",
        }

    return {
        "summary": (f'{stats["error_count"]} error(s) in {stats["total_lines"]} log lines between '
                    f'{stats["time_range"][0]} and {stats["time_range"][1]}.'),
        "key_errors": key_errors,
        "patterns": patterns,
        "likely_cause": likely_cause,
        "evidence": evidence,
        "assumptions": assumptions,
        "severity": severity,
        "severity_reason": " ".join(stats["rules_severity_reasons"]),
        "troubleshooting_steps": steps,
        "escalation": escalation,
        "source": "rules",
    }
