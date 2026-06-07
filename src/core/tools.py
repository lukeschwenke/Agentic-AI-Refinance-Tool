import re
import requests
from langchain_core.tools import tool
from tavily import TavilyClient
import os
from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv()

#@tool
def get_treasury_10yr_yield() -> float:
    """"
    Gets the 10 year treasury yield value.
    """

    url = "https://quote.cnbc.com/quote-html-webservice/quote.htm"

    headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/118.0.5993.89 Safari/537.36"
    )
    }

    params = {
        "noform": "1",
        "partnerId": "2",
        "fund": "1",
        "exthrs": "0",
        "output": "json",
        "symbols": "US10Y"
    }

    resp = requests.get(url, params=params, headers=headers, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    try:
        quotes = data["QuickQuoteResult"]["QuickQuote"]
        value = quotes[0]["last"]
        str_value = str(value).strip().rstrip("%")
        return float(str_value)
    except Exception as e:
        raise ValueError(f"Unexpected CNBC payload shape or symbol missing: {e}") from e

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
