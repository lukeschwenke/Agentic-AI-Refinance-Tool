from core.define_state_and_llm import State, llm, llm_finalizer
from langchain_core.prompts import PromptTemplate
import json
from core.tools import *
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Literal


def _format_scenarios_for_prompt(scenarios) -> str:
    """Render the scenario list as compact bullets for the finalizer prompt. Signed
    amounts use the same +/- formatting as the standalone variables so the LLM never
    sees an awkward '$-127,248.78'."""
    if not scenarios:
        return "(no scenarios computed)"
    lines = []
    for s in scenarios:
        be = f"{s['break_even']} mo" if s["break_even"] is not None else "n/a"
        lines.append(
            f"- {s['label']} ({s['term_years']}-yr): new payment ${s['new_payment']:,.2f}, "
            f"monthly savings ${s['monthly_savings']:,.2f}, break-even {be}, "
            f"lifetime interest change {_fmt_signed_money(s['lifetime_interest_delta'])}, "
            f"net over horizon {_fmt_signed_money(s['net_savings_over_horizon'])}"
        )
    return "\n".join(lines)

def _get_national_rate() -> float:
    """National average 30-yr rate: Tavily's answer parsed deterministically, with a
    single LLM extraction only as a fallback when no in-range number is present.
    Returns 0.0 on any failure so the source is simply ignored downstream."""
    try:
        answer = get_rates_search_tool()
    except Exception:
        return 0.0
    rate = parse_rate_from_text(answer)
    if rate:
        return rate
    try:
        resp = llm.invoke(
            f"Extract the average 30-year fixed mortgage interest rate from this text: {answer}\n"
            "Return ONLY the number with up to two decimal places (e.g. 6.32)."
        )
        return parse_rate_from_text(resp.content) or float(resp.content.strip())
    except Exception:
        return 0.0


# Agent #1
def market_expert_agent(state: State) -> dict:
    # Source 1: national average (Tavily search, parsed deterministically)
    national_rate = _get_national_rate()

    # Source 2: local credit union, Washington DC area (deterministic fetch + parse)
    try:
        local_rate = get_local_credit_union_30yr_rate()
    except Exception:
        local_rate = 0.0

    # Effective market rate = lower of the available (non-zero) sources
    market_rate, source = consolidate_rates(national_rate, local_rate)
    if market_rate > 0:
        print("===SUCCESSFULLY EXECUTED MARKET RESEARCH AGENT TOOL CALL===")

    state["national_rate"] = national_rate
    state["local_credit_union_rate"] = local_rate
    state["market_rate"] = market_rate
    state["market_rate_source"] = source
    # Count successful external data fetches only.
    state["num_tool_calls"] += int(national_rate > 0) + int(local_rate > 0)
    state["path"].append("market_expert_agent")
    return state

# Agent #2
def treasury_yield_agent(state: State) -> dict:
    """Fetches the 10-year Treasury quote (yield + 52-week high/low + prior close) and
    derives regime-relative timing signals: where the yield sits within its trailing
    52-week range, the day-over-day direction, and the mortgage-minus-Treasury spread
    vs the long-run norm. These are stored as timing/context for the finalizer, not as
    a pass/fail gate. Runs only in the CONTINUE path, so a mortgage rate is available."""
    # Spread benchmark: prefer the national average, fall back to the effective rate.
    mortgage_rate = state.get("national_rate") or state.get("market_rate") or 0.0

    fetched = False
    try:
        quote = get_treasury_10yr_quote()
        fetched = True
        print("===SUCCESSFULLY EXECUTED TREASURY YIELD AGENT TOOL CALL===")
    except Exception:
        quote = {"last": 0.0, "yr_high": None, "yr_low": None, "prev_close": None}

    timing = classify_rate_timing(
        treasury_yield=quote["last"],
        yr_high=quote["yr_high"],
        yr_low=quote["yr_low"],
        prev_close=quote["prev_close"],
        mortgage_rate=mortgage_rate,
    )

    state["treasury_yield"] = quote["last"]
    state["treasury_yr_low"] = quote["yr_low"]
    state["treasury_yr_high"] = quote["yr_high"]
    state["treasury_range_position"] = timing["range_position"]
    state["treasury_timing_label"] = timing["range_label"]
    state["treasury_direction"] = timing["direction"]
    state["mortgage_treasury_spread"] = timing["spread"]
    state["spread_label"] = timing["spread_label"]
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + int(fetched)
    state["path"].append("treasury_yield_agent")
    return state

class RateOutlookRead(BaseModel):
    """Structured classification of the rate-outlook search answer."""
    label: Literal["falling", "stable", "rising"]
    action: Literal["act", "wait", "neutral"]
    summary: str = Field(description="One short plain-English sentence a homeowner can understand.")


# Agent #2b
def rate_outlook_agent(state: State) -> dict:
    """Adds a FORWARD-looking view on top of the deterministic Treasury timing signal:
    searches recent Fed/forecaster commentary on where 30-year mortgage rates are headed,
    then has the LLM classify it into a label + action + one-sentence summary (structured
    output, so the values are guaranteed valid). Framed as timing context (not a gate).
    Degrades to 'unavailable' on any failure."""
    try:
        outlook_text = get_rate_outlook_search()
        print("===SUCCESSFULLY EXECUTED RATE OUTLOOK AGENT TOOL CALL===")
    except Exception:
        outlook_text = ""

    if not outlook_text:
        state["rate_outlook_label"] = "unavailable"
        state["rate_outlook_summary"] = ""
        state["rate_outlook_action"] = "neutral"
        state["path"].append("rate_outlook_agent")
        return state

    prompt = f"""Classify the near-term outlook for US 30-year fixed mortgage rates from the
market commentary below.

Rules:
- label = expected direction of mortgage rates over the next few months.
- action = "wait" if rates look likely to fall meaningfully, "act" if they look likely to
  rise (lock in now), otherwise "neutral".
- summary = one plain-English sentence a homeowner can understand.

Commentary:
{outlook_text}"""

    label, action, summary = "unavailable", "neutral", outlook_text.strip()[:300]
    try:
        read = llm.with_structured_output(RateOutlookRead).invoke(prompt)
        label, action, summary = read.label, read.action, read.summary or summary
    except Exception:
        pass

    state["rate_outlook_label"] = label
    state["rate_outlook_summary"] = summary
    state["rate_outlook_action"] = action
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + 1
    state["path"].append("rate_outlook_agent")
    return state

# Agent #3
def calculator_agent(state: State) -> dict:
    """Builds the standard refinance scenario set DETERMINISTICALLY (no LLM math):
    'Keep your current payoff date' (same remaining term), a 30-year reset, and a 15-year
    payoff. Resolves the remaining term (user value, else solved from the current payment,
    else 30), closing costs (quote or ~2% default), and stay-horizon (default) so the
    3-field flow still works. Seeds the 'primary' metric values from the keep-payoff
    scenario; the strategy agent overrides them with the recommended structure."""
    balance = state["mortgage_balance"]
    current_payment = state["current_payment"]
    market_rate = state["market_rate"]

    remaining_term = state.get("remaining_term_years")
    if not remaining_term:
        remaining_term = estimate_remaining_term_years(balance, current_payment, state["interest_rate"])
    if not remaining_term or remaining_term <= 0:
        remaining_term = 30.0
    state["remaining_term_years"] = round(remaining_term, 1)

    horizon = state.get("stay_horizon_years") or DEFAULT_STAY_HORIZON_YEARS
    state["stay_horizon_years"] = horizon
    closing_costs = resolve_closing_costs(state.get("closing_costs"), balance)
    state["closing_costs"] = round(closing_costs, 2)

    scenarios = build_refinance_scenarios(balance, current_payment, market_rate,
                                          remaining_term, closing_costs, horizon)
    state["scenarios"] = scenarios

    if scenarios:
        primary = scenarios[0]
        state["new_payment"] = primary["new_payment"]
        state["monthly_savings"] = primary["monthly_savings"]
        state["break_even"] = primary["break_even"]
        state["lifetime_interest_delta"] = primary["lifetime_interest_delta"]
        state["breaks_even_within_horizon"] = primary["breaks_even_within_horizon"]
        state["recommended_scenario_label"] = primary["label"]

    print("===SUCCESSFULLY EXECUTED CALCULATOR AGENT (scenarios built)===")
    state["path"].append("calculator_agent")
    return state

class StrategyPick(BaseModel):
    """Structured strategy decision over the precomputed scenarios."""
    recommended_label: str = Field(description='Exactly one of the scenario labels, or "none" if no scenario is worth doing.')
    rationale: str = Field(description="One sentence explaining the pick (or why none is viable).")


