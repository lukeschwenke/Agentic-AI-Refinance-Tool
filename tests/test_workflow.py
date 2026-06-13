"""Offline tests for the LangGraph workflow: every external fetch and LLM call is
stubbed, so these verify the graph's routing (including the parallel treasury/rate-outlook
fan-out and the verifier regeneration loop), the state wiring between agents, and that the
finalizer receives the right precomputed decision — with no network access."""

import pytest
from types import SimpleNamespace

import core.agents as agents
from core.workflow import app as graph_app


GOOD_QUOTE = {"last": 4.40, "yr_high": 4.70, "yr_low": 3.90, "prev_close": 4.42}


def make_initial_state(**overrides):
    """Mirror of the initial_state the API builds in api_setup.py."""
    state = {
        "interest_rate": 7.5,
        "current_payment": 3850.0,
        "mortgage_balance": 480000.0,
        "remaining_term_years": None,
        "stay_horizon_years": None,
        "closing_costs": None,
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
    state.update(overrides)
    return state


def assert_continue_path(path):
    """market -> {treasury, rate_outlook in either order} -> calculator -> strategy
    -> finalizer -> verifier."""
    assert path[0] == "market_expert_agent"
    assert set(path[1:3]) == {"treasury_yield_agent", "rate_outlook_agent"}
    assert path[3:] == ["calculator_agent", "strategy_agent", "finalizer_agent", "verifier_agent"]


class FakeStructured:
    def __init__(self, result):
        self.result = result

    def invoke(self, prompt):
        return self.result


class FakeLLM:
    """Stands in for core.agents.llm: canned structured outputs keyed by schema name."""
    def __init__(self, by_schema=None):
        self.by_schema = by_schema or {}

    def with_structured_output(self, schema):
        return FakeStructured(self.by_schema[schema.__name__])

    def invoke(self, prompt):
        return SimpleNamespace(content="6.55")


class FakeFinalizerLLM:
    """Captures every formatted finalizer prompt so tests can assert on contents/retries."""
    def __init__(self):
        self.prompts = []

    @property
    def last_prompt(self):
        return self.prompts[-1] if self.prompts else None

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content="**Stubbed verdict.**")


def stub_happy_market(monkeypatch):
    monkeypatch.setattr(agents, "get_rates_search_tool", lambda: "The average rate is 6.55% today.")
    monkeypatch.setattr(agents, "get_local_credit_union_30yr_rate", lambda: 6.31)


def stub_down_market(monkeypatch):
    def _boom():
        raise RuntimeError("simulated outage")
    monkeypatch.setattr(agents, "get_rates_search_tool", _boom)
    monkeypatch.setattr(agents, "get_local_credit_union_30yr_rate", _boom)


def stub_rest(monkeypatch, recommended_label="Keep your current payoff date", verifier_passed=True):
    monkeypatch.setattr(agents, "get_treasury_10yr_quote", lambda: dict(GOOD_QUOTE))
    monkeypatch.setattr(agents, "get_rate_outlook_search", lambda: "Rates look steady near 6%.")
    fake_llm = FakeLLM({
        "RateOutlookRead": agents.RateOutlookRead(
            label="stable", action="neutral", summary="Rates should hold steady."),
        "StrategyPick": agents.StrategyPick(
            recommended_label=recommended_label, rationale="Best balance of savings and payoff date."),
        "VerifierVerdict": agents.VerifierVerdict(passed=verifier_passed, problem="" if verifier_passed else "x"),
    })
    finalizer = FakeFinalizerLLM()
    monkeypatch.setattr(agents, "llm", fake_llm)
    monkeypatch.setattr(agents, "llm_finalizer", finalizer)
    return finalizer


@pytest.mark.calculation
def test_continue_path_runs_all_agents_and_wires_state(monkeypatch):
    stub_happy_market(monkeypatch)
    finalizer = stub_rest(monkeypatch)

    result = graph_app.invoke(make_initial_state(
        remaining_term_years=22.0, stay_horizon_years=6.0, closing_costs=9000.0))

    assert_continue_path(result["path"])
    # Lower of the two sources wins; both sources reported.
    assert result["market_rate"] == 6.31
    assert result["national_rate"] == 6.55
    assert result["market_rate_source"] == "Washington DC area"
    # Fetch counter = national + local + treasury + outlook (summed via reducer).
    assert result["num_tool_calls"] == 4
    assert result["treasury_timing_label"] in ("favorable", "neutral", "elevated")
    assert result["rate_outlook_label"] == "stable"
    # Scenario set built; primary metrics mirror the recommended scenario.
    assert len(result["scenarios"]) == 3
    recommended = next(s for s in result["scenarios"]
                       if s["label"] == result["recommended_scenario_label"])
    assert result["new_payment"] == recommended["new_payment"]
    assert result["monthly_savings"] == recommended["monthly_savings"]
    assert result["break_even"] == recommended["break_even"]
    assert result["lifetime_interest_delta"] == recommended["lifetime_interest_delta"]
    # The finalizer got the precomputed verdict branch (gap 7.5 - 6.31 >= 1.0).
    assert "STRONG_REFINANCE_OPPORTUNITY" in finalizer.last_prompt
    assert result["verifier_passed"] is True
    assert len(finalizer.prompts) == 1   # no regeneration when the verifier passes
    assert result["recommendation"].content == "**Stubbed verdict.**"


