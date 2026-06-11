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
        "uses the **lower of the two** as the effective market rate. If that market rate is "
        "already **higher** than your current rate, the workflow short-circuits straight to "
        "the Finalizer — there's no refinance worth analyzing.",
    ),
    (
        "Agent #2 · Treasury Yield",
        "Pulls the U.S. 10-year Treasury yield plus its 52-week high/low and prior close from "
        "CNBC, then derives **relative** timing signals: where the yield sits within its "
        "trailing 52-week range, its day-over-day direction, and the mortgage-to-Treasury "
        "spread versus the ~1.75% long-run norm. It's framed as timing *context*, not a "
        "pass/fail gate (this replaced the old static 4.0% rule).",
    ),
    (
        "Agent #3 · Rate Outlook",
        "Searches recent Federal Reserve and forecaster commentary (Tavily) for where 30-year "
        "mortgage rates are heading, then classifies a forward-looking label "
        "(**falling / stable / rising**) and a posture (**act / wait / neutral**) — adding a "
        "forward view that complements the Treasury signal.",
    ),
    (
        "Agent #4 · Calculator",
        "Models several refinance structures deterministically — **keeping your current payoff "
        "date** (same remaining term), a **30-year reset**, and a **15-year** payoff. For each "
        "it computes the new payment, monthly savings, realistic closing costs (~2% of balance "
        "or your own quote), break-even, and the change in **lifetime interest**, and flags "
        "whether you'd break even before your stay-horizon.",
    ),
    (
        "Agent #5 · Strategy",
        "Reasons over those scenarios and your time horizon to **recommend the best structure**, "
        "explicitly weighing monthly savings against the lifetime-interest tradeoff — a lower "
        "payment from a fresh 30-year term can quietly cost tens of thousands more overall.",
    ),
    (
        "Agent #6 · Finalizer",
        "Synthesizes the rates, the recommended structure, your savings, break-even-vs-horizon, "
        "the Treasury timing, and the rate outlook into a clear, skimmable recommendation — "
        "naming which rate drove the math and calling out the lifetime-interest tradeoff.",
    ),
]

col1, col2 = st.columns([1, 2], gap="large")

with col1:
    with st.container(border=True):
        st.markdown('<div class="refi-eyebrow">Workflow graph</div>', unsafe_allow_html=True)
        st.markdown("###### DAG")
        st.image(str(IMG_PATH), width="stretch")
        st.caption(
            "Flow: **Market → Treasury → Rate Outlook → Calculator → Strategy → Finalizer**. "
            "If the market rate is already higher than your rate, RefiAI skips straight to the "
            "Finalizer."
        )

with col2:
    st.markdown('<div class="refi-eyebrow">The agents</div>', unsafe_allow_html=True)
    st.markdown("###### Six specialists, one recommendation")
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
