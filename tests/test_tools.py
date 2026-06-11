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
    monthly_payment,
    total_interest,
    estimate_remaining_term_years,
    resolve_closing_costs,
    build_scenario,
    build_refinance_scenarios,
    get_rate_outlook_search,
    DEFAULT_CLOSING_COST_PCT,
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


# ---- Refinance math (pure, offline) ----

@pytest.mark.calculation
def test_monthly_payment_known_value():
    """$500k @ 6% over 30yr -> ~$2,997.75 P&I."""
    assert monthly_payment(500_000, 6.0, 30) == pytest.approx(2997.75, abs=0.5)


@pytest.mark.calculation
def test_monthly_payment_zero_rate_is_straight_line():
    """A 0% loan is just principal spread evenly across the term."""
    assert monthly_payment(360_000, 0.0, 30) == pytest.approx(1000.0, abs=0.01)


@pytest.mark.calculation
def test_estimate_remaining_term_round_trips():
    """The payment produced by a 30yr loan should imply ~30 years remaining."""
    pmt = monthly_payment(500_000, 6.0, 30)
    years = estimate_remaining_term_years(500_000, pmt, 6.0)
    assert years == pytest.approx(30.0, abs=0.1)


@pytest.mark.calculation
def test_estimate_remaining_term_none_when_payment_below_interest():
    """If the monthly payment doesn't cover interest, no finite term exists."""
    # 500k @ 6% accrues ~$2,500/mo interest; a $1,000 payment never amortizes.
    assert estimate_remaining_term_years(500_000, 1_000, 6.0) is None


@pytest.mark.calculation
def test_resolve_closing_costs_quote_vs_default():
    assert resolve_closing_costs(9_000, 500_000) == 9_000.0          # explicit quote wins
    assert resolve_closing_costs(None, 500_000) == 500_000 * DEFAULT_CLOSING_COST_PCT
    assert resolve_closing_costs(0, 500_000) == 500_000 * DEFAULT_CLOSING_COST_PCT  # 0 -> default


@pytest.mark.calculation
def test_total_interest_basic():
    """Total interest = payments * months - principal."""
    # 0% / 30yr on 360k -> $1,000 x 360 - 360k = 0 interest.
    assert total_interest(1_000, 30, 360_000) == pytest.approx(0.0, abs=0.01)


@pytest.mark.calculation
def test_build_scenario_term_reset_trap_adds_lifetime_interest():
    """A 30-yr reset over a ~20-yr-remaining loan at a modestly lower rate lowers the
    monthly payment but ADDS lifetime interest (delta > 0) -- the trap we want to surface."""
    # Borrower: 300k left, ~20yr remaining at 7%, paying ~$2,326/mo. Refi to 30yr @ 6%.
    current_payment = monthly_payment(300_000, 7.0, 20)
    s = build_scenario("Lower payment (30-yr)", 300_000, current_payment, 6.0,
                       new_term_years=30, remaining_term_years=20,
                       closing_costs=6_000, horizon_years=7)
    assert s["monthly_savings"] > 0                 # payment drops
    assert s["lifetime_interest_delta"] > 0         # but lifetime interest rises
    assert s["break_even"] == pytest.approx(6_000 / s["monthly_savings"], abs=0.1)


@pytest.mark.calculation
def test_build_scenario_horizon_fields():
    s = build_scenario("Keep your current payoff date", 300_000, 2_500, 6.0,
                       new_term_years=20, remaining_term_years=20,
                       closing_costs=6_000, horizon_years=7)
    expected_net = s["monthly_savings"] * 7 * 12 - 6_000
    assert s["net_savings_over_horizon"] == pytest.approx(expected_net, abs=0.5)
    assert s["breaks_even_within_horizon"] == (s["break_even"] is not None and s["break_even"] <= 84)


@pytest.mark.calculation
def test_build_refinance_scenarios_dedupes_when_remaining_near_30():
    """A ~30-yr remaining loan should not produce a duplicate 30-yr reset row."""
    scenarios = build_refinance_scenarios(500_000, 3_500, 6.0, remaining_term_years=30,
                                          closing_costs=10_000, horizon_years=7)
    terms = [round(s["term_years"]) for s in scenarios]
    assert terms.count(30) == 1                     # 'keep payoff' (30) merged with the 30-yr reset
    assert 15 in terms                              # 15-yr option still present


@pytest.mark.rate_outlook
def test_live_rate_outlook_search():
    """Live: Tavily returns a non-empty near-term mortgage-rate outlook string."""
    val = get_rate_outlook_search()
    print(f"TEST - Rate outlook = {val}")
    assert isinstance(val, str) and len(val.strip()) > 0

