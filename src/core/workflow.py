from core.define_state_and_llm import State
from langgraph.graph import StateGraph, END
from core.agents import *


def route_after_market(state: State):
    market_rate = state["market_rate"] or 0.0
    # Nothing valid to analyze (both rate sources failed, or the user's rate already
    # beats the market) -> skip straight to the finalizer rather than computing against
    # a useless market rate. Otherwise fan OUT to the two independent context fetches.
    if market_rate <= 0 or market_rate > state["interest_rate"]:
        return "finalizer"
    return ["treasury_yield", "rate_outlook"]

workflow = StateGraph(State)
workflow.add_node("market", market_expert_agent)
workflow.add_node("treasury_yield", treasury_yield_agent)
workflow.add_node("rate_outlook", rate_outlook_agent)
workflow.add_node("calculator", calculator_agent)
workflow.add_node("strategy", strategy_agent)
workflow.add_node("finalizer", finalizer_agent)
workflow.add_node("verifier", verifier_agent)

workflow.set_entry_point("market")
# treasury_yield and rate_outlook are independent, so they run in PARALLEL and fan back
# in at the calculator (which waits for both).
workflow.add_conditional_edges("market", route_after_market,
                               ["treasury_yield", "rate_outlook", "finalizer"])
workflow.add_edge("treasury_yield", "calculator")
workflow.add_edge("rate_outlook", "calculator")
workflow.add_edge("calculator", "strategy")
workflow.add_edge("strategy", "finalizer")
# Every finalizer draft is checked by the verifier (LLM-as-judge), which either ends the
# run or sends it back to the finalizer once with feedback.
workflow.add_edge("finalizer", "verifier")
workflow.add_conditional_edges("verifier", verifier_route, {"finalizer": "finalizer", "END": END})

app = workflow.compile()