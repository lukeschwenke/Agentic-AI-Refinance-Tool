from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from core.workflow import app as graph_app
from dotenv import load_dotenv
import logging
import traceback
from datetime import datetime
import uuid
from core.db_logging import (
    log_event,
    increment_ip_usage,
    increment_global_usage,
    DAILY_IP_LIMIT,
    DAILY_GLOBAL_LIMIT,
)
from zoneinfo import ZoneInfo
load_dotenv()

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Refinance Advisor API", version="1.0.0")

# ----- Schemas -----
class RefiAdviceRequest(BaseModel):
    interest_rate: float = Field(..., gt=0, description="User's current mortgage interest rate (e.g., 7.125)")
    current_payment: float = Field(..., gt=0, description="User's current monthly mortgage pamyne (principal and interest only, e.g., $3,200)")
    mortgage_balance: float = Field(..., gt=0, description="User's remaining balance on mortgage (e.g., $500,000)")
    client_ip: Optional[str] = Field(None, description="End-user IP forwarded by the UI; used for the daily demo rate limit")
    # Optional "advanced details" — defaulted/derived downstream when omitted, so the
    # 3-field flow (and the daily Lambda) keep working unchanged.
    remaining_term_years: Optional[float] = Field(None, gt=0, description="Years left on the current loan (derived from payment/balance/rate if omitted)")
    stay_horizon_years: Optional[float] = Field(None, gt=0, description="How long the user plans to keep the home (years)")
    closing_costs: Optional[float] = Field(None, gt=0, description="Estimated refinance closing costs in dollars (defaults to ~2% of balance)")

class RefiAdviceResponse(BaseModel):
    recommendation: str
    market_rate: Optional[float] = None
    treasury_yield: Optional[float] = None
    num_tool_calls: int
    path: List[str]
    new_payment: Optional[float] = None
    monthly_savings: Optional[float] = None
    break_even: Optional[float] = None
    scenarios: List[dict] = []
    recommended_scenario_label: Optional[str] = None
    lifetime_interest_delta: Optional[float] = None
    rate_outlook_label: Optional[str] = None
    rate_outlook_summary: Optional[str] = None
    rate_outlook_action: Optional[str] = None
    # Resolved assumptions (user-provided or defaulted/derived by the calculator),
    # echoed back so the UI can show exactly what the math assumed.
    remaining_term_years: Optional[float] = None
    stay_horizon_years: Optional[float] = None
    closing_costs: Optional[float] = None
    verifier_passed: Optional[bool] = None

# ----- Helpers -----
def extract_text(value) -> str:
    """Safely turn LangChain objects (AIMessage, str, etc.) into a string."""
    if value is None:
        return ""
    # AIMessage has .content; plain strings do not
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(value, str):
        return value
    return str(value)

# ----- Routes -----
@app.post("/refinance_agent/recommendation", response_model=RefiAdviceResponse)
def return_advice_recommendation(payload: RefiAdviceRequest):
    # Daily demo limits, applied to UI traffic only (requests carrying a
    # client_ip) so the scheduled Lambda is never locked out. Per-IP is
    # checked first so a blocked IP can't burn the global budget. Checked
    # outside the try below so the 429 isn't swallowed and re-raised as a
    # 500. If DynamoDB is unreachable we fail open rather than lock
    # visitors out.
    if payload.client_ip:
        try:
            used_today = increment_ip_usage(payload.client_ip)
        except Exception:
            logger.exception("Rate-limit check failed; allowing request.")
            used_today = None
        if used_today is not None and used_today > DAILY_IP_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Demo limit reached: this demo allows {DAILY_IP_LIMIT} "
                    "recommendations per visitor per day. Please come back tomorrow!"
                ),
            )

        try:
            global_today = increment_global_usage()
        except Exception:
            logger.exception("Global rate-limit check failed; allowing request.")
            global_today = None
        if global_today is not None and global_today > DAILY_GLOBAL_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=(
                    "The demo is at capacity for today — it allows "
                    f"{DAILY_GLOBAL_LIMIT} recommendations per day across all "
                    "visitors. Please come back tomorrow!"
                ),
            )

    try:
        initial_state = {
            "interest_rate": payload.interest_rate,
            "current_payment": payload.current_payment,
            "mortgage_balance": payload.mortgage_balance,
            "remaining_term_years": payload.remaining_term_years,
            "stay_horizon_years": payload.stay_horizon_years,
            "closing_costs": payload.closing_costs,
            "treasury_yield": None,
            "treasury_yr_low": None,
            "treasury_yr_high": None,
            "treasury_range_position": None,
            "treasury_timing_label": "unavailable",
            "treasury_direction": "unavailable",
            "mortgage_treasury_spread": None,
            "spread_label": "unavailable",
            "market_rate": None,
            "national_rate": None,
            "local_credit_union_rate": None,
            "market_rate_source": "",
            "num_tool_calls": 0,
            "path": [],
            "scenarios": [],
            "recommended_scenario_label": "",
            "strategy_rationale": "",
            "lifetime_interest_delta": None,
            "breaks_even_within_horizon": None,
            "rate_outlook_label": "unavailable",
            "rate_outlook_summary": "",
            "rate_outlook_action": "neutral",
            "new_payment": None,
            "monthly_savings": None,
            "break_even": None,
            "recommendation": "",
            "verifier_passed": True,
            "verifier_feedback": "",
            "verifier_attempts": 0,
        }

        result = graph_app.invoke(initial_state)

        resp = RefiAdviceResponse(
            recommendation=extract_text(result.get("recommendation")),
            market_rate=result.get("market_rate"),
            treasury_yield=result.get("treasury_yield"),
            num_tool_calls=int(result.get("num_tool_calls", 0)),
            path=list(result.get("path", [])),
            new_payment=result.get("new_payment", None),
            monthly_savings=result.get("monthly_savings", None),
            break_even=result.get("break_even", None),
            scenarios=list(result.get("scenarios", []) or []),
            recommended_scenario_label=result.get("recommended_scenario_label") or None,
            lifetime_interest_delta=result.get("lifetime_interest_delta", None),
            rate_outlook_label=result.get("rate_outlook_label") or None,
            rate_outlook_summary=result.get("rate_outlook_summary") or None,
            rate_outlook_action=result.get("rate_outlook_action") or None,
            remaining_term_years=result.get("remaining_term_years", None),
            stay_horizon_years=result.get("stay_horizon_years", None),
            closing_costs=result.get("closing_costs", None),
            verifier_passed=result.get("verifier_passed", None),
            )
        
        print("POST Request Successful!")
        
        # Log to DynamoDB
        try:
            log_event(interest_rate=payload.interest_rate,
                  current_payment=payload.current_payment,
                  mortgage_balance=payload.mortgage_balance,
                  timestamp=datetime.now(ZoneInfo("US/Eastern")).isoformat(),
                  primary_key=str(uuid.uuid4()),
                  ip=payload.client_ip)
            
        except Exception:
            logger.exception("DynamoDB logging failed.")

        return resp
    except Exception as e:
        #raise HTTPException(status_code=500, detail=f"Advisor failed: {e}")
        logger.error("Advisor failure:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Advisor failed: {str(e)}")

# RUN SERVER: poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload