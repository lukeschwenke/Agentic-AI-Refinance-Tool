import os
import requests
from dotenv import load_dotenv
from typing import TypedDict, Optional
from api.api_setup import RefiAdviceRequest, RefiAdviceResponse

load_dotenv()

# API_BASE_URL = os.getenv("API_BASE_URL")
# API_PORT = os.getenv("API_PORT")
# API_NAME = os.getenv("API_PATH")
# FULL_API_URL = f"{str(API_BASE_URL)}:{str(API_PORT)}/{str(API_NAME)}"

API_BASE_URL = (os.getenv("API_BASE_URL") or "http://127.0.0.1").rstrip("/")
API_PORT = (os.getenv("API_PORT") or "8000").strip()
API_PATH = (os.getenv("API_PATH") or "refinance_agent/recommendation/").lstrip("/")

# If API_BASE_URL already includes a port, don't append API_PORT
if "://" in API_BASE_URL and API_BASE_URL.rsplit(":", 1)[-1].isdigit():
    FULL_API_URL = f"{API_BASE_URL}/{API_PATH}"
else:
    FULL_API_URL = f"{API_BASE_URL}:{API_PORT}/{API_PATH}"

def get_recommendation(interest_rate: float,
                       current_payment: float,
                       mortgage_balance: float,
                       client_ip: Optional[str] = None,
                       remaining_term_years: Optional[float] = None,
                       stay_horizon_years: Optional[float] = None,
                       closing_costs: Optional[float] = None) -> RefiAdviceResponse:

    data_payload = RefiAdviceRequest(interest_rate=interest_rate,
                                     current_payment=current_payment,
                                     mortgage_balance=mortgage_balance,
                                     client_ip=client_ip,
                                     remaining_term_years=remaining_term_years,
                                     stay_horizon_years=stay_horizon_years,
                                     closing_costs=closing_costs).model_dump()

    try:
        response = requests.post(FULL_API_URL, json=data_payload, timeout=90)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = None
        return {"error": detail or f"HTTP {response.status_code}: {response.text if response is not None else e}"}
    except Exception as e:
        return {"error": str(e)}
    