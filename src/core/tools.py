import re
import math
import time
import functools
import requests
from tavily import TavilyClient
import os
from dotenv import load_dotenv


load_dotenv()


def _with_retries(call, attempts=3, backoff_seconds=0.5):
    """Run a zero-arg callable, retrying transient failures with linear backoff.
    Re-raises the last exception so callers' degrade-to-unavailable handling still works."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(backoff_seconds * attempt)


MARKET_DATA_TTL_SECONDS = 15 * 60


def _ttl_cache(fn):
    """Cache a zero-arg fetcher's successful result for MARKET_DATA_TTL_SECONDS.
    Rates don't move minute-to-minute, and demo visitors repeat requests — this cuts
    latency, Tavily cost, and exposure to source flakiness. Failures are never cached."""
    cached = {"at": 0.0, "value": None}

    @functools.wraps(fn)
    def wrapper():
        if cached["value"] is not None and time.time() - cached["at"] < MARKET_DATA_TTL_SECONDS:
            return cached["value"]
        value = fn()
        cached["at"], cached["value"] = time.time(), value
        return value
    return wrapper

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


@_ttl_cache
def get_treasury_10yr_quote() -> dict:
    """Fetch the 10-year Treasury quote from CNBC (retried, cached ~15 min).

    Returns {"last", "yr_high", "yr_low", "prev_close"} as floats. `last` is
    required (raises ValueError if the payload is malformed); the 52-week high/low
    and previous close degrade to None if absent, so the plain yield fetch and the
    timing classifier can still work with partial data.
    """
    params = {
        "noform": "1", "partnerId": "2", "fund": "1", "exthrs": "0",
        "output": "json", "symbols": "US10Y",
    }

    def _fetch():
        r = requests.get(TREASURY_QUOTE_URL, params=params,
                         headers={"User-Agent": TREASURY_USER_AGENT}, timeout=8)
        r.raise_for_status()
        return r

    resp = _with_retries(_fetch)
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

RATE_MIN, RATE_MAX = 2.0, 12.0


def parse_rate_from_text(text: str) -> float:
    """Pull the first plausible mortgage-rate percentage (RATE_MIN-RATE_MAX) out of
    free text, e.g. a search answer like 'The average rate is 6.62% as of...'.
    Returns 0.0 if no in-range decimal number is found."""
    for match in re.findall(r"\d{1,2}\.\d{1,3}", str(text)):
        value = float(match)
        if RATE_MIN <= value <= RATE_MAX:
            return value
    return 0.0


@_ttl_cache
def get_rates_search_tool() -> str:
    """Get the average mortgage interest rate (Tavily answer text; retried, cached ~15 min)."""
    tavily_client = TavilyClient(api_key=os.getenv('TAVILY_API_KEY'))

    response = _with_retries(lambda: tavily_client.search(
        query="""What is the current average 30-year fixed mortgage interest rate people in the United States are receiving?" \
        "Provide the answer as a number with 2 decimal places. E.g., 6.55.
        ONLY provide the number without any additional text.""",
        topic="finance",
        search_depth="basic",
        max_results=3,
        time_range="day",
        include_answer=True #Include an LLM-generated answer to the provided query.
    ))

    answer = response["answer"]
    return answer


@_ttl_cache
def get_rate_outlook_search() -> str:
    """Near-term outlook for US 30-year fixed mortgage rates (Fed signals + forecaster
    commentary) via a Tavily finance search (retried, cached ~15 min). Returns the
    LLM-generated answer text."""
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    response = _with_retries(lambda: tavily_client.search(
        query=("Over the next few months, are US 30-year fixed mortgage rates expected to "
               "rise, fall, or hold steady? What are the Federal Reserve and forecasters "
               "signaling? Answer briefly."),
        topic="finance",
        search_depth="basic",
        max_results=4,
        time_range="week",
        include_answer=True,
    ))
    return response["answer"]


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


@_ttl_cache
def get_local_credit_union_30yr_rate() -> float:
    """Fetch the local credit union's Conforming 30-Year Fixed rate (average of the
    listed rows; retried, cached ~15 min). The institution-specific URL is read from
    LOCAL_CREDIT_UNION_RATES_URL so the source is not hardcoded. Raises ValueError on
    any failure (missing env var, network error, or parse failure)."""
    url = os.getenv("LOCAL_CREDIT_UNION_RATES_URL")
    if not url:
        raise ValueError("LOCAL_CREDIT_UNION_RATES_URL is not set")

    def _fetch():
        r = requests.get(url, headers={"User-Agent": LOCAL_CU_USER_AGENT}, timeout=8)
        r.raise_for_status()
        return r

    return parse_conforming_30yr_avg(_with_retries(_fetch).text)


# --- Refinance calculation defaults (tunable; see the scenarios/strategy spec) ---
DEFAULT_CLOSING_COST_PCT = 0.02     # 2% of balance when no quote given (2026 norm: 2-6%)
DEFAULT_STAY_HORIZON_YEARS = 7      # median owner tenure; used when horizon not provided
SCENARIO_TERMS = (30, 15)           # standard alt terms modeled alongside "keep payoff date"


def monthly_payment(balance: float, annual_rate: float, term_years: float) -> float:
    """Standard amortized monthly P&I payment for a loan of `balance` at `annual_rate`
    (percent) over `term_years` years."""
    r = (annual_rate / 100) / 12
    n = int(round(term_years * 12))
    if n <= 0:
        return 0.0
    if r == 0:
        return balance / n
    return balance * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def total_interest(payment: float, term_years: float, principal: float) -> float:
    """Total interest paid over the life of a loan (sum of payments minus principal)."""
    return payment * int(round(term_years * 12)) - principal


def estimate_remaining_term_years(balance, current_payment, interest_rate):
    """Solve the amortization equation for the number of years left on the CURRENT loan
    from (remaining balance, monthly P&I payment, annual rate). Returns None if the
    payment doesn't cover the monthly interest (no finite term can be derived)."""
    r = (interest_rate / 100) / 12
    if r <= 0:
        return None
    denom = current_payment - balance * r          # (1+r)^n = P / (P - B*r)
    if denom <= 0:
        return None
    return (math.log(current_payment / denom) / math.log(1 + r)) / 12


def resolve_closing_costs(closing_costs, balance: float) -> float:
    """Use the user's closing-cost quote if given, else default to
    DEFAULT_CLOSING_COST_PCT of the balance."""
    if closing_costs and closing_costs > 0:
        return float(closing_costs)
    return balance * DEFAULT_CLOSING_COST_PCT


def build_scenario(label, balance, current_payment, market_rate, new_term_years,
                   remaining_term_years, closing_costs, horizon_years) -> dict:
    """Compute one refinance scenario fully and deterministically (no LLM). The Strategy
    agent reasons over these dicts; it does NOT compute the numbers itself."""
    new_pmt = monthly_payment(balance, market_rate, new_term_years)
    monthly_savings = current_payment - new_pmt
    break_even = (closing_costs / monthly_savings) if monthly_savings > 0 else None
    new_interest = total_interest(new_pmt, new_term_years, balance)
    current_interest = total_interest(current_payment, remaining_term_years, balance)
    horizon_months = horizon_years * 12
    return {
        "label": label,
        "term_years": round(new_term_years, 1),
        "new_payment": round(new_pmt, 2),
        "monthly_savings": round(monthly_savings, 2),
        "break_even": round(break_even, 1) if break_even is not None else None,
        "lifetime_interest_delta": round(new_interest - current_interest, 2),  # + = costs more
        "net_savings_over_horizon": round(monthly_savings * horizon_months - closing_costs, 2),
        "breaks_even_within_horizon": break_even is not None and break_even <= horizon_months,
    }


def build_refinance_scenarios(balance, current_payment, market_rate, remaining_term_years,
                              closing_costs, horizon_years) -> list:
    """Build the standard scenario set:
    - 'Keep your current payoff date' (same remaining term -> apples-to-apples)
    - 30-year reset (lowest payment)
    - 15-year (fastest payoff)
    Terms within ~1 year of an already-added term are skipped (dedupe)."""
    scenarios, seen = [], set()

    def _add(label, term):
        key = round(term)
        if term <= 0 or key in seen:
            return
        seen.add(key)
        scenarios.append(build_scenario(label, balance, current_payment, market_rate,
                                        term, remaining_term_years, closing_costs, horizon_years))

    _add("Keep your current payoff date", remaining_term_years)
    for t in SCENARIO_TERMS:
        _add("Lower payment (30-yr)" if t == 30 else "Pay off faster (15-yr)", float(t))
    return scenarios


def calculate_estimates_and_breakeven(current_payment: float,
                                      mortgage_balance: float,
                                      market_rate: float,
                                      term_years: float = 30,
                                      closing_costs: float | None = None) -> tuple[float, float, float | None]:
    """Calculate the new monthly P&I payment, monthly savings, and break-even period
    (months) for a refinance into `term_years` at `market_rate`. Closing costs default
    to DEFAULT_CLOSING_COST_PCT of the balance when not provided. Break-even is None when
    there are no monthly savings."""
    new_pmt = monthly_payment(mortgage_balance, market_rate, term_years)
    costs = resolve_closing_costs(closing_costs, mortgage_balance)
    monthly_savings = current_payment - new_pmt
    break_even = costs / monthly_savings if monthly_savings > 0 else None
    return new_pmt, monthly_savings, break_even

if __name__ == "__main__":
    print(get_treasury_10yr_yield())
