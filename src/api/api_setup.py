from enum import Enum
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from core.workflow import app as graph_app
from dotenv import load_dotenv
import logging
import traceback
from datetime import datetime, timezone
import os, json, time, uuid
from core.db_logging import log_event
from zoneinfo import ZoneInfo
load_dotenv()

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Refinance Advisor API", version="1.0.0")

# ----- Schemas -----
class RefiAdviceRequest(BaseModel):
    interest_rate: float = Field(..., gt=0, description="User's current mortgage interest rate (e.g., 7.125)")
    current_payment: float = Field(..., gt=0, description="User's current monthly mortgage pamyne (principal and interest only, e.g., $3,200)")
    mortgage_balance: float = Field(..., gt=0, description="User's remaining balance on mortgage (e.g., $500,000)")

class RefiAdviceResponse(BaseModel):
    recommendation: str
    market_rate: Optional[float] = None
    treasury_yield: Optional[float] = None
    num_tool_calls: int
    path: List[str]
    new_payment: Optional[float] = None
    monthly_savings: Optional[float] = None
    break_even: Optional[float] = None

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
    try:
        initial_state = {
            "interest_rate": payload.interest_rate,
            "current_payment": payload.current_payment,
            "mortgage_balance": payload.mortgage_balance,
            "treasury_yield": None,
            "market_rate": None,
            "national_rate": None,
            "local_credit_union_rate": None,
            "market_rate_source": "",
            "num_tool_calls": 0,
            "path": [],
            "new_payment": None,
            "monthly_savings": None,
            "break_even": None,
            "recommendation": "",
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
            break_even=result.get("break_even", None)
            )
        
        print("POST Request Successful!")
        
        # Log to DynamoDB
        try:
            log_event(interest_rate=payload.interest_rate,
                  current_payment=payload.current_payment,
                  mortgage_balance=payload.mortgage_balance,
                  timestamp=datetime.now(ZoneInfo("US/Eastern")).isoformat(),
                  primary_key=str(uuid.uuid4()))
            
        except Exception:
            logger.exception("DynamoDB logging failed.")

        return resp
    except Exception as e:
        #raise HTTPException(status_code=500, detail=f"Advisor failed: {e}")
        logger.error("Advisor failure:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Advisor failed: {str(e)}")

# RUN SERVER: poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload