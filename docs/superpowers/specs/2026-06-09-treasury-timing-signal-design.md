# Treasury timing signal: relative range position + spread

**Date:** 2026-06-09
**Status:** Approved (design)
**Component:** `treasury_yield_agent`, the CNBC treasury tool, and the finalizer prompt

## Summary

Replace the static `treasury_yield < 4.0%` rule with a **regime-relative timing signal**:

1. **Range position** — where the current 10-year yield sits within its own trailing
   52-week high/low range (favorable / neutral / elevated).
2. **Spread** — the mortgage-minus-Treasury spread vs the long-run ~1.75% norm
   (wide / normal / tight).

A deterministic Python function computes these labels and metrics; the finalizer receives
the **full data** (numbers + labels) and synthesizes the final natural-language advice,
treating the Treasury read as **timing/context, not a pass/fail gate**.

## Motivation

The 4.0% threshold is an absolute level that no longer carries information: the 10-year has
held ~4.0–4.6% for essentially all of 2025–2026 (ended 2025 at 4.16%, ~4.55% in June 2026),
so `< 4.0%` almost never triggers and every user gets the same "wait" verdict. An absolute
level also ignores the mortgage-Treasury spread, which swung from ~1.7% (normal) to ~2.5–3%
(2022–24 QT) and back to ~1.9% — so the same yield implied very different mortgage rates.
What actually decides a refinance is the current mortgage rate vs the user's rate and the
break-even (already computed by the market and calculator agents); the Treasury yield's real
value is forward-looking *timing*, which a relative signal captures and a fixed cutoff does not.

## Data — no new source

The existing CNBC quote endpoint already returns everything needed (verified against the live
`US10Y` payload):

- `last` — current 10-year yield
- `FundamentalData.yrhiprice` / `yrhidate` — trailing 52-week high
- `FundamentalData.yrloprice` / `yrlodate` — trailing 52-week low
- `previous_day_closing` — prior close (for day-over-day direction)

The spread's other input — the current mortgage rate — is already in state from the market
expert agent (`national_rate`, with `market_rate` as fallback). No FRED / external history.

## Detailed design

### 1. Tool changes — `src/core/tools.py`

- **New** `get_treasury_10yr_quote() -> dict`: fetches the CNBC quote once and returns
  `{"last": float, "yr_high": float, "yr_low": float, "prev_close": float}`. Raises
  `ValueError` on a malformed payload (mirrors the existing failure style).
- **Keep** `get_treasury_10yr_yield() -> float`, now implemented as
  `get_treasury_10yr_quote()["last"]` — preserves the existing public function, its live test,
  and the API behavior.
- **New pure function** `classify_rate_timing(treasury_yield, yr_high, yr_low, prev_close,
  mortgage_rate) -> dict` — the testable core (no network, no LLM). Returns:
  - `range_position` (float, percentage 0–100): `100 * (treasury_yield - yr_low) / (yr_high - yr_low)`, clamped.
  - `range_label` (str): `favorable` / `neutral` / `elevated`.
  - `direction` (str): `rising` / `falling` / `flat`.
  - `spread` (float): `mortgage_rate - treasury_yield`.
  - `spread_label` (str): `wide` / `normal` / `tight`.
  - On bad inputs (`yr_high == yr_low`, missing/zero mortgage rate, non-numeric): returns the
    affected labels as `"unavailable"` and numeric fields as `None` rather than raising.

### 2. Thresholds (module-level constants, tunable)

```
RANGE_FAVORABLE_MAX = 33     # range_position < 33 -> favorable (near 12-mo low)
RANGE_ELEVATED_MIN  = 66     # range_position > 66 -> elevated (near 12-mo high); else neutral

NORMAL_SPREAD       = 1.75   # long-run mortgage-minus-10yr spread (percentage points)
SPREAD_BAND         = 0.35   # normal band = 1.40..2.10; > -> wide; < -> tight

DIRECTION_FLAT_BAND = 0.03   # |last - prev_close| < 0.03 -> flat
```

Worked example (June 2026): last 4.54, yr_low 3.93, yr_high 4.69 -> range_position ≈ 81 ->
**elevated**; mortgage ≈ 6.50 -> spread ≈ 1.96 -> **normal**; rising day-over-day.

### 3. State fields — `src/core/define_state_and_llm.py`

