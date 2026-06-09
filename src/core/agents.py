from core.define_state_and_llm import State, llm, llm_finalizer, llm_with_tools
from langchain_core.prompts import PromptTemplate
import json
from core.tools import *
from langgraph.prebuilt import ToolNode
from pathlib import Path

tool_nodes = ToolNode([get_treasury_10yr_yield_for_agent,
                       get_rates_search_tool_for_agent,
                       get_local_credit_union_30yr_rate_for_agent,
                       calculate_estimates_and_breakeven_for_agent])

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

# Agent #3
def calculator_agent(state: State) -> dict:
    """Agent intakes the user's current principal and interest payment as well as a calculated estimated principal 
    and interest payment based their loan amount. The agent will get a difference in payment (savings) between the current
    and estimated payment. The estimated closing costs will also be calculated. The estimated closing costs divided by savings is the break even
    calculation that will be displayed."""

    prompt = PromptTemplate(
    input_variables=["current_payment", "mortgage_balance", "market_rate"],
    template="""
    You are an expert on calculating new mortgage payments and break-even points.

    You MUST call the tool `calculate_estimates_and_breakeven_for_agent` 
    and pass it exactly these three arguments:

    - current_payment: {current_payment}
    - mortgage_balance: {mortgage_balance}
    - market_rate: {market_rate}

    Your ONLY job is to call the tool with:

    {{
        "current_payment": {current_payment},
        "mortgage_balance": {mortgage_balance},
        "market_rate": {market_rate}
    }}

    After the tool returns, output ONLY valid JSON of the form:
    {{
        "new_payment": <float>,
        "monthly_savings": <float>,
        "break_even": <float>
    }}
    """
    )
    final_prompt = prompt.invoke({
        "current_payment": state['current_payment'],
        "mortgage_balance": state['mortgage_balance'],
        "market_rate": state['market_rate']
        })
    
    resp = llm_with_tools.invoke(final_prompt)

    # Check if LLM wants to call tools
    if resp.tool_calls:
        # Execute the call to tool
        tool_result = tool_nodes.invoke({"messages": [resp]})
        values = json.loads(tool_result["messages"][0].content)
        print("===SUCCESSFULLY EXECUTED CALCULATOR AGENT TOOL CALL===")
    else:
        values=[0,0,0]

    state['new_payment'] = values[0]
    state['monthly_savings'] = values[1]
    state['break_even'] = values[2]
    state["num_tool_calls"] = state.get("num_tool_calls", 0) + 1
    state["path"].append("calculator_agent")
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
                                             "spread_label"],
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
    )

    response = llm_finalizer.invoke(final_prompt)
    state["recommendation"] = response
    state["path"].append("finalizer_agent")
    return state