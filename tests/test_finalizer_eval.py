"""Opt-in evals for the finalizer prompt. These call the LIVE LLM, so they're marked
`finalizer_eval` and excluded by default (see pyproject addopts). Run explicitly:

    poetry run pytest -m finalizer_eval -s

Each case feeds a fully-populated state through finalizer_agent and asserts the
rendered recommendation contains the right substance and avoids known failure modes
(reporting 0%, contradicting the precomputed verdict, etc.). They guard against
regressions when editing src/prompts/finalizer_prompt.txt."""

import pytest

from core.agents import finalizer_agent
from core.tools import build_refinance_scenarios


def _base_state(**overrides):
    state = {
        "interest_rate": 7.5,
        "current_payment": 3850.0,
        "mortgage_balance": 480000.0,
        "remaining_term_years": 22.0,
        "stay_horizon_years": 6.0,
        "closing_costs": 9000.0,
        "treasury_yield": 4.45,
        "treasury_yr_low": 3.93,
        "treasury_yr_high": 4.69,
        "treasury_range_position": 69.6,
        "treasury_timing_label": "elevated",
        "treasury_direction": "falling",
        "mortgage_treasury_spread": 1.86,
        "spread_label": "normal",
        "market_rate": 6.3125,
        "national_rate": 6.56,
        "local_credit_union_rate": 6.3125,
        "market_rate_source": "Washington DC area",
        "num_tool_calls": 4,
        "path": ["market_expert_agent", "treasury_yield_agent", "rate_outlook_agent",
                 "calculator_agent", "strategy_agent"],
        "scenarios": [],
        "recommended_scenario_label": "Keep your current payoff date",
        "strategy_rationale": "Lowers the payment without restarting the term.",
        "lifetime_interest_delta": -127248.78,
        "breaks_even_within_horizon": True,
        "rate_outlook_label": "stable",
        "rate_outlook_summary": "Rates are expected to hold mostly steady.",
        "rate_outlook_action": "neutral",
        "new_payment": 3368.0,
        "monthly_savings": 482.0,
        "break_even": 18.7,
        "recommendation": "",
    }
    state.update(overrides)
    if not state["scenarios"] and state["market_rate"]:
        state["scenarios"] = build_refinance_scenarios(
            state["mortgage_balance"], state["current_payment"], state["market_rate"],
            state["remaining_term_years"], state["closing_costs"], state["stay_horizon_years"])
    return state


def _text(state):
    out = finalizer_agent(_base_state(**state))
    rec = out["recommendation"]
    return (rec.content if hasattr(rec, "content") else str(rec))


@pytest.mark.finalizer_eval
def test_strong_refi_reports_numbers_and_lifetime_warning():
    text = _text({})
    print("\n--- STRONG REFI ---\n", text)
    assert "$3,368" in text and "$482" in text          # pre-formatted numbers survive
    assert "18.7 months" in text
    assert "127,2" in text                               # lifetime-interest figure present (~$127k)
    assert "0%" not in text                              # never reports a zero rate
    assert text.strip().startswith("**")                 # bold verdict line first


@pytest.mark.finalizer_eval
def test_do_not_refinance_when_rate_beats_market():
    text = _text({
        "interest_rate": 4.0, "scenarios": [], "recommended_scenario_label": "n/a",
        "new_payment": None, "monthly_savings": None, "break_even": None,
        "lifetime_interest_delta": None, "breaks_even_within_horizon": None,
    })
    print("\n--- DO NOT REFI ---\n", text)
    low = text.lower()
    assert "keep" in low or "better off" in low or "not refinance" in low or "don't refinance" in low


@pytest.mark.finalizer_eval
def test_rates_unavailable_does_not_fabricate():
    text = _text({
        "market_rate": 0.0, "national_rate": 0.0, "local_credit_union_rate": 0.0,
        "market_rate_source": "unavailable", "treasury_yield": None,
        "treasury_timing_label": "unavailable", "spread_label": "unavailable",
        "rate_outlook_label": "unavailable", "rate_outlook_summary": "",
        "scenarios": [], "recommended_scenario_label": "n/a",
        "new_payment": None, "monthly_savings": None, "break_even": None,
        "lifetime_interest_delta": None, "breaks_even_within_horizon": None,
        "num_tool_calls": 0, "treasury_range_position": None,
        "treasury_yr_low": None, "treasury_yr_high": None,
        "mortgage_treasury_spread": None,
    })
    print("\n--- RATES UNAVAILABLE ---\n", text)
    low = text.lower()
    assert "0%" not in text
    assert "couldn't" in low or "could not" in low or "unavailable" in low or "try again" in low


@pytest.mark.finalizer_eval
def test_sell_before_breakeven_is_flagged():
    text = _text({
        "stay_horizon_years": 1.0, "breaks_even_within_horizon": False,
    })
    print("\n--- SELL BEFORE BREAKEVEN ---\n", text)
    low = text.lower()
    assert "sell" in low or "before" in low or "may not" in low or "horizon" in low