Add: `treasury_yr_low`, `treasury_yr_high`, `treasury_range_position`,
`treasury_timing_label`, `treasury_direction`, `mortgage_treasury_spread`, `spread_label`.
`treasury_yield` (the current yield) stays. Initialize the new fields in the API's
`initial_state` (`None` for numerics, `""`/`"unavailable"` for labels).

### 4. `treasury_yield_agent` — `src/core/agents.py`

Runs only in the CONTINUE path (after the market agent), so a mortgage rate is available.
- Call `get_treasury_10yr_quote()` directly inside `try/except` (deterministic, mirrors how
  `market_expert_agent` calls `get_local_credit_union_30yr_rate()`); on failure all treasury
  fields become "unavailable"/`None`/`0.0`.
- Choose the spread's mortgage rate: `national_rate` if `> 0`, else `market_rate`.
- Call `classify_rate_timing(...)`, store `treasury_yield` (= `quote["last"]`) and the new
  fields, bump `num_tool_calls`, append to `path` as today.
- The `get_treasury_10yr_yield_for_agent` tool stays registered per the dual-definition
  convention even though the agent now calls the plain function directly.

### 5. Finalizer prompt — `src/prompts/finalizer_prompt.txt`

Remove the `< 4.0% / >= 4.0%` rule. Add template vars `{treasury_yr_low}`,
`{treasury_yr_high}`, `{treasury_range_position}`, `{treasury_timing_label}`,
`{treasury_direction}`, `{mortgage_treasury_spread}`, `{spread_label}` (plus existing
`{treasury_yield}`), wire them into the `PromptTemplate` `input_variables` and the
`prompt.format(...)` call in `finalizer_agent`. New guidance instructs the finalizer to:

- Report the 10-year yield and where it sits in its 52-week range
  (`{treasury_yr_low}`–`{treasury_yr_high}`, ~`{treasury_range_position}` of the way up =
  `{treasury_timing_label}`), and the spread `{mortgage_treasury_spread}%` vs the ~1.75% norm
  (`{spread_label}`: wide = rates may fall as spreads normalize; tight = little room).
- Treat this strictly as **timing/context, not a pass/fail gate**: the refinance decision is
  driven by the rate comparison and break-even; the Treasury read informs *act now vs. wait*.
- If any treasury label is `"unavailable"` (short-circuit path or fetch failure), say the
  Treasury context could not be evaluated instead of reporting zeros.

### 6. Workflow & calculator — unchanged

`condition` and `calculator_agent` are untouched. In the short-circuit path the treasury agent
still never runs, so the treasury fields keep their `unavailable`/`None` defaults and the
finalizer reports it wasn't checked.

## Testing — `tests/test_tools.py`

- `classify_rate_timing` (pure, offline, `@pytest.mark.calculation`):
  - favorable (range_position < 33), neutral, elevated (> 66) — assert labels.
  - spread wide (> 2.10), normal, tight (< 1.40) — assert labels.
  - direction rising / falling / flat.
  - edge cases: `yr_high == yr_low` -> range label `unavailable`; mortgage rate `0` -> spread
    label `unavailable`.
- Live (`@pytest.mark.treasury`): `get_treasury_10yr_quote()` returns
  `yr_low < last < yr_high`, all in `(0, 20)`.

## Failure handling summary

| Scenario | Behavior |
|----------|----------|
| CNBC fetch fails | treasury fields -> "unavailable"/None; finalizer says not evaluated |
| `yr_high == yr_low` | range_label -> "unavailable"; spread still computed if possible |
| Mortgage rate missing/0 | spread_label -> "unavailable"; range still computed |
| Short-circuit path (rate already beats market) | treasury agent skipped; fields stay default |

## Out of scope

- Multi-day moving averages or any external history source (FRED).
- Surfacing the new treasury fields in the API response or Streamlit UI beyond the finalizer's
  prose.
- Auto-tuning the threshold constants.

## Open notes for reviewer

- **Thresholds are first-pass defaults** (33/66 range; 1.75 ± 0.35 spread). They are isolated
  module constants so they can be tuned without touching logic. Flag if you want different
  bands.
- **Spread mortgage rate** uses the national average (`national_rate`) as the benchmark
  (the ~1.75% norm is measured against national-average mortgage rates), falling back to the
  effective `market_rate` only if the national figure is unavailable.