# Agent #3b
def strategy_agent(state: State) -> dict:
    """Reasons over the pre-computed scenarios + the user's stay-horizon to RECOMMEND a
    loan structure, explicitly weighing monthly savings against the lifetime-interest
    tradeoff (the term-reset trap). The math is deterministic (calculator_agent built it);
    this agent only selects and explains. One LLM call; falls back to the first scenario."""
    scenarios = state.get("scenarios") or []
    if not scenarios:
        state["path"].append("strategy_agent")
        return state

    horizon = state.get("stay_horizon_years") or DEFAULT_STAY_HORIZON_YEARS
    labels = [s["label"] for s in scenarios]
    prompt = f"""You are a mortgage refinance strategist. The numbers below are ALREADY
computed; do NOT recompute them. Pick the single best loan structure for this borrower,
or "none" if no structure is worth doing.

Borrower's current rate: {state['interest_rate']}%
Plans to keep the home for about {horizon} years.

Scenarios (JSON):
{json.dumps(scenarios, indent=2)}

Guidance:
- "monthly_savings" is the monthly P&I reduction; "lifetime_interest_delta" is the change
  in total interest over the life of the loan (POSITIVE means the refi COSTS more interest
  overall, even if the monthly payment drops -- the term-reset trap).
- "break_even" is months to recoup closing costs; it only matters if it is within the
  borrower's {horizon}-year horizon.
- Prefer a structure that lowers the monthly payment WITHOUT ballooning lifetime interest,
  unless the borrower's short horizon makes lifetime interest largely irrelevant.
- If NO scenario has positive monthly savings AND none breaks even within the horizon,
  set recommended_label to "none" — do NOT pick a least-bad option.

recommended_label must be exactly one of {labels}, or "none"."""

    chosen, rationale = scenarios[0], ""
    try:
        pick = llm.with_structured_output(StrategyPick).invoke(prompt)
        rationale = pick.rationale or ""
        if pick.recommended_label.strip().lower() == "none":
            chosen = None
        else:
            chosen = next((s for s in scenarios if s["label"] == pick.recommended_label), scenarios[0])
        print("===SUCCESSFULLY EXECUTED STRATEGY AGENT===")
    except Exception:
        pass

    if chosen is None:
        # No structure is worth doing: keep the calculator's honest seeded numbers for
        # the metric cards, but tell the finalizer nothing was viable.
        state["recommended_scenario_label"] = "none"
    else:
        state["recommended_scenario_label"] = chosen["label"]
        state["new_payment"] = chosen["new_payment"]
        state["monthly_savings"] = chosen["monthly_savings"]
        state["break_even"] = chosen["break_even"]
        state["lifetime_interest_delta"] = chosen["lifetime_interest_delta"]
        state["breaks_even_within_horizon"] = chosen["breaks_even_within_horizon"]
    state["strategy_rationale"] = rationale
    state["path"].append("strategy_agent")
    return state

# ---- Finalizer input formatting: Python formats, the LLM only narrates ----

def _fmt_money(v) -> str:
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "n/a"


def _fmt_signed_money(v) -> str:
    if not isinstance(v, (int, float)):
        return "n/a"
    sign = "+" if v > 0 else "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def _fmt_pct(v) -> str:
    if not isinstance(v, (int, float)):
        return "n/a"
    return f"{v:.3f}".rstrip("0").rstrip(".") + "%"


def _fmt_months(v) -> str:
    return f"{v:.1f} months" if isinstance(v, (int, float)) else "n/a"


def _fmt_years(v) -> str:
    return f"{v:g} years" if isinstance(v, (int, float)) else "n/a"


def _fmt_flag(v) -> str:
    return "yes" if v is True else "no" if v is False else "not evaluated"


def _decision_hint(interest_rate, market_rate) -> str:
    """Precompute the verdict branch so the LLM never does the comparison itself."""
    if not isinstance(market_rate, (int, float)) or market_rate <= 0:
        return ("RATES_UNAVAILABLE — live market rates could not be retrieved, so no analysis "
                "was performed. Tell the user to try again later; do NOT give a refinance verdict.")
    gap = interest_rate - market_rate
    if gap < 0:
        return f"DO_NOT_REFINANCE — the user's rate already beats the market by {abs(gap):.3f} points."
    if gap >= 1.0:
        return f"STRONG_REFINANCE_OPPORTUNITY — the user's rate is {gap:.3f} points above market."
    return (f"POSSIBLE_REFINANCE — the user's rate is {gap:.3f} points above market; worthwhile "
            "only if the savings/horizon numbers below support it.")


