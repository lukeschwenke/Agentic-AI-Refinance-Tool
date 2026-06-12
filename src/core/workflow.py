from core.define_state_and_llm import State
from langgraph.graph import StateGraph, END
from core.agents import *


def condition(state: State) -> str:
    market_rate = state["market_rate"] or 0.0
    # Both rate sources failed: there is nothing valid to analyze, so skip straight
    # to the finalizer (which reports that live rates couldn't be retrieved) instead
    # of letting the calculator build scenarios against a 0% market rate.
    if market_rate <= 0:
        return "END"
    if market_rate > state["interest_rate"]:
        return "END"
    return "CONTINUE"

workflow = StateGraph(State)
workflow.add_node("market", market_expert_agent)
workflow.add_node("treasury_yield", treasury_yield_agent)
workflow.add_node("rate_outlook", rate_outlook_agent)
workflow.add_node("calculator", calculator_agent)
workflow.add_node("strategy", strategy_agent)
workflow.add_node("finalizer", finalizer_agent)

workflow.set_entry_point("market")
workflow.add_conditional_edges("market", condition, {"CONTINUE": "treasury_yield",
                                                     "END": "finalizer"})
# CONTINUE path: deterministic Treasury signal -> forward-looking outlook -> scenario
# math -> strategy pick -> finalizer.
workflow.add_edge("treasury_yield", "rate_outlook")
workflow.add_edge("rate_outlook", "calculator")
workflow.add_edge("calculator", "strategy")
workflow.add_edge("strategy", "finalizer")
workflow.add_edge("finalizer", END)

app = workflow.compile()