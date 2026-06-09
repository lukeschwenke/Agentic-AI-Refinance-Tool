import re
import requests
from langchain_core.tools import tool
from tavily import TavilyClient
import os
from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()

TREASURY_QUOTE_URL = "https://quote.cnbc.com/quote-html-webservice/quote.htm"
TREASURY_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.5993.89 Safari/537.36"
)

# --- Treasury timing thresholds (tunable; see the treasury-timing spec) ---
NORMAL_SPREAD = 1.75          # long-run mortgage-minus-10yr spread (percentage points)
SPREAD_BAND = 0.35            # normal band = NORMAL_SPREAD +/- this
RANGE_FAVORABLE_MAX = 33      # range_position < 33 -> favorable (near 12-mo low)
RANGE_ELEVATED_MIN = 66       # range_position > 66 -> elevated (near 12-mo high)
DIRECTION_FLAT_BAND = 0.03    # |last - prev_close| < this -> flat

TIMING_FAVORABLE = "favorable"
TIMING_NEUTRAL = "neutral"
TIMING_ELEVATED = "elevated"
SPREAD_WIDE = "wide"
SPREAD_NORMAL = "normal"
SPREAD_TIGHT = "tight"
UNAVAILABLE = "unavailable"


def _to_float(value) -> float:
    """Parse a CNBC numeric string (which may carry a trailing %) into a float."""
    return float(str(value).strip().rstrip("%"))


def _is_pos(v) -> bool:
    return isinstance(v, (int, float)) and v > 0


#@tool
def get_treasury_10yr_quote() -> dict:
    """Fetch the 10-year Treasury quote from CNBC.

    Returns {"last", "yr_high", "yr_low", "prev_close"} as floats. `last` is
    required (raises ValueError if the payload is malformed); the 52-week high/low
    and previous close degrade to None if absent, so the plain yield fetch and the
    timing classifier can still work with partial data.
    """
    params = {
        "noform": "1", "partnerId": "2", "fund": "1", "exthrs": "0",
        "output": "json", "symbols": "US10Y",
    }
    resp = requests.get(TREASURY_QUOTE_URL, params=params,
                        headers={"User-Agent": TREASURY_USER_AGENT}, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    try:
        quote = data["QuickQuoteResult"]["QuickQuote"][0]
        last = _to_float(quote["last"])
    except Exception as e:
        raise ValueError(f"Unexpected CNBC payload shape or symbol missing: {e}") from e

    fundamentals = quote.get("FundamentalData") or {}

    def _opt(d, key):
        try:
            return _to_float(d[key])
        except Exception:
            return None

    return {
        "last": last,
        "yr_high": _opt(fundamentals, "yrhiprice"),
        "yr_low": _opt(fundamentals, "yrloprice"),
        "prev_close": _opt(quote, "previous_day_closing"),
    }


#@tool
def get_treasury_10yr_yield() -> float:
    """Gets the 10 year treasury yield value (the latest yield)."""
    return get_treasury_10yr_quote()["last"]


def classify_rate_timing(treasury_yield, yr_high, yr_low, prev_close, mortgage_rate) -> dict:
    """Turn the raw treasury + mortgage numbers into timing/context signals.

    Returns: range_position (0-100), range_label (favorable/neutral/elevated),
    direction (rising/falling/flat), spread (mortgage - 10yr), and spread_label
    (wide/normal/tight). Any input that's missing/invalid degrades the affected
    label to "unavailable" (and its number to None) instead of raising.
    """
    result = {
        "range_position": None,
        "range_label": UNAVAILABLE,
        "direction": UNAVAILABLE,
        "spread": None,
        "spread_label": UNAVAILABLE,
    }

    # Where the yield sits within its trailing 52-week high/low range.
    if _is_pos(treasury_yield) and _is_pos(yr_high) and _is_pos(yr_low) and yr_high > yr_low:
        pos = 100.0 * (treasury_yield - yr_low) / (yr_high - yr_low)
        pos = max(0.0, min(100.0, pos))
        result["range_position"] = round(pos, 1)
        if pos < RANGE_FAVORABLE_MAX:
            result["range_label"] = TIMING_FAVORABLE
        elif pos > RANGE_ELEVATED_MIN:
            result["range_label"] = TIMING_ELEVATED
        else:
            result["range_label"] = TIMING_NEUTRAL

    # Day-over-day direction.
    if _is_pos(treasury_yield) and _is_pos(prev_close):
        delta = treasury_yield - prev_close
        if abs(delta) < DIRECTION_FLAT_BAND:
            result["direction"] = "flat"
        else:
            result["direction"] = "rising" if delta > 0 else "falling"

    # Mortgage-minus-Treasury spread vs the long-run norm.
    if _is_pos(treasury_yield) and _is_pos(mortgage_rate):
        spread = round(mortgage_rate - treasury_yield, 2)
        result["spread"] = spread
        if spread > NORMAL_SPREAD + SPREAD_BAND:
            result["spread_label"] = SPREAD_WIDE
        elif spread < NORMAL_SPREAD - SPREAD_BAND:
            result["spread_label"] = SPREAD_TIGHT
        else:
            result["spread_label"] = SPREAD_NORMAL

    return result

#@tool
def get_rates_search_tool() -> str:
    """Get the average mortgage interest rate."""

    tavily_client = TavilyClient(api_key=os.getenv('TAVILY_API_KEY'))

    response = tavily_client.search(
        query="""What is the current average 30-year fixed mortgage interest rate people in the United States are receiving?" \
        "Provide the answer as a number with 2 decimal places. E.g., 6.55.
        ONLY provide the number without any additional text.""",
        topic="finance",
        search_depth="basic",
        max_results=3,
        time_range="day",
        include_answer=True #Include an LLM-generated answer to the provided query. 
    )

    answer = response["answer"]
    return answer


LOCAL_CU_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.5993.89 Safari/537.36"
)

