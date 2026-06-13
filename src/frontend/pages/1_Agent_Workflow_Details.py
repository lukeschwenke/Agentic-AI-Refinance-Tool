import streamlit as st
from pathlib import Path
from ui import apply_theme, page_header, footer

st.set_page_config(page_title="Agent Workflow Details", page_icon="🏡", layout="wide")
apply_theme()

page_header(
    "Under the hood",
    "Agentic Workflow Details",
    "How RefiAI's cooperating agents move from your inputs to a clear recommendation.",
)

FRONTEND_DIR = Path(__file__).resolve().parents[1]
IMG_PATH = FRONTEND_DIR / "images" / "agentic_dag.png"

AGENTS = [
    (
        "1 · Market Expert",
        "Pulls a national average rate (web search) and a Washington DC-area credit-union rate, "
        "and uses the **lower** of the two. If it already beats your rate, the run stops here.",
    ),
    (
        "2 · Treasury Timing",
        "Reads the 10-year Treasury yield and where it sits in its 52-week range and spread — "
        "market context, not a gate. Runs **in parallel** with the Rate Outlook.",
    ),
    (
        "3 · Rate Outlook",
        "Searches recent Fed and forecaster commentary and classifies where 30-year rates are "
        "headed: **falling, stable, or rising**.",
    ),
    (
        "4 · Calculator",
        "Deterministically models three structures — keep your payoff date, a 30-year reset, and "
        "15-year — with payment, savings, break-even, and **lifetime-interest** change.",
    ),
    (
        "5 · Strategy",
        "Picks the best structure for your time horizon, weighing monthly savings against lifetime "
        "interest — or recommends **none** if nothing pencils out.",
    ),
    (
        "6 · Finalizer",
        "Writes the recommendation. Every number and the verdict are precomputed in Python; the "
        "model only narrates.",
    ),
    (
        "7 · Self-check",
        "A second model fact-checks the draft against the computed numbers and sends it back once "
        "for a fix if anything is off.",
    ),
]

col1, col2 = st.columns([1, 2], gap="large")

with col1:
    with st.container(border=True):
        st.markdown('<div class="refi-eyebrow">Workflow graph</div>', unsafe_allow_html=True)
        st.markdown("###### DAG")
        st.image(str(IMG_PATH), width="stretch")
        st.caption(
            "**Market → (Treasury + Rate Outlook, in parallel) → Calculator → Strategy → "
            "Finalizer → Self-check.** If your rate already beats the market, it skips straight "
            "to the Finalizer."
        )

with col2:
    st.markdown('<div class="refi-eyebrow">The agents</div>', unsafe_allow_html=True)
    st.markdown("###### Seven specialists, one recommendation")
    for title, body in AGENTS:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.markdown(body)

st.write("")
st.caption("Source")
st.markdown(
    "[Agent code](https://github.com/lukeschwenke/Agentic-AI/blob/main/src/core/agents.py)  ·  "
    "[Tools code](https://github.com/lukeschwenke/Agentic-AI/blob/main/src/core/tools.py)"
)

footer()
