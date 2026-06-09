import os
import pytest
from core.tools import (
    get_treasury_10yr_yield,
    get_treasury_10yr_quote,
    classify_rate_timing,
    get_rates_search_tool,
    calculate_estimates_and_breakeven,
    parse_conforming_30yr_avg,
    consolidate_rates,
    get_local_credit_union_30yr_rate,
)

# Minimal, name-free fixture mirroring the real "today's featured rates" markup.
# Includes a following 15-Year product to prove the parser stops at the next product.
CONFORMING_RATES_HTML_FIXTURE = """
<div class="product-type"> First Mortgage - Conforming Limits </div>
<div class="product">
  <div class="link">
    <a role="button" class='tfr-product' data-productid="75507">30 Year Fixed Rate</a>
  </div>
  <div class="rates" role="table">
    <div role="rowgroup"><div class="rate-row" role="row">
      <div role="cell"><a aria-label="Rate 6.250%" class="tfr-rate-detail">6.250%</a></div>
      <div role="cell"><a aria-label="APR 6.391%" class="tfr-rate-detail">6.391%</a></div>
      <div role="cell" aria-label="Points 1.000%">1.000%</div>
    </div></div>
    <div role="rowgroup"><div class="rate-row" role="row">
      <div role="cell"><a aria-label="Rate 6.375%" class="tfr-rate-detail">6.375%</a></div>
      <div role="cell"><a aria-label="APR 6.433%" class="tfr-rate-detail">6.433%</a></div>
      <div role="cell" aria-label="Points 0.125%">0.125%</div>
    </div></div>
  </div>
</div>
<div class="product">
  <div class="link">
    <a role="button" class='tfr-product' data-productid="75509">15 Year Fixed Rate</a>
  </div>
  <div class="rates" role="table">
    <div role="rowgroup"><div class="rate-row" role="row">
      <div role="cell"><a aria-label="Rate 5.750%" class="tfr-rate-detail">5.750%</a></div>
    </div></div>
  </div>
</div>
"""

@pytest.mark.treasury
def test_live_us10y_range():
    """
    Test to see if CNBC 10 year treasury yield is returned
    """
    val = get_treasury_10yr_yield()
    print(f"TEST #1 - 10 Year Treasury Yield = {val}")
    assert 0.0 < val < 20.0 

@pytest.mark.interest_rate
def test_live_average_interest_rate():
    """
    Test to see what the average interest rate is in the US currently.
    """
    val = get_rates_search_tool()
    print(f"TEST #2 - Average US Interest Rate = {val}")
    assert val is not None

@pytest.mark.calculation
def test_calulcator_rool():
    """
    Test to see how the calculator performs getting the new payment and break even.
    """
    current_payment = 5000
    mortgage_balance = 650000
    market_rate = 6.125
    vals = calculate_estimates_and_breakeven(current_payment, mortgage_balance, market_rate)
    new_payment, monthly_savings, break_even = vals

    print(f"\nTEST #3.1 - New Monthly Payment: {round(new_payment,2)}")
    print(f"\nTEST #3.2 - Monthly Savings: {round(monthly_savings,2)}")
    print(f"\nTest #3.3 - Break Even: {round(break_even,2)} ")

    assert isinstance(vals, tuple)
    assert len(vals) == 3
    assert isinstance(new_payment, float)
    assert isinstance(monthly_savings, float)
    assert isinstance(break_even, float)
    assert monthly_savings > 0
    assert new_payment > 0
    assert break_even > 0


# Run tests with
# poetry run pytest test_tools.py -m treasury -s
# poetry run pytest test_tools.py -m interest_rate -s

@pytest.mark.calculation
def test_parse_conforming_30yr_avg_returns_average_of_two_rows():
    """Averages the two Conforming 30yr Rate rows and ignores the 15yr product."""
    result = parse_conforming_30yr_avg(CONFORMING_RATES_HTML_FIXTURE)
    assert result == 6.3125

@pytest.mark.calculation
def test_parse_conforming_30yr_avg_raises_on_missing_section():
    """Raises ValueError when the Conforming section is absent."""
    with pytest.raises(ValueError):
        parse_conforming_30yr_avg("<html><body>no rates here</body></html>")

@pytest.mark.calculation
def test_parse_conforming_30yr_avg_raises_when_product_absent():
    """Raises ValueError when the Conforming section exists but has no 30yr product."""
    html = '<div class="product-type"> First Mortgage - Conforming Limits </div><div>nothing</div>'
    with pytest.raises(ValueError):
        parse_conforming_30yr_avg(html)


