from core.define_state_and_llm import State
from langgraph.graph import StateGraph, END
from core.agents import *
from IPython.display import Image
from io import BytesIO
from PIL import Image as PILImage


def condition(state: State) -> str:
    if state["market_rate"] > state["interest_rate"]:
        return "END"
    else:
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

app=workflow.compile()

# Generate the visual graph
# workflow_image = None
# try:
#     png_bytes = app.get_graph().draw_mermaid_png()
#     workflow_image = PILImage.open(BytesIO(png_bytes))
# except Exception:
#     workflow_image = None