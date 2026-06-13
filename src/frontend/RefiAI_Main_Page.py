import streamlit as st
import streamlit.components.v1 as components
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
    pills=["National + DC-area rates", "Break-even analysis", "Real-time market data"],
    badge="Live market intelligence",
)

# Ensure there is a place to store the last response
if "resp" not in st.session_state:
    st.session_state.resp = None


def clean_strings(text: str) -> str:
    return text.strip().replace("%", "").replace("$", "").replace(",", "")


def colorize_verdict(md: str) -> str:
    """Tint the opening verdict line and the 'Bottom line:' in the theme's primary
    (emerald) color using Streamlit's :primary[...] markdown directive."""
    lines = md.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if s:
            lines[i] = f":primary[{s}]"
            break
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("**Bottom line") or s.startswith("Bottom line"):
            lines[i] = f":primary[{s}]"
    return "\n".join(lines)


def fmt_signed_money(v) -> str:
    """Money with an explicit +/− so the lifetime-interest direction reads at a glance."""
    if not isinstance(v, (int, float)):
        return "—"
    sign = "+" if v > 0 else "−" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


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

    with st.expander("Advanced details"):
        st.caption("Leave any field blank and we'll use a sensible default.")
        term_str = st.text_input(
            "Years left on your current loan", placeholder="e.g., 24 (we'll estimate if blank)",
            key="term_in",
        )
        horizon_str = st.text_input(
            "How long you'll keep the home (years)", placeholder="e.g., 7 (default)",
            key="horizon_in",
        )
        closing_str = st.text_input(
            "Estimated closing costs", placeholder="e.g., $9,000 (defaults to ~2% of balance)",
            key="closing_in", on_change=_reformat, args=("closing_in", "money"),
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
            remaining_term_years = float(clean_strings(term_str)) if term_str.strip() else None
            stay_horizon_years = float(clean_strings(horizon_str)) if horizon_str.strip() else None
            closing_costs = float(clean_strings(closing_str)) if closing_str.strip() else None
        except ValueError:
            st.error("Please enter valid numbers only.")
            st.stop()

        # Soft sanity checks: warn about likely typos but never block the request.
        if not 1.0 <= rate <= 15.0:
            st.warning(f"A {rate:g}% rate is unusual — most mortgage rates fall between 2% and 10%. Double-check it.")
        if mortgage_balance < 10_000:
            st.warning("That balance looks low — double-check you entered the full remaining amount.")
        elif current_payment <= mortgage_balance * (rate / 100) / 12:
            st.warning(
                "That payment doesn't cover the monthly interest at this rate, so parts of the "
                "estimate may be off. Double-check the payment (principal & interest only)."
            )

        with st.spinner("Checking live rates, Treasury data, and the rate outlook — usually 20–40 seconds..."):
            st.session_state.resp = get_recommendation(
                rate, current_payment, mortgage_balance, client_ip=client_ip(),
                remaining_term_years=remaining_term_years,
                stay_horizon_years=stay_horizon_years,
                closing_costs=closing_costs,
            )
        # Scroll to the results once, on the rerun that first shows them.
        st.session_state.scroll_to_results = True

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
        c4.metric("Break-even", fmt_months(resp.get("break_even")))

        # Show exactly what the math assumed, flagging anything that was defaulted or
        # derived rather than typed in (the inputs persist in session_state by key).
        rt, sh, cc = resp.get("remaining_term_years"), resp.get("stay_horizon_years"), resp.get("closing_costs")
        if isinstance(rt, (int, float)) and isinstance(sh, (int, float)) and isinstance(cc, (int, float)):
            term_given = bool(st.session_state.get("term_in", "").strip())
            horizon_given = bool(st.session_state.get("horizon_in", "").strip())
            closing_given = bool(st.session_state.get("closing_in", "").strip())
            st.caption(
                f"Assumes {fmt_money(cc)} in closing costs{'' if closing_given else ' (2% default)'}, "
                f"{rt:g} years left on your loan{'' if term_given else ' (estimated from your payment)'}, "
                f"and a {sh:g}-year stay{'' if horizon_given else ' (default)'}. "
                "Open Advanced details to adjust these."
            )

        outlook = resp.get("rate_outlook_label")
        if outlook and outlook != "unavailable":
            summary = resp.get("rate_outlook_summary") or ""
            st.caption(f"Rate outlook: **{outlook}** — {summary}")

        st.write("")
        # Render the LLM's Markdown (bold/bullets/headers). Escape $ so Streamlit doesn't
        # treat dollar amounts as LaTeX math. st.markdown sanitizes raw HTML by default.
        recommendation = colorize_verdict(resp.get("recommendation", "-").replace("$", "\\$"))
        with st.container(border=True):
            st.markdown(recommendation)

        if st.session_state.pop("scroll_to_results", False):
            # components.html runs in an iframe, so reach the parent document to
            # scroll the freshly rendered verdict into view.
            components.html(
                """
                <script>
                setTimeout(function () {
                    const doc = window.parent.document;
                    for (const h of doc.querySelectorAll("h4")) {
                        if (h.innerText.includes("Here's the verdict")) {
                            h.scrollIntoView({behavior: "smooth", block: "start"});
                            break;
                        }
                    }
                }, 300);
                </script>
                """,
                height=0,
            )

        # ---- Loan structures compared ----
        scenarios = resp.get("scenarios") or []
        if scenarios:
            rec_label = resp.get("recommended_scenario_label")
            st.write("")
            st.markdown('<div class="refi-eyebrow">Loan structures compared</div>', unsafe_allow_html=True)
            rows = []
            for s in scenarios:
                be = s.get("break_even")
                label = str(s.get("label", ""))
                if s.get("label") == rec_label:
                    label += "  ·  Recommended"
                rows.append({
                    "Structure": label,
                    "Term": f"{s.get('term_years', 0):g} yr",
                    "New payment": fmt_money(s.get("new_payment")),
                    "Monthly savings": fmt_money(s.get("monthly_savings")),
                    "Break-even": f"{be:.0f} mo" if isinstance(be, (int, float)) else "—",
                    "Lifetime interest change": fmt_signed_money(s.get("lifetime_interest_delta")),
                })
            st.dataframe(rows, hide_index=True, use_container_width=True)
            st.caption(
                "**Lifetime interest change**: **+** means the refi adds total interest over the "
                "loan's life (even if the monthly payment drops); **−** means it saves interest too."
            )

        with st.expander("Agent run details"):
            FRIENDLY_STEPS = {
                "market_expert_agent": "Market rates",
                "treasury_yield_agent": "Treasury context",
                "rate_outlook_agent": "Rate outlook",
                "calculator_agent": "Scenario math",
                "strategy_agent": "Strategy",
                "finalizer_agent": "Final write-up",
                "verifier_agent": "Self-check",
            }
            path = resp.get("path", [])
            labels = [FRIENDLY_STEPS.get(p, p) for p in path] if isinstance(path, list) else [str(path)]
            # Collapse consecutive repeats (a verifier retry re-runs write-up + self-check).
            steps = [lbl for i, lbl in enumerate(labels) if i == 0 or lbl != labels[i - 1]]
            st.caption("The steps the agents took:")
            st.code(" → ".join(steps))
            passed = resp.get("verifier_passed")
            check = "passed" if passed else "flagged" if passed is False else "—"
            st.caption(f"Live data fetches: {resp.get('num_tool_calls', '-')}  ·  Self-check: {check}")

footer()

# RUN: poetry run streamlit run src/frontend/RefiAI_Main_Page.py