NATIONAL_RATE_LABEL = "national average"
LOCAL_RATE_LABEL = "Washington DC area"
UNAVAILABLE_RATE_LABEL = "unavailable"


def consolidate_rates(national_rate: float, local_rate: float) -> tuple[float, str]:
    """Choose the effective market rate as the LOWER of the available (non-zero) source
    rates and return (rate, human-readable source label). Sources that failed are passed
    in as 0.0 and ignored. If both failed, returns (0.0, 'unavailable'). Ties prefer the
    national source (listed first)."""
    candidates = []
    if national_rate and national_rate > 0:
        candidates.append((national_rate, NATIONAL_RATE_LABEL))
    if local_rate and local_rate > 0:
        candidates.append((local_rate, LOCAL_RATE_LABEL))
    if not candidates:
        return 0.0, UNAVAILABLE_RATE_LABEL
    return min(candidates, key=lambda c: c[0])


def parse_conforming_30yr_avg(html: str) -> float:
    """Parse the 'First Mortgage - Conforming Limits' 30-Year Fixed rates from the
    rendered 'today's featured rates' HTML partial and return the average of the listed
    Rate-column values (the published rows differ only by points). Raises ValueError if
    the expected section/product/rows are not found."""
    section_start = html.find("First Mortgage - Conforming Limits")
    if section_start == -1:
        raise ValueError("Conforming Limits section not found in rates HTML")
    section = html[section_start:]

    product_start = section.find("30 Year Fixed Rate")
    if product_start == -1:
        raise ValueError("30 Year Fixed Rate product not found in Conforming section")
    block = section[product_start:]

    # End the block at the next product so other products' rows are excluded.
    next_product = re.search(r"class=['\"]tfr-product['\"]", block)
    if next_product:
        block = block[: next_product.start()]

    # Rate-column values are exposed as aria-label="Rate X.XXX%".
    rates = [float(m) for m in re.findall(r"aria-label=['\"]Rate (\d+(?:\.\d+)?)%['\"]", block)]
    if not rates:
        raise ValueError("No Rate values parsed from Conforming 30-Year block")

    return sum(rates) / len(rates)


def get_local_credit_union_30yr_rate() -> float:
    """Fetch the local credit union's Conforming 30-Year Fixed rate (average of the
    listed rows). The institution-specific URL is read from LOCAL_CREDIT_UNION_RATES_URL
    so the source is not hardcoded. Raises ValueError on any failure (missing env var,
    network error, or parse failure)."""
    url = os.getenv("LOCAL_CREDIT_UNION_RATES_URL")
    if not url:
        raise ValueError("LOCAL_CREDIT_UNION_RATES_URL is not set")

    resp = requests.get(url, headers={"User-Agent": LOCAL_CU_USER_AGENT}, timeout=8)
    resp.raise_for_status()
    return parse_conforming_30yr_avg(resp.text)


def calculate_estimates_and_breakeven(#interest_rate: float,
                                      current_payment: float,
                                      mortgage_balance: float,
                                      market_rate: float) -> tuple[float, float]:
    """Calculate the new monthly mortgage payment and the break-even period on the closing costs"""
    ### New Payment Calculation ###
    remaining_term_years = 30
    # Convert to monthly rate
    r = (market_rate / 100) / 12
    n = int(remaining_term_years * 12)  # total remaining monthly payments
    # Compute new monthly payment using amortization formula
    if r == 0:
        # Zero-interest edge case
        return mortgage_balance / n
    # New Monthly Mortgage Payment (P&I only)
    new_payment = mortgage_balance * (r * (1 + r)**n) / ((1 + r)**n - 1)

    ### Break Even Calculation ###
    estimated_closing_costs = mortgage_balance * 0.01
    monthly_savings = current_payment - new_payment
    break_even = estimated_closing_costs / monthly_savings
    
    return new_payment, monthly_savings, break_even

# Define the tools for the agents to use using LangChains tool decorate
# It needs to be done this way because PyTest will throw an error if @tool is present 
# on the function it's testing

@tool
def get_treasury_10yr_yield_for_agent() -> float:
    """Gets the 10 year treasury yield value."""
    return get_treasury_10yr_yield()

@tool
def get_rates_search_tool_for_agent() -> str:
    """Get the average mortgage interest rate."""
    return get_rates_search_tool()

@tool
def get_local_credit_union_30yr_rate_for_agent() -> float:
    """Get the local credit union's (Washington DC area) average 30-year fixed rate."""
    return get_local_credit_union_30yr_rate()


class CalcArgs(BaseModel):
    current_payment: float
    mortgage_balance: float
    market_rate: float

@tool(args_schema=CalcArgs)
def calculate_estimates_and_breakeven_for_agent(
    current_payment: float,
    mortgage_balance: float,
    market_rate: float
) -> tuple[float, float, float]:
    """Calculate the user's estimated new payment, savings, and break-even point."""
    return calculate_estimates_and_breakeven(
        current_payment=current_payment,
        mortgage_balance=mortgage_balance,
        market_rate=market_rate
    )

if __name__ == "__main__":
    print(get_treasury_10yr_yield())