@pytest.mark.calculation
def test_short_circuit_when_rate_beats_market(monkeypatch):
    stub_happy_market(monkeypatch)
    finalizer = stub_rest(monkeypatch)

    result = graph_app.invoke(make_initial_state(interest_rate=4.0))

    assert result["path"] == ["market_expert_agent", "finalizer_agent", "verifier_agent"]
    assert result["scenarios"] == []
    assert result["new_payment"] is None
    assert "DO_NOT_REFINANCE" in finalizer.last_prompt


@pytest.mark.calculation
def test_rates_unavailable_skips_analysis(monkeypatch):
    """P0 regression test: when BOTH rate sources fail, the workflow must NOT build
    scenarios against a 0% market rate — it routes straight to the finalizer with a
    RATES_UNAVAILABLE decision."""
    stub_down_market(monkeypatch)
    finalizer = stub_rest(monkeypatch)

    result = graph_app.invoke(make_initial_state())

    assert result["path"] == ["market_expert_agent", "finalizer_agent", "verifier_agent"]
    assert result["market_rate"] == 0.0
    assert result["market_rate_source"] == "unavailable"
    assert result["scenarios"] == []
    assert result["new_payment"] is None
    assert result["num_tool_calls"] == 0
    assert "RATES_UNAVAILABLE" in finalizer.last_prompt


@pytest.mark.calculation
def test_strategy_none_keeps_seeded_numbers(monkeypatch):
    """When the strategist says no structure is viable, the calculator's honest seeded
    numbers stay on the metric fields and the finalizer is told 'none'."""
    stub_happy_market(monkeypatch)
    finalizer = stub_rest(monkeypatch, recommended_label="none")

    result = graph_app.invoke(make_initial_state(
        remaining_term_years=22.0, stay_horizon_years=6.0, closing_costs=9000.0))

    assert result["recommended_scenario_label"] == "none"
    # Seeded from the first scenario by calculator_agent, not cleared.
    assert result["new_payment"] == result["scenarios"][0]["new_payment"]
    assert "none" in finalizer.last_prompt


@pytest.mark.calculation
def test_verifier_regenerates_finalizer_once_on_failure(monkeypatch):
    """The verifier fails the first draft, the finalizer regenerates with the complaint,
    the second draft passes — and the loop is bounded to a single retry."""
    stub_happy_market(monkeypatch)
    monkeypatch.setattr(agents, "get_treasury_10yr_quote", lambda: dict(GOOD_QUOTE))
    monkeypatch.setattr(agents, "get_rate_outlook_search", lambda: "Rates look steady near 6%.")

    class FlakyLLM(FakeLLM):
        def __init__(self, by_schema):
            super().__init__(by_schema)
            self.verifier_calls = 0

        def with_structured_output(self, schema):
            if schema.__name__ == "VerifierVerdict":
                self.verifier_calls += 1
                passed = self.verifier_calls >= 2   # fail first, pass second
                return FakeStructured(agents.VerifierVerdict(
                    passed=passed, problem="" if passed else "a stated number is wrong"))
            return FakeStructured(self.by_schema[schema.__name__])

    flaky = FlakyLLM({
        "RateOutlookRead": agents.RateOutlookRead(label="stable", action="neutral", summary="Steady."),
        "StrategyPick": agents.StrategyPick(recommended_label="Keep your current payoff date", rationale="ok"),
    })
    finalizer = FakeFinalizerLLM()
    monkeypatch.setattr(agents, "llm", flaky)
    monkeypatch.setattr(agents, "llm_finalizer", finalizer)

    result = graph_app.invoke(make_initial_state(
        remaining_term_years=22.0, stay_horizon_years=6.0, closing_costs=9000.0))

    assert flaky.verifier_calls == 2
    assert len(finalizer.prompts) == 2                       # regenerated exactly once
    assert "CORRECTION REQUIRED" in finalizer.prompts[1]     # feedback fed back in
    assert "a stated number is wrong" in finalizer.prompts[1]
    assert result["verifier_passed"] is True
    assert result["path"].count("finalizer_agent") == 2
    assert result["path"].count("verifier_agent") == 2
