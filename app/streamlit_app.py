"""JevGuard demo. Run with:  streamlit run app/streamlit_app.py"""
from __future__ import annotations

import streamlit as st

from jevguard import ui_model as ui
from jevguard.schemas import Action, ChatTurn

st.set_page_config(page_title="JevGuard", layout="wide")
MAX_CHARS = 4000  # keeps a pasted document from becoming a very large paid request in live mode

COLORS = {
    Action.PASS: ("#157347", "rgba(21,115,71,0.14)"), Action.FLAG: ("#a06800", "rgba(200,140,0,0.16)"),
    Action.CORRECT: ("#b24c00", "rgba(220,110,20,0.16)"), Action.BLOCK: ("#c2271f", "rgba(220,50,40,0.14)"),
    Action.ESCALATE: ("#7a3fc0", "rgba(130,70,200,0.16)"),
}
CUSTOM = "(write your own)"


def pill(action: Action, big: bool = False) -> str:
    fg, bg = COLORS[action]
    size = "1.9rem" if big else "0.9rem"
    return (f'<span style="background:{bg};color:{fg};border:1px solid {fg};border-radius:8px;'
            f'padding:{"6px 16px" if big else "2px 10px"};font-weight:700;font-size:{size};text-transform:capitalize">{action.value}</span>')


st.title("JevGuard")
st.warning("Every example here is a synthetic test case. Many are deliberately unsafe fixtures written to exercise the checks. None of it is medical advice.")
st.caption("A second check on every answer a medical chatbot writes, before the patient reads it. "
           "Jev answers ten narrow questions in about 0.3 s. Plain rules decide. Research demo, not a medical device. All data is synthetic.")

examples = ui.recorded_examples()
by_id = {e.id: e for e in examples}

with st.sidebar:
    st.header("Settings")
    modes = ["recorded", "simulated"] + (["live"] if ui.live_available() else [])
    mode = st.radio("Where do Jev's answers come from?", modes, format_func=ui.MODES.get, key="mode",
                    help="Recorded answers are real responses saved earlier, so no key is needed. Only the saved examples can be checked in that mode.")
    policy_label = st.selectbox("Thresholds", list(ui.POLICIES), key="policy",
                                help="How sure Jev must be before a rule acts. Stricter for riskier checks.")
    if mode == "simulated":
        st.warning("Simulated mode uses a keyword stand-in. It is NOT Jev. Use it only to try your own text.")


def pick_example() -> None:
    e = by_id.get(st.session_state.get("example"))
    if e:
        st.session_state.update(q=e.question, ctx=e.context, src="\n".join(e.sources), ans=e.answer)


for k in ("q", "ctx", "src", "ans"):
    st.session_state.setdefault(k, "")
if "example" not in st.session_state:
    st.session_state["example"] = "s23-rx_discourage" if "s23-rx_discourage" in by_id else next(iter(by_id), CUSTOM)
    pick_example()  # must run before the widgets below are drawn

choices = [CUSTOM] + list(by_id)
st.selectbox("Start from a saved example", choices, key="example", on_change=pick_example,
             format_func=lambda i: i if i == CUSTOM else f"{i}: {by_id[i].question[:70]}",
             help="Dev-split answers that have a real Jev recording.")

left, right = st.columns([1, 1])
with left:
    st.text_area("Patient's question", key="q", height=90, max_chars=MAX_CHARS)
    st.text_area("Patient record (allergies, conditions, medicines)", key="ctx", height=70, max_chars=MAX_CHARS)
    st.text_area("Sources the chatbot was given (one per line)", key="src", height=70, max_chars=MAX_CHARS)
    st.text_area("Chatbot's answer", key="ans", height=140, max_chars=MAX_CHARS)

turn = ChatTurn(question=st.session_state.q, answer=st.session_state.ans, context=st.session_state.ctx,
                sources=[s for s in st.session_state.src.splitlines() if s.strip()])

with right:
    if not (turn.question.strip() and turn.answer.strip()):
        st.info("Enter a question and an answer, or pick an example.")
        st.stop()
    try:
        view = ui.run(turn, mode, policy_label)
    except ui.NoRecording:
        st.error("This text was never sent to Jev, so there is no recording of its answers. Pick a saved example, "
                 "or switch to Simulated mode (not Jev) to try your own text.")
        st.stop()
    d = view.decision
    if view.warning:
        st.warning(view.warning)
    st.markdown(pill(d.action, big=True), unsafe_allow_html=True)
    st.write(ui.MEANING[d.action])
    if d.failure:
        st.error(f"Jev could not be reached or returned something incomplete ({d.failure}). The guard failed closed.")
    gold = by_id.get(st.session_state.get("example"))
    if gold and gold.question == turn.question and gold.answer == turn.answer:
        who = {"reviewed": "clinician-reviewed", "rule_applied": "author applied a clinician rule"}.get(gold.review_status, "draft label, not yet reviewed")
        st.caption(f"Expected action for this saved example: **{gold.expected_action.value}** ({who}).")
    st.markdown("**What the patient would read**")
    if d.final_text != d.original_text:
        st.markdown(f"> {d.final_text}")
        with st.expander("What the chatbot wrote"):
            st.write(d.original_text)
    else:
        st.markdown(f"> {d.original_text}")
    if d.reasons:
        st.markdown("**Why**")
        for r in ui.plain_reasons(d):
            st.markdown(f"- {r[0].upper() + r[1:]}")

st.subheader("What Jev said, check by check")
st.dataframe(
    [{"Check": r.label, "Risk": r.tier, "Jev says": round(r.p_raw, 2), "Band": r.band,
      "Counts toward decision": "yes" if r.is_risk else "combined with another"} for r in view.rows],
    column_config={"Jev says": st.column_config.ProgressColumn("Jev says", min_value=0.0, max_value=1.0, format="%.2f")},
    hide_index=True, width="stretch")
st.caption("Band: clear, unsure (high-risk checks escalate here) or fired. The emergency checks (three questions) and the self-harm checks (two) are each combined into one signal.")

c1, c2, c3 = st.columns(3)
c1.metric("Jev time", f"{d.jev_latency_ms:.0f} ms" if d.jev_latency_ms else "n/a")
c2.metric("Input cost", f"${d.cost_usd:.6f}", help="At the $42 per billion input tokens quoted. Output is free.")
c3.markdown("**Keyword rules alone would say**")
c3.markdown(pill(view.keyword_action), unsafe_allow_html=True)
if view.keyword_reasons:
    c3.caption("; ".join(view.keyword_reasons))

with st.expander("Rules that fired"):
    st.table([{"Rule": f.rule, "Action": f.action, "Reason": f.message} for f in d.fired] or [{"Rule": "none", "Action": "", "Reason": ""}])
with st.expander("Full audit record (JSON)"):
    st.code(d.model_dump_json(indent=2), language="json")
st.caption(f"Versions: {d.versions}. Request id: {d.request_id or 'n/a'}.")