@pytest.mark.calculation
def test_consolidate_rates_picks_lower_when_both_present():
    assert consolidate_rates(6.55, 6.3125) == (6.3125, "Washington DC area")
    assert consolidate_rates(6.10, 6.3125) == (6.10, "national average")


@pytest.mark.calculation
def test_consolidate_rates_ignores_failed_source():
    # local failed (0.0) -> use national
    assert consolidate_rates(6.55, 0.0) == (6.55, "national average")
    # national failed (0.0) -> use local
    assert consolidate_rates(0.0, 6.3125) == (6.3125, "Washington DC area")


@pytest.mark.calculation
def test_consolidate_rates_both_failed_is_unavailable():
    assert consolidate_rates(0.0, 0.0) == (0.0, "unavailable")


@pytest.mark.calculation
def test_consolidate_rates_tie_prefers_national():
    assert consolidate_rates(6.3, 6.3) == (6.3, "national average")


@pytest.mark.local_cu
def test_live_local_credit_union_30yr_rate():
    """Live: fetch + parse the local CU conforming 30yr rate. Skips if URL unset."""
    if not os.getenv("LOCAL_CREDIT_UNION_RATES_URL"):
        pytest.skip("LOCAL_CREDIT_UNION_RATES_URL not set")
    val = get_local_credit_union_30yr_rate()
    print(f"TEST - Local CU 30yr Rate = {val}")
    assert isinstance(val, float)
    assert 0.0 < val < 20.0


# ---- Treasury timing classifier (pure, offline) ----

@pytest.mark.calculation
def test_classify_rate_timing_range_labels():
    favorable = classify_rate_timing(4.0, yr_high=4.7, yr_low=3.9, prev_close=4.0, mortgage_rate=6.0)
    neutral = classify_rate_timing(4.3, yr_high=4.7, yr_low=3.9, prev_close=4.3, mortgage_rate=6.0)
    elevated = classify_rate_timing(4.54, yr_high=4.69, yr_low=3.93, prev_close=4.54, mortgage_rate=6.5)
    assert favorable["range_label"] == "favorable"   # ~13th percentile
    assert neutral["range_label"] == "neutral"        # 50th percentile
    assert elevated["range_label"] == "elevated"      # ~80th percentile


@pytest.mark.calculation
def test_classify_rate_timing_range_position_value():
    r = classify_rate_timing(4.54, yr_high=4.69, yr_low=3.93, prev_close=4.50, mortgage_rate=6.5)
    assert r["range_position"] == pytest.approx(80.3, abs=0.5)


@pytest.mark.calculation
def test_classify_rate_timing_spread_labels():
    assert classify_rate_timing(4.0, 4.7, 3.9, 4.0, mortgage_rate=6.5)["spread_label"] == "wide"    # 2.50
    assert classify_rate_timing(4.54, 4.69, 3.93, 4.54, mortgage_rate=6.5)["spread_label"] == "normal"  # 1.96
    assert classify_rate_timing(4.5, 4.7, 3.9, 4.5, mortgage_rate=5.7)["spread_label"] == "tight"   # 1.20


@pytest.mark.calculation
def test_classify_rate_timing_direction():
    assert classify_rate_timing(4.55, 4.7, 3.9, 4.50, 6.5)["direction"] == "rising"
    assert classify_rate_timing(4.45, 4.7, 3.9, 4.50, 6.5)["direction"] == "falling"
    assert classify_rate_timing(4.501, 4.7, 3.9, 4.50, 6.5)["direction"] == "flat"


@pytest.mark.calculation
def test_classify_rate_timing_unavailable_edges():
    # Equal hi/lo -> range unavailable; spread still computed.
    r = classify_rate_timing(4.5, yr_high=4.5, yr_low=4.5, prev_close=4.5, mortgage_rate=6.5)
    assert r["range_label"] == "unavailable"
    assert r["range_position"] is None
    assert r["spread_label"] == "normal"
    # Missing mortgage rate -> spread unavailable; range still computed.
    r2 = classify_rate_timing(4.0, 4.7, 3.9, 4.0, mortgage_rate=0.0)
    assert r2["spread_label"] == "unavailable"
    assert r2["spread"] is None
    assert r2["range_label"] == "favorable"


@pytest.mark.treasury
def test_live_treasury_10yr_quote():
    """Live: CNBC quote returns last within its 52-week low..high band."""
    q = get_treasury_10yr_quote()
    print(f"TEST - 10yr quote = {q}")
    assert 0.0 < q["last"] < 20.0
    if q["yr_high"] is not None and q["yr_low"] is not None:
        assert 0.0 < q["yr_low"] <= q["last"] <= q["yr_high"] < 20.0

