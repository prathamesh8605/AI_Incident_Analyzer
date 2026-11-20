# Case Study: AI-Powered Incident Analyzer
**Role:** Technology Operations Intern – Practical AI Assignment 1

---

## 1. The Problem

After a service issue, a support engineer receives many log files. Under time pressure they must answer four questions fast:

1. What went wrong?
2. How serious is it?
3. What should I check first?
4. Do I need to escalate?

Reading hundreds of lines by hand is slow, and tired people miss patterns. Worse, people often treat a **guess** as a **fact**, which sends the investigation in the wrong direction.

## 2. Goal

Build a simple prototype that reads sample logs and produces a clear, honest analysis:
errors summarized, a likely cause, severity with a reason, next steps, escalation advice, and a shareable summary.

**Success looks like:** a readable analysis, recommendations that match the evidence, and guesses that are *labelled* as guesses.

## 3. Users

| User | What they need |
|---|---|
| Support engineer (primary) | A fast first look and a clear "check this first" |
| On-call / engineering team | A short summary they can trust |
| Operations manager | Severity and impact in plain words |

## 4. My Approach

**Core idea: let code do the counting and let AI do the thinking.**

- Code is exact at counting errors, grouping repeats and reading timestamps.
- AI is good at connecting clues and writing useful advice.
- So the code produces **facts first**, then the AI reasons over those facts.

```
Logs -> Parse -> Mask secrets -> Rules (facts) -> AI (reasoning) -> Validate -> Report
                                        \__ if AI fails, use rule-based answer __/
```

### Key design decisions

| Decision | Reason |
|---|---|
| Parse into time / level / service / message | Makes counting and timelines possible |
| Group similar errors by replacing numbers (`30012ms` -> `<n>ms`) | Shows true repeats, not 8 "different" errors |
| Mask emails, card numbers, tokens before AI | Logs often contain private data by accident |
| Send facts + numbered lines to the AI | AI can cite line numbers as evidence |
| Force JSON output, then validate it | Output is predictable; bad answers are rejected |
| Rule-based fallback | Tool still works without internet or an API key |
| Separate **Evidence** and **Assumptions** | Directly meets "do not present guesses as facts" |
| Keep rule severity next to AI severity | Gives a human a second opinion to compare |

## 5. How the AI Component Works

1. The code builds a message with **statistics** (counts, time range, services, repeated errors) and up to ~150 relevant log lines (problems first).
2. The system prompt tells the model to: use only the logs, cite line numbers, separate evidence from assumptions, say "likely/possible" for causes, and reply in a fixed JSON shape.
3. `temperature = 0` keeps answers steady and repeatable.
4. The code checks the reply: valid JSON, all fields present, severity is one of the four allowed words.
5. If anything fails, the rule-based answer is shown and a note explains why.

## 6. Severity Framework (explainable on purpose)

| Level | Rule used |
|---|---|
| **Critical** | A FATAL message, **or** a business-critical service failing with 2+ kinds of failure at once |
| **High** | Business-critical service with 3+ repeated errors |
| **Medium** | Same error repeating 3+ times elsewhere, or many warnings |
| **Low** | A few isolated errors |

Business-critical = payment, order, checkout, auth, login, billing.

## 7. Worked Example (the assignment's scenario)

**Input:** simulated logs with payment API timeouts and database connection failures.

**What the tool finds**

- 8 payment gateway timeouts, 6 failed order saves ("could not acquire DB connection"), 2 DB connection failures, 1 gateway 503.
- Timeline: pool usage warning (85%, then 96%) -> pool exhausted -> order failures -> payment timeouts -> health check failures.

**Likely cause (not confirmed):** database connection pool exhaustion appears *first*, so payment timeouts may be a side effect.

**Evidence:** line 9 "Connection pool exhausted: 50/50 connections active, 12 requests waiting"; 6 order failures within ~1 minute after it.

**Assumptions:** the earliest failure is the trigger; the payment gateway itself may be healthy; logs cover the whole window.

