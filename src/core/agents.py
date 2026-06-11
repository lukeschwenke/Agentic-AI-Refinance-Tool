from core.define_state_and_llm import State, llm, llm_finalizer, llm_with_tools
from langchain_core.prompts import PromptTemplate
import json
from core.tools import *
from langgraph.prebuilt import ToolNode
from pathlib import Path

tool_nodes = ToolNode([get_treasury_10yr_yield_for_agent,
                       get_rates_search_tool_for_agent,
                       get_rate_outlook_search_for_agent,
                       get_local_credit_union_30yr_rate_for_agent,
                       calculate_estimates_and_breakeven_for_agent])


def _extract_json(text: str) -> str:
    """Pull the first JSON object out of an LLM response, tolerating ```json fences."""
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end != -1 else text


def _format_scenarios_for_prompt(scenarios) -> str:
    """Render the scenario list as compact bullets for the finalizer prompt."""
    if not scenarios:
        return "(no scenarios computed)"
    lines = []
    for s in scenarios:
        be = f"{s['break_even']} mo" if s["break_even"] is not None else "n/a"
        lines.append(
            f"- {s['label']} ({s['term_years']}-yr): new payment ${s['new_payment']:,.2f}, "
            f"monthly savings ${s['monthly_savings']:,.2f}, break-even {be}, "
            f"lifetime interest change ${s['lifetime_interest_delta']:,.2f}, "
            f"net over horizon ${s['net_savings_over_horizon']:,.2f}"
        )
    return "\n".join(lines)

def _get_national_rate_via_tavily() -> float:
    """National average via Tavily search + a follow-on LLM numeric extraction.
    Returns 0.0 on any failure so the source can be ignored downstream."""
    prompt = PromptTemplate(template="""
                            You are a mortgage market expert. You should summarize some recent articles to get
                            an average mortgage interest rate people are seeing right now by
                            calling the `get_rates_search_tool_for_agent`.
                            """)
    try:
        resp = llm_with_tools.invoke(prompt.format())
        if not resp.tool_calls:
            return 0.0
        tool_result = tool_nodes.invoke({"messages": [resp]})
        message = tool_result["messages"][0].content
        follow_on_prompt = f"""Extract the average mortgage interest rate value from this body of text: {message}
                              You must ONLY return the numerical value up to two decimal places.
                              Example answer: 5.32"""
        updated_resp = llm.invoke(follow_on_prompt)
        return float(updated_resp.content)
    except Exception:
        return 0.0


# Agent #1
def market_expert_agent(state: State) -> dict:
    # Source 1: national average (Tavily search + LLM extraction)
    national_rate = _get_national_rate_via_tavily()

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
    state["num_tool_calls"] += 2
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

    try:
        quote = get_treasury_10yr_quote()
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
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + 1
    state["path"].append("treasury_yield_agent")
    return state

# Agent #2b
def rate_outlook_agent(state: State) -> dict:
    """Adds a FORWARD-looking view on top of the deterministic Treasury timing signal:
    searches recent Fed/forecaster commentary on where 30-year mortgage rates are headed,
    then has the LLM classify it into a label + action + one-sentence summary. Framed as
    timing context (not a gate). Degrades to 'unavailable' on any failure."""
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
market commentary below. Respond with ONLY valid JSON:
{{"label": "falling|stable|rising", "action": "act|wait|neutral", "summary": "<one short sentence>"}}

Rules:
- label = expected direction of mortgage rates over the next few months.
- action = "wait" if rates look likely to fall meaningfully, "act" if they look likely to
  rise (lock in now), otherwise "neutral".
- summary = one plain-English sentence a homeowner can understand.

Commentary:
{outlook_text}"""

    label, action, summary = "unavailable", "neutral", outlook_text.strip()[:300]
    try:
        resp = llm.invoke(prompt)
        data = json.loads(_extract_json(resp.content))
        label = (data.get("label") or "unavailable")
        action = (data.get("action") or "neutral")
        summary = (data.get("summary") or summary)
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
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + 1
    state["path"].append("calculator_agent")
    return state

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
computed; do NOT recompute them. Pick the single best loan structure for this borrower.

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

Respond with ONLY valid JSON:
{{"recommended_label": "<one of: {labels}>", "rationale": "<one sentence>"}}"""

    chosen, rationale = scenarios[0], ""
    try:
        resp = llm.invoke(prompt)
        data = json.loads(_extract_json(resp.content))
        rationale = data.get("rationale", "") or ""
        match = next((s for s in scenarios if s["label"] == data.get("recommended_label")), None)
        if match:
            chosen = match
        print("===SUCCESSFULLY EXECUTED STRATEGY AGENT===")
    except Exception:
        pass

    state["recommended_scenario_label"] = chosen["label"]
    state["strategy_rationale"] = rationale
    state["new_payment"] = chosen["new_payment"]
    state["monthly_savings"] = chosen["monthly_savings"]
    state["break_even"] = chosen["break_even"]
    state["lifetime_interest_delta"] = chosen["lifetime_interest_delta"]
    state["breaks_even_within_horizon"] = chosen["breaks_even_within_horizon"]
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + 1
    state["path"].append("strategy_agent")
    return state

# Agent #4
def finalizer_agent(state: State) -> dict:
    """Agent finalizes the recommendation to the user based on their interest rate, the market interest rate, 
    and the 10-year treasury yield value."""

    PROMPT_PATH = "src/prompts/finalizer_prompt.txt"
    FINALIZER_PROMPT = Path(PROMPT_PATH).read_text()
    
    prompt = PromptTemplate(input_variables=["interest_rate",
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
                            # template="""You are a mortgage refinance expert who should make the final recommendation 
                            # to the user if they should refinance or not. You should make your recommendation within 5-8
                            # sentences. Keep your response concise and to the point.

                            # # FORMAT:
                            # Ensure all dollar values are formatting properly with a dollar sign and commans (e.g., $7,124.32)

                            # # IMPORTANT!
                            # If the user interest rate ({interest_rate}) is lower than the market rate ({market_rate})
                            # then tell them they should NOT refinance right now since their rate is already LOWER than the market rate.
                            # If the user interest rate ({interest_rate}) is higher than the market rate ({market_rate}), continue:

                            # # INTEREST RATE CHECK
                            # Otherwise, tell them now may be a good time to refinance since their rate of {interest_rate} 
                            # is higher than the market rate of {market_rate}. If the market rate ({market_rate}) 
                            # is more than 1.0 percent lower than the user's interest rate ({interest_rate}) then let 
                            # them know it is a good time to refinance.
                            
                            # # TREASURY YIELD CHECK
                            # If the {treasury_yield} is below 4.0 then let the user know and inform them this is a good
                            # indicator to refinance. If the {treasury_yield} is above 4.0 then let the user know they should consider waiting for the treasury
                            # yield to come down more. Let them know it is an Excellent time to refinance if the
                            # treasury yield is below 4.0 and the market rate ({market_rate}) is 1.0 percent lower then their interest rate ({interest_rate}).
                            # You MUST tell the user what the current treasury yield value is by reporting this number ({treasury_yield}) as a percent (e.g., 4.102%). 
                            # If the {treasury_yield} value is 0 or 0.0 tell the user you did not check this value since their interest rate is better than the market rate.
                            # You MUST tell the user what the current market rate is by reporting this number ({market_rate}) as a percent (e.g., 6.125%).

                            # # CALCULATION REPORTING
                            # You MUST inform the user that you calculated their estimated monthly savings by taking their monthly Principal and Interest payment ({current_payment})
                            # and subtracting their estimated new payment ({new_payment}) to come up with their savings of {monthly_savings}.
                            # You MUST inform the user you estimated their new payment with a 30-year loan, the average market interest rate of {market_rate}, and a
                            # loan value that is their remaining mortgage balance ({mortgage_balance}).

                            # # GENERAL INFO
                            # In general, a market rate that is lower than the user's interest rate indicates refinancing is good but it is best to target a market rate
                            # that is 1.0 percent or more lower. If the {market_rate} is higher than the user's {interest_rate} that means refinancing is a bad option.
                            # All numbers you report should NOT be more than 3 decimal places (e.g. 7.125).
                            # """)
    
    final_prompt = prompt.format(
        interest_rate=state['interest_rate'],
        current_payment=state['current_payment'],
        mortgage_balance=state['mortgage_balance'],
        market_rate=state['market_rate'],
        treasury_yield=state['treasury_yield'],
        monthly_savings=state['monthly_savings'],
        break_even=state['break_even'],
        new_payment=state['new_payment'],
        national_rate=state['national_rate'],
        local_credit_union_rate=state['local_credit_union_rate'],
        market_rate_source=state['market_rate_source'],
        treasury_yr_low=state['treasury_yr_low'],
        treasury_yr_high=state['treasury_yr_high'],
        treasury_range_position=state['treasury_range_position'],
        treasury_timing_label=state['treasury_timing_label'],
        treasury_direction=state['treasury_direction'],
        mortgage_treasury_spread=state['mortgage_treasury_spread'],
        spread_label=state['spread_label'],
        remaining_term_years=state.get('remaining_term_years'),
        stay_horizon_years=state.get('stay_horizon_years'),
        scenarios_text=_format_scenarios_for_prompt(state.get('scenarios')),
        recommended_scenario_label=state.get('recommended_scenario_label') or "n/a",
        strategy_rationale=state.get('strategy_rationale') or "",
        lifetime_interest_delta=state.get('lifetime_interest_delta'),
        breaks_even_within_horizon=state.get('breaks_even_within_horizon'),
        rate_outlook_label=state.get('rate_outlook_label') or "unavailable",
        rate_outlook_summary=state.get('rate_outlook_summary') or "",
        rate_outlook_action=state.get('rate_outlook_action') or "neutral",
    )

    response = llm_finalizer.invoke(final_prompt)
    state["recommendation"] = response
    state["path"].append("finalizer_agent")
    return state