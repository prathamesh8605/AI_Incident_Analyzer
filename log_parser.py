"""
log_parser.py
-------------
Step 1 of the tool: turn raw log text into a clean list of entries.

A typical log line looks like this:
    2026-11-18 10:14:05,123 ERROR [payment-service] Payment API timeout after 30000ms

We split it into: time, level, service and message.
Lines that do not follow this shape (for example stack-trace lines) are
handled gracefully so one strange line never breaks the whole analysis.
"""

import re
from dataclasses import dataclass


# ---------- The shape of one parsed log line ----------

@dataclass
class LogEntry:
    line_number: int      # position in the file (starts at 1) so we can point to evidence
    time: str             # e.g. "2026-11-18 10:14:05" (empty if the line had no time)
    level: str            # FATAL, ERROR, WARN, INFO, DEBUG or UNKNOWN
    service: str          # e.g. "payment-service" (empty if not present)
    message: str          # the human-readable part
    raw: str              # the original line, untouched


# ---------- Pattern that recognises a normal log line ----------

LOG_LINE_PATTERN = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(?:[.,]\d+)?\s+"
    r"(?P<level>FATAL|CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\s+"
    r"(?:\[(?P<service>[^\]]+)\]\s+)?"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)

# Different tools write the same level differently, so we use one standard name.
LEVEL_ALIASES = {
    "CRITICAL": "FATAL",
    "WARNING": "WARN",
}

# Used only when a line has no proper format but still mentions a level word.
LOOSE_LEVEL_PATTERN = re.compile(r"\b(FATAL|CRITICAL|ERROR|WARN(?:ING)?)\b", re.IGNORECASE)


def _standard_level(level: str) -> str:
    level = level.upper()
    return LEVEL_ALIASES.get(level, level)


def parse_logs(text: str) -> list[LogEntry]:
    """Read the whole log text and return a list of LogEntry objects."""
    entries: list[LogEntry] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue  # skip empty lines

        match = LOG_LINE_PATTERN.match(line.strip())
        if match:
            entries.append(LogEntry(
                line_number=line_number,
                time=match.group("time").replace("T", " "),
                level=_standard_level(match.group("level")),
                service=(match.group("service") or "").strip(),
                message=match.group("message").strip(),
                raw=line,
            ))
            continue

        # Stack-trace style lines ("   at com.shop.Foo", "Caused by: ...") belong
        # to the entry above them, so we attach them there instead of counting
        # them as separate events.
        looks_like_continuation = line.startswith((" ", "\t")) or line.strip().startswith(("at ", "Caused by"))
        if looks_like_continuation and entries:
            entries[-1].message += " | " + line.strip()
            continue

        # Last resort: a free-form line. Try to spot a level word in it.
        loose = LOOSE_LEVEL_PATTERN.search(line)
        entries.append(LogEntry(
            line_number=line_number,
            time="",
            level=_standard_level(loose.group(1)) if loose else "UNKNOWN",
            service="",
            message=line.strip(),
            raw=line,
        ))

    return entries


# ---------- Helpers used by the rest of the tool ----------

def normalize_message(message: str) -> str:
    """
    Make similar messages look identical so we can count repeats.

    "Payment API timeout after 30012ms order=ORD-8841"
    "Payment API timeout after 29987ms order=ORD-9120"
    both become
    "Payment API timeout after <n>ms order=ORD-<n>"
    """
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", message, flags=re.I)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", text)
    text = re.sub(r"\d+", "<n>", text)
    return text


def mask_sensitive_data(text: str) -> str:
    """
    Hide personal or secret data before logs are shown or sent to an AI model.
    Real logs often contain emails, card numbers and tokens by accident.
    """
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", text)
    text = re.sub(r"\b(?:\d[ -]?){13,16}\b", "<card-number>", text)
    text = re.sub(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b\s*[=:]\s*\S+", r"\1=<hidden>", text)
    text = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._-]+", "Bearer <hidden>", text)
    return text