# Agent #4
def finalizer_agent(state: State) -> dict:
    """Agent finalizes the recommendation to the user based on their interest rate, the market interest rate,
    and the 10-year treasury yield value."""

    PROMPT_PATH = "src/prompts/finalizer_prompt.txt"
    FINALIZER_PROMPT = Path(PROMPT_PATH).read_text()
    
    prompt = PromptTemplate(input_variables=["decision_hint",
                                             "interest_rate",
                                             "treasury_yield",
                                             "market_rate",
                                             "current_payment",
                                             "monthly_savings",
                                             "break_even",
                                             "new_payment",
                                             "mortgage_balance",
                                             "national_rate",
                                             "local_credit_union_rate",
                                             "market_rate_source",
                                             "treasury_yr_low",
                                             "treasury_yr_high",
                                             "treasury_range_position",
                                             "treasury_timing_label",
                                             "treasury_direction",
                                             "mortgage_treasury_spread",
                                             "spread_label",
                                             "remaining_term_years",
                                             "stay_horizon_years",
                                             "scenarios_text",
                                             "recommended_scenario_label",
                                             "strategy_rationale",
                                             "lifetime_interest_delta",
                                             "breaks_even_within_horizon",
                                             "rate_outlook_label",
                                             "rate_outlook_summary",
                                             "rate_outlook_action"],
                              template=FINALIZER_PROMPT)

    # Every value is pre-formatted here so the LLM only narrates — it never has to
    # format, compare, or recompute a number (see the "$-81,933.26" class of bugs).
    spread = state['mortgage_treasury_spread']
    final_prompt = prompt.format(
        decision_hint=_decision_hint(state['interest_rate'], state['market_rate']),
        interest_rate=_fmt_pct(state['interest_rate']),
        current_payment=_fmt_money(state['current_payment']),
        mortgage_balance=_fmt_money(state['mortgage_balance']),
        market_rate=_fmt_pct(state['market_rate'] if state['market_rate'] else None),
        treasury_yield=_fmt_pct(state['treasury_yield'] if state['treasury_yield'] else None),
        monthly_savings=_fmt_money(state['monthly_savings']),
        break_even=_fmt_months(state['break_even']),
        new_payment=_fmt_money(state['new_payment']),
        national_rate=_fmt_pct(state['national_rate'] if state['national_rate'] else None),
        local_credit_union_rate=_fmt_pct(state['local_credit_union_rate'] if state['local_credit_union_rate'] else None),
        market_rate_source=state['market_rate_source'] or "unavailable",
        treasury_yr_low=_fmt_pct(state['treasury_yr_low']),
        treasury_yr_high=_fmt_pct(state['treasury_yr_high']),
        treasury_range_position=_fmt_pct(state['treasury_range_position']),
        treasury_timing_label=state['treasury_timing_label'],
        treasury_direction=state['treasury_direction'],
        mortgage_treasury_spread=(f"{spread:.2f} points" if isinstance(spread, (int, float)) else "n/a"),
        spread_label=state['spread_label'],
        remaining_term_years=_fmt_years(state.get('remaining_term_years')),
        stay_horizon_years=_fmt_years(state.get('stay_horizon_years')),
        scenarios_text=_format_scenarios_for_prompt(state.get('scenarios')),
        recommended_scenario_label=state.get('recommended_scenario_label') or "n/a",
        strategy_rationale=state.get('strategy_rationale') or "",
        lifetime_interest_delta=_fmt_signed_money(state.get('lifetime_interest_delta')),
        breaks_even_within_horizon=_fmt_flag(state.get('breaks_even_within_horizon')),
        rate_outlook_label=state.get('rate_outlook_label') or "unavailable",
        rate_outlook_summary=state.get('rate_outlook_summary') or "",
        rate_outlook_action=state.get('rate_outlook_action') or "neutral",
    )

    response = llm_finalizer.invoke(final_prompt)
    state["recommendation"] = response
    state["path"].append("finalizer_agent")
    return state