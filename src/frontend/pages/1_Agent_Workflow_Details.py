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
        "Agent #1 · Market Expert",
        "Gathers two rate signals: a national average via a Tavily web search, and a "
        "Washington DC-area rate scraped from a local credit union's published rates. It "
        "uses the **lower of the two** as the effective market rate that drives the "
        "recommendation.",
    ),
    (
        "Agent #2 · Treasury Yield",
        "Retrieves the current U.S. 10-year Treasury yield via the CNBC REST API, evaluates "
        "it against desirability thresholds, and provides contextual guidance that informs "
        "the final recommendation.",
    ),
    (
        "Agent #3 · Calculator",
        "Computes the refinance break-even using your current monthly principal-and-interest "
        "payment and an estimated post-refinance payment — deriving monthly savings, "
        "estimated closing costs, and break-even as **closing costs ÷ monthly savings**.",
    ),
    (
        "Agent #4 · Finalizer",
        "Synthesizes the market-rate, treasury-yield, and break-even outputs into a concise "
        "recommendation. It reports both the national and Washington DC-area rates and states "
        "which one (the lower) drove the calculations.",
    ),
]

col1, col2 = st.columns([1, 2], gap="large")

with col1:
    with st.container(border=True):
        st.markdown('<div class="refi-eyebrow">Workflow graph</div>', unsafe_allow_html=True)
        st.markdown("###### DAG")
        st.image(str(IMG_PATH), width="stretch")

with col2:
    st.markdown('<div class="refi-eyebrow">The agents</div>', unsafe_allow_html=True)
    st.markdown("###### Four specialists, one recommendation")
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
