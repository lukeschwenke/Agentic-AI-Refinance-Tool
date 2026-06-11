from typing import TypedDict, List
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from core.tools import *
import os
from dotenv import load_dotenv

load_dotenv()

class State(TypedDict):
    interest_rate: float
    treasury_yield: float
    treasury_yr_low: float | None
    treasury_yr_high: float | None
    treasury_range_position: float | None
    treasury_timing_label: str
    treasury_direction: str
    mortgage_treasury_spread: float | None
    spread_label: str
    market_rate: float
    national_rate: float
    local_credit_union_rate: float
    market_rate_source: str
    num_tool_calls: int
    path: List[str]
    current_payment: float
    mortgage_balance: float
    # Optional user-provided "advanced details" (None -> derived/defaulted downstream)
    remaining_term_years: float | None
    stay_horizon_years: float | None
    closing_costs: float | None
    # Scenario/strategy outputs
    scenarios: list
    recommended_scenario_label: str
    strategy_rationale: str
    lifetime_interest_delta: float | None
    breaks_even_within_horizon: bool | None
    # Forward-looking rate outlook
    rate_outlook_label: str
    rate_outlook_summary: str
    rate_outlook_action: str
    # Primary (recommended-scenario) numbers used by the metric cards / API response
    new_payment: float | None
    monthly_savings: float | None
    break_even: float | None
    recommendation: str

llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL_NAME", "gpt-5.4-mini"),
                 api_key=os.getenv("OPENAI_API_KEY"),
                 temperature=0.1)

llm_finalizer = ChatOpenAI(model=os.getenv("OPENAI_FINALIZER_MODEL_NAME", "gpt-5.4"),
                            api_key=os.getenv("OPENAI_API_KEY"),
                            temperature=0.1)

# #Ollama Support
# llm = ChatOllama(model="gpt-oss:20b",
#                  temperature=0.1)
# Start ollam model
# OLLAMA_HOST=127.0.0.1:11435 ollama serve

llm_with_tools = llm.bind_tools([get_treasury_10yr_yield_for_agent,
                                 get_rates_search_tool_for_agent,
                                 get_rate_outlook_search_for_agent,
                                 get_local_credit_union_30yr_rate_for_agent,
                                 calculate_estimates_and_breakeven_for_agent])