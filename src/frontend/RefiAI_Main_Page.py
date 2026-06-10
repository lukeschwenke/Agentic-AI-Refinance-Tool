import streamlit as st
import html
from ui import apply_theme, hero, footer, fmt_pct, fmt_money, fmt_months

st.set_page_config(page_title="RefiAI", page_icon="🏡")
apply_theme()

from client import get_recommendation


def client_ip():
    """Visitor IP for the API's daily demo limit. Behind the Caddy proxy the
    direct peer is Caddy itself, so prefer the X-Forwarded-For header."""
    xff = st.context.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return st.context.ip_address

hero(
    title_html="Refi<span>AI</span>",
    subtitle=(
        "Should you refinance? A team of AI agents checks live mortgage rates, the "
        "10-year Treasury yield, and your personal break-even — then gives you a "
        "straight answer."
    ),
    pills=["🌐 National + DC-area rates", "📊 Break-even analysis", "⚡ Real-time market data"],
    badge="Live market intelligence",
)

# Ensure there is a place to store the last response
if "resp" not in st.session_state:
    st.session_state.resp = None


def clean_strings(text: str) -> str:
    return text.strip().replace("%", "").replace("$", "").replace(",", "")


def _reformat(key: str, kind: str) -> None:
    """Reformat a field's value once the user commits it (on blur/enter):
    'pct' -> 6.125%, 'money' -> $4,755.10. Leaves empty/invalid input untouched."""
    cleaned = clean_strings(st.session_state.get(key, ""))
    if not cleaned:
        return
    try:
        val = float(cleaned)
    except ValueError:
        return
    st.session_state[key] = f"{val:g}%" if kind == "pct" else f"${val:,.2f}"


# ---- Input card ----
with st.container(border=True):
    st.markdown('<div class="refi-eyebrow">Your mortgage</div>', unsafe_allow_html=True)
    st.markdown("##### Tell us about your current loan")
    rate_str = st.text_input(
        "Current mortgage interest rate (%)", placeholder="e.g., 6.125",
        key="rate_in", on_change=_reformat, args=("rate_in", "pct"),
    )
    current_payment_str = st.text_input(
        "Current monthly payment — principal & interest only", placeholder="e.g., $3,350",
        key="payment_in", on_change=_reformat, args=("payment_in", "money"),
    )
    mortgage_balance_str = st.text_input(
        "Remaining balance on your mortgage", placeholder="e.g., $500,000",
        key="balance_in", on_change=_reformat, args=("balance_in", "money"),
    )
    run = st.button("Get recommendation  →", use_container_width=True)

if run:
    if not all(s.strip() for s in (rate_str, current_payment_str, mortgage_balance_str)):
        st.error("Please fill in all three fields.")
    else:
        try:
            rate = float(clean_strings(rate_str))
            current_payment = float(clean_strings(current_payment_str))
            mortgage_balance = float(clean_strings(mortgage_balance_str))
        except ValueError:
            st.error("Please enter valid numbers only.")
            st.stop()

        with st.spinner("RefiAI agents are analyzing live market data..."):
            st.session_state.resp = get_recommendation(
                rate, current_payment, mortgage_balance, client_ip=client_ip()
            )

# ---- Results ----
resp = st.session_state.resp
if resp:
    if "error" in resp:
        st.error(resp["error"])
    else:
        st.write("")
        st.markdown('<div class="refi-eyebrow">Your recommendation</div>', unsafe_allow_html=True)
        st.markdown("#### Here's the verdict")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Effective market rate", fmt_pct(resp.get("market_rate")))
        c2.metric("New payment (est.)", fmt_money(resp.get("new_payment")))
        c3.metric("Monthly savings", fmt_money(resp.get("monthly_savings")))
        c4.metric("Break-even (mo)", fmt_months(resp.get("break_even")))

        st.write("")
        recommendation = html.escape(resp.get("recommendation", "-")).replace("\n", "<br>")
        with st.container(border=True):
            st.markdown(f'<div class="refi-reco">{recommendation}</div>', unsafe_allow_html=True)

        with st.expander("Agent run details"):
            st.metric("Agentic tool calls", resp.get("num_tool_calls", "-"))
            st.caption("The path this agentic workflow took:")
            path = resp.get("path", "-")
            st.code(" → ".join(path) if isinstance(path, list) else str(path))

footer()

# RUN: poetry run streamlit run src/frontend/RefiAI_Main_Page.py