**Severity:** Critical. Payment and order flows both failing, several failure types at once.

**First checks:** database connections vs. maximum, long-running or blocked queries, pool settings and recent changes, then the payment gateway status.

**Escalate:** yes, to on-call engineering if customers are affected or errors keep rising.

*Also tested:* a memory leak ending in a crash (Critical because of FATAL) and a mostly healthy log (Low).

## 8. Testing

- **16 automated tests:** parsing, stack traces, junk lines, repeat grouping, secret masking, severity on three samples, rejection of invalid AI replies, fallback to rules, and "evidence and assumptions are always separated."
- **Fake AI client** in tests: no API cost, no internet, same result every run.
- **Safety checks found real problems during development:**
  - A harmless "Disk usage at 78%" warning was wrongly flagged as a disk failure -> I tightened the rule and added a test.
  - The first version gave 10 troubleshooting steps, too many to act on -> now capped at 6, root-cause first.

## 9. Limitations (said honestly)

- Keyword rules can miss unusual wording or flag harmless text.
- Large logs are sampled (about 150 lines) before going to the AI.
- The AI can be wrong. Output is guidance for a human to confirm.
- Logs alone can't prove cause and effect, which is why the tool says "likely" and lists assumptions.
- No metrics or traces, only logs. Thresholds would need tuning by a real team.

## 10. What I Would Do Next

1. Add a "Was this helpful?" button to measure accuracy over time.
2. Accept metrics and traces, not only logs.
3. Learn from past incidents and their final root causes.
4. Post the summary straight to Slack or create a Jira ticket.
5. Support JSON-structured logs and very large files (streaming).

## 11. My Contribution and AI Use
*(Fill this in with your own honest words. The assignment asks for it, and interviewers will ask.)*

- **What I designed / decided myself:** e.g. the facts-first approach, the severity rules, evidence vs. assumptions split.
- **Where AI tools helped:** e.g. drafting code, reviewing, wording prompts.
- **What I checked or changed myself:** e.g. tested all three logs, fixed the disk-warning false alarm.

---

## Appendix A: 10-Minute Presentation Plan

| Min | Slide | Say |
|---|---|---|
| 0:00–1:00 | Problem | Engineers must triage fast; guesses get mistaken for facts |
| 1:00–2:00 | Goal and users | Fast first look, honest output |
| 2:00–4:00 | Approach | Diagram: code for facts, AI for reasoning, fallback |
| 4:00–7:30 | **Live demo** | Payment + DB sample: severity, cause, evidence vs. assumptions, steps, summary. Then show the Low sample for contrast |
| 7:30–8:30 | Testing | 16 tests, fake AI client, two bugs I found |
| 8:30–9:30 | Limitations and next steps | Be honest |
| 9:30–10:00 | My contribution and AI use | Clear and truthful |

**Backup plan:** if internet or the API key fails, switch off "Use AI" and demo rule-based mode. It still works, and it shows the fallback design.

## Appendix B: Likely Q&A

**Why use both rules and AI?** Rules are exact and explainable. AI reasons better across messages. Rules also make the tool work offline.

**How do you stop the AI from making things up?** Facts are computed by code; the prompt forbids invention and requires line-number evidence; replies are validated; "likely" wording and an Assumptions section are enforced.

**What if the AI and the rules disagree on severity?** The screen shows both. A human decides. Disagreement is a useful signal to look closer.

**How did you test an AI component?** Tests use a fake client with good, broken and garbage replies. I also compared AI-on and AI-off results on three logs.

**What about sensitive data in logs?** Emails, card numbers and tokens are masked before analysis and before anything is sent to the model.

**What would break it?** Very unusual log formats, huge logs, or failures that need metrics (e.g. a slow memory climb with no log lines).

**How would you improve it for production?** Feedback loop, past-incident memory, metrics/traces, Slack/Jira integration, tuned thresholds, access control and audit logs.

**Why is the severity Critical in the example?** Payment and order flows are failing together with multiple failure types, so customers are likely affected.
