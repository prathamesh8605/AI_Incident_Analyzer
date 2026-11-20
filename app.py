"""
app.py
------
The screen the support engineer sees.

Run it with:   streamlit run app.py

Flow on screen:
  1. Upload a log file, paste logs, or pick a sample.
  2. Click "Analyze incident".
  3. Read the severity, cause, evidence, next steps, and copy the summary.
"""

import os
from pathlib import Path

import streamlit as st

from analyzer import run_analysis

SAMPLE_FOLDER = Path(__file__).parent / "sample_logs"

SEVERITY_COLORS = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}


def show_list(items):
    """Show a list of text lines as bullet points."""
    for item in items:
        st.markdown(f"- {item}")


# ---------- Page setup ----------
st.set_page_config(page_title="AI Incident Analyzer", page_icon="🛠️", layout="wide")
st.title("🛠️ AI-Powered Incident Analyzer")
st.caption("Paste or upload application logs. Get a likely cause, severity, next steps and a shareable summary. "
           "Use sample or simulated logs only.")

# ---------- Sidebar: settings ----------
with st.sidebar:
    st.header("Settings")
    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    use_ai = st.checkbox("Use AI model (Claude)", value=has_key,
                         help="Needs ANTHROPIC_API_KEY. Without it, rule-based analysis is used.")
    if use_ai and not has_key:
        st.warning("No ANTHROPIC_API_KEY found. The rule-based analysis will be used.")
    st.markdown("**Privacy:** emails, card numbers and tokens are masked before analysis.")

# ---------- Step 1: get the logs ----------
# The assignment's own example (payment + database) is shown first.
sample_files = sorted((p.name for p in SAMPLE_FOLDER.glob("*.log")), key=lambda n: (not n.startswith("payment"), n))
source = st.radio("Where are the logs coming from?", ["Sample log", "Paste text", "Upload file"], horizontal=True)

log_text, source_name = "", "pasted logs"

if source == "Sample log":
    choice = st.selectbox("Choose a sample", sample_files)
    if choice:
        log_text = (SAMPLE_FOLDER / choice).read_text()
        source_name = choice
        with st.expander("Preview the log"):
            st.code(log_text, language="log")
elif source == "Paste text":
    log_text = st.text_area("Paste logs here", height=250)
else:
    uploaded = st.file_uploader("Upload a .log or .txt file", type=["log", "txt"])
    if uploaded:
        log_text = uploaded.read().decode("utf-8", errors="replace")
        source_name = uploaded.name

# ---------- Step 2: analyse ----------
if st.button("Analyze incident", type="primary", disabled=not log_text.strip()):
    try:
        with st.spinner("Analyzing logs..."):
            result = run_analysis(log_text, use_ai=use_ai, source_name=source_name)
        st.session_state["result"] = result
    except ValueError as problem:
        st.error(str(problem))

# ---------- Step 3: show the answer ----------
result = st.session_state.get("result")
if result:
    analysis, stats = result["analysis"], result["stats"]

    if analysis.get("note"):
        st.info(analysis["note"])

    icon = SEVERITY_COLORS.get(analysis["severity"], "")
    st.header(f"{icon} Severity: {analysis['severity']}")
    st.write(analysis["severity_reason"])

    if analysis.get("source") == "ai" and analysis.get("rules_severity") != analysis["severity"]:
        st.caption(f"Note: the simple rule check suggested **{analysis['rules_severity']}**. "
                   "A human should decide which one fits.")

    # Quick numbers
    c1, c2, c3 = st.columns(3)
    c1.metric("Log lines", stats["total_lines"])
    c2.metric("Errors", stats["error_count"])
    c3.metric("Services with errors", len(stats["services_with_errors"]))

    left, right = st.columns(2)
    with left:
        st.subheader("What happened")
        st.write(analysis["summary"])
        st.subheader("Key errors")
        show_list(analysis["key_errors"])
        st.subheader("Patterns")
        show_list(analysis["patterns"])
    with right:
        st.subheader("Likely cause (not confirmed)")
        st.write(analysis["likely_cause"])
        st.markdown("**✅ Evidence (seen in the logs)**")
        show_list(analysis["evidence"])
        st.markdown("**⚠️ Assumptions (not proven)**")
        show_list(analysis["assumptions"])

    st.subheader("Troubleshooting steps")
    for number, step in enumerate(analysis["troubleshooting_steps"], start=1):
        st.markdown(f"{number}. {step}")

    st.subheader("Escalation")
    esc = analysis["escalation"]
    (st.error if esc.get("needed") else st.success)(
        f"{'Escalate: ' if esc.get('needed') else 'Not needed yet. '}{esc.get('when', '')}  \n"
        f"**Contact:** {esc.get('to', 'n/a')}")

    st.subheader("Shareable incident summary")
    st.text_area("Copy this into Slack, email or a ticket", result["summary_text"], height=350)
    st.download_button("Download summary (.txt)", result["summary_text"], file_name="incident_summary.txt")
