# AI-Powered Incident Analyzer

A small tool that helps a Technology Operations engineer investigate an application issue.
Paste or upload logs and it will:

1. Summarize key errors and repeated failures
2. Suggest a **likely** cause, keeping **evidence** separate from **assumptions**
3. Rate severity (Critical / High / Medium / Low) and explain why
4. Recommend troubleshooting steps and say when to escalate
5. Produce a short incident summary you can paste into Slack, email or a ticket

> Uses **sample / simulated logs only**. No production access is needed.

---

## Setup (about 2 minutes)

```bash
# 1. Install
pip install -r requirements.txt

# 2. (Optional) turn on the AI model. Without a key, the rule-based mode still works.
export ANTHROPIC_API_KEY="your-key-here"        # Windows PowerShell: $env:ANTHROPIC_API_KEY="your-key-here"

# 3. Create the sample logs (already included, this just regenerates them)
python make_sample_logs.py

# 4. Start the app
streamlit run app.py
```

Run the tests: `pytest -v`

## How to use

1. Choose **Sample log**, **Paste text** or **Upload file**.
2. Click **Analyze incident**.
3. Read the result and copy the summary at the bottom.

Start with `payment_and_database_incident.log`. It matches the example in the assignment.

---

## Approach

```
raw logs -> parse -> mask secrets -> rules (facts) -> AI (reasoning) -> check answer -> report
                                          \______ if AI fails: rule-based answer ______/
```

| File | Job |
|---|---|
| `log_parser.py` | Reads each line into time / level / service / message. Masks emails, card numbers, tokens. |
| `rules_engine.py` | Counts errors, groups repeats, detects failure types (timeout, database, memory...), scores severity with simple rules. |
| `ai_analyzer.py` | Sends the facts and the most relevant log lines to Claude, asks for strict JSON, validates the answer. |
| `report_builder.py` | Builds the shareable incident summary. |
| `analyzer.py` | Connects all steps in one function. |
| `app.py` | The Streamlit screen. |

**Why rules AND AI?** Code is better at exact counting. The AI is better at reasoning across
messages and writing clear advice. Rules give the AI reliable numbers, and act as a backup when the
AI is unavailable.

## AI tools / models used

- **Runtime:** Anthropic Claude via the API (model set by `ANTHROPIC_MODEL`, default in `ai_analyzer.py`), `temperature=0` for steady answers.
- **Development:** AI assistance was used to help write and review the code. *(Edit this line to describe exactly what you did yourself vs. what AI helped with.)*

## How the AI is kept honest

- It receives computed statistics and numbered log lines, not just raw text.
- The system prompt says: use only the logs, separate evidence from assumptions, never present a guess as fact.
- The reply must be JSON with fixed fields. Missing fields or an invalid severity are rejected.
- Rule-based severity is kept alongside the AI's severity, and the screen shows a note if they differ.

## Assumptions

- Logs follow a common format: `date time LEVEL [service] message`. Other formats are handled loosely.
- The earliest failure type is treated as the best root-cause suspect (a hypothesis, never a fact).
- Services with words like *payment, order, auth, checkout* are treated as business-critical.
- Pasted logs cover the incident window.

## Testing

- 16 automated tests (`pytest`) cover: parsing, stack traces, messy lines, grouping of repeats, secret masking, severity on three sample logs (Critical / Critical / Low), rejection of bad AI answers, and fallback to rules.
- Tests use a **fake AI client**, so they run offline and give the same result each time.
- Manual check: run all three sample logs with AI on and off, and compare results.

| Sample log | Expected severity | Why |
|---|---|---|
| `payment_and_database_incident.log` | Critical | Payment/order errors plus several failure types |
| `memory_leak_crash.log` | Critical | Contains a FATAL crash |
| `mostly_healthy.log` | Low | One isolated error |

## Limitations

- Keyword rules can miss unusual wording or flag harmless text. Rules are simple on purpose.
- Only the most relevant ~150 lines are sent to the AI, so very large logs are sampled.
- The AI can still be wrong. Output is guidance for a human, not a decision.
- Cause and effect cannot be proven from logs alone, so the tool says "likely" and lists assumptions.
- No live monitoring, metrics or trace data. Logs only.
- Severity depends on rule thresholds that a real team would tune.

## Future improvements

Metrics and trace inputs, learning from past incidents, a feedback button ("was this right?"),
Slack / Jira integration, and support for JSON-structured logs.
