import streamlit as st
from client import get_recommendation
import time
import html
from pathlib import Path

st.set_page_config(page_title="Agentic Refinance Tool", page_icon="🏡")

st.title("Refi with Agentic AI")
st.markdown("##### Hello! Use this Agentic AI powered refinance tool to determine if now is a good time for you to refinance.")

FRONTEND_DIR = Path(__file__).resolve().parents[0]
IMG_PATH = FRONTEND_DIR / "images" / "landing_page_v1.png"
#st.set_page_config(layout="wide")
st.image(str(IMG_PATH), width="stretch")

# Ensure there is a place to store the last response
if "resp" not in st.session_state:
    st.session_state.resp = None

# User Input + Basic Validation
rate_str = st.text_input("What is your current mortgage interest rate (%)", placeholder="e.g., 6.125")
current_payment_str = st.text_input("What is your current monthly mortgage payment (principal and interest only)?", placeholder="e.g., $3,350")
mortgage_balance_str = st.text_input("What is the remaining balance on your mortgage loan?", placeholder="e.g., $500,000")
run = st.button("Get recommendation")

def clean_strings(text: str) -> str:
    return text.strip().replace("%", "").replace("$", "")

if run:
    if not rate_str or not rate_str.strip():
        st.error("Please enter an interest rate.")
    if not current_payment_str or not current_payment_str.strip():
        st.error("Please enter a current monthly payment.")
    if not mortgage_balance_str or not mortgage_balance_str.strip():
        st.error("Please enter a mortgage balance.")
    try:
        rate=float(clean_strings(rate_str))
        current_payment=float(clean_strings(current_payment_str))
        mortgage_balance=float(clean_strings(mortgage_balance_str))

        # Placeholder for secondary message
        status_placeholder = st.empty()
        start_time = time.time()

        with st.spinner("Calling agents for a recommendation..."):
            resp = get_recommendation(rate, current_payment, mortgage_balance)
            st.session_state.resp = resp
                
    except ValueError:
        st.error("Please enter valid numbers only.")
        st.stop()

# Render results only if we have them
resp = st.session_state.resp
if resp:
    if "error" in resp:
        st.error(resp["error"])
    else:
        st.success("Success!")
        st.subheader("Your Refinance Recommendation: ")

        recommendation = html.escape(resp.get("recommendation", "-")).replace("\n", "<br>")

        st.markdown(
            f"""
            <div style="
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 1.05rem;
                line-height: 1.6;
            ">
                {recommendation}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.write("")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total number of agentic tools called:", resp.get("num_tool_calls", "-"))
        with col2:
            st.caption("The agentic path this workflow took is:")
            path = resp.get("path", "-")
            if isinstance(path, list):
                st.code(" -> ".join(path))
            else:
                st.code(str(path))

# RUN: poetry run streamlit run Agentic_Refinance_Tool.py
