import streamlit as st
from PIL import Image as PILImage
from io import BytesIO
import traceback
from pathlib import Path
#from langchain_core.runnables.graph import MermaidDrawMethod

st.set_page_config(page_title="Agentic Workflow Details")

st.markdown("# Agentic Workflow Details")
#st.sidebar.header("Technical Details")

FRONTEND_DIR = Path(__file__).resolve().parents[1]
IMG_PATH = FRONTEND_DIR / "images" / "agentic_dag.png"

col1, col2 = st.columns(2)

with col1:
    st.markdown("""#### Agentic Workflow:""")
    st.markdown("""###### *Directed Acyclic Diagram (DAG)*""")
    # from core.workflow import workflow_image
    # if workflow_image is not None:
    #     st.image(workflow_image, width=300)
    # else:
    #     st.info("Workflow diagram unavailable (Mermaid PNG render failed).")

    from core.workflow import app
    workflow_image = None
    try:
        #png_bytes = app.get_graph().draw_mermaid_png(max_retries=5, retry_delay=2.0)
        #workflow_image = PILImage.open(BytesIO(png_bytes))
        workflow_image = IMG_PATH
        st.image(workflow_image, width=300)
    except Exception:
        st.code(traceback.format_exc())
        workflow_image = None

with col2:
    st.markdown("""#### Overview of Agents:""")
    st.markdown("""
    ###### Agent #1 - Market Expert Agent \n
    A mortgage market intelligence agent that gathers two rate signals: a national average via a Tavily web search, and a Washington DC-area rate scraped from a local credit union's published rates. It uses the lower of the two as the effective market rate that drives the recommendation.

    ###### Agent #2 - Treasury Yield Agent \n
    A financial data agent that retrieves the current U.S. 10-year Treasury yield via the CNBC REST API. The agent evaluates the yield relative to predefined desirability thresholds and provides contextual guidance that informs the final recommendation.
    
    ###### Agent #3 - Calculator Agent \n
    A financial calculation agent that computes the refinance breakeven period using user-provided and estimated loan data. Inputs include the user’s current monthly principal-and-interest (P&I) payment and an estimated post-refinance P&I payment. The agent calculates monthly savings, estimates closing costs, and determines the breakeven horizon as: Estimated Closing Costs ÷ Monthly Payment Savings
    
    ###### Agent #4 - Finalizer Agent \n
    A terminal agent that synthesizes outputs from the market-rate, treasury-yield, and breakeven-calculation agents to generate a concise refinance recommendation. It reports both the national and Washington DC-area rates and states which one (the lower) drove the calculations, tailored to the user’s current rate and prevailing market conditions.
    """)

st.write("""
         Agent Code: https://github.com/lukeschwenke/Agentic-AI/blob/main/src/core/agents.py
         \nTools Code: https://github.com/lukeschwenke/Agentic-AI/blob/main/src/core/tools.py
""")