# Dual-source market rate: Tavily (national) + local credit union (DC-area)

**Date:** 2026-06-06
**Status:** Approved (design)
**Component:** `market_expert_agent` and supporting tool/state/finalizer

## Summary

Extend the `market_expert_agent` to gather mortgage rates from **two** sources instead
of one, and carry both numbers through to the finalizer:

- **National average** — the existing Tavily web-search flow (`national_rate`).
- **Washington DC area** — a new tool that fetches a **local credit union's** published
  "Today's Featured Rates" and parses the Conforming 30-Year Fixed rate
  (`local_credit_union_rate`). The institution serves the DC metro area, so its quote
  reflects that region.

> **Identity is intentionally not named** in source code or this document. The exact
> rates URL (which would reveal the institution) is supplied via the
> `LOCAL_CREDIT_UNION_RATES_URL` environment variable, kept in the gitignored `.env`.
> Revealing the **region** ("Washington DC area") is fine; revealing the specific
> credit union is not.

The two numbers are **not blended into a single average**. Both are stored separately.
An **effective rate** (`market_rate`) — the **lower of the two** available numbers —
drives the break-even math and the refinance short-circuit. The finalizer narrates both
numbers and states which one it used for the math.

## Motivation

Today a single Tavily-derived `market_rate` drives everything. Adding a real, live
lender quote gives the user a concrete, regionally-relevant data point alongside the
national average, and a stricter, more trustworthy basis for the refinance decision.

## Data source (production mechanism)

Production fetches the local credit union rates with a plain `requests.get()` — **no
browser, no MCP, no auth** — exactly like the existing CNBC treasury tool
(`get_treasury_10yr_yield`).

- **Endpoint:** read from the `LOCAL_CREDIT_UNION_RATES_URL` environment variable. The
  literal URL is **not** hardcoded in source or committed docs. It points at the
  institution's hosted "Today's Featured Rates" partial (path pattern
  `.../responsive/todaysfeaturedrates/partial`).
- Verified: that endpoint returns HTTP 200, `text/html` (~52 KB) of **server-rendered**
  HTML with the rate tables, with only a `User-Agent` header and no cookies/session.
- The institution's React SPA calls this partial; Playwright MCP was used **only at
  dev-time to discover** the endpoint. It is not a runtime dependency.

Relevant markup (stable, platform-generic anchors used for parsing — these do not name
the institution):

```html
<div class="product-type"> First Mortgage - Conforming Limits </div>
  <div class="product">
    <a ... class='tfr-product' data-productid="75507" ...> 30 Year Fixed Rate </a>
    <div class="rates" role="table">
      ... Rate 6.250% | APR 6.391% | Points 1.000%
      ... Rate 6.375% | APR 6.433% | Points 0.125%
```

## Scope decisions (locked)

| Decision | Choice |
|----------|--------|
| Which product | **Conforming 30-Year Fixed only** (exclude HomeReady, 100%, Jumbo) |
| Two rate rows per product | **Average the two Rate-column values** (6.250% + 6.375% → 6.3125%) |
| Combining the two sources | **Do not blend** — store both; effective `market_rate` = **lower of the two** |
| Which rate drives math/short-circuit | The **effective (lower)** rate |
| Finalizer behavior | Narrate both rates **and** state which rate it used for the math |
| HTML parsing | **stdlib `re`** (no new dependency) |
| Fetch mechanism | `requests.get()` (no browser) |
| Institution identity | **Hidden** — URL via `LOCAL_CREDIT_UNION_RATES_URL` env var; generic naming in code |

## Detailed design

### 1. New tool — `get_local_credit_union_30yr_rate()` / `_for_agent`

In `src/core/tools.py`, following the existing dual-definition pattern (plain function
for pytest, `@tool` wrapper for agents):

- Plain `get_local_credit_union_30yr_rate() -> float`:
  - Read the URL from `os.getenv("LOCAL_CREDIT_UNION_RATES_URL")`; if unset, treat as a
    failed source (return/raise per the failure convention below).
  - `requests.get(url, headers={UA}, timeout=8)`, `raise_for_status()`.
  - With stdlib `re`: isolate the **"First Mortgage - Conforming Limits" → "30 Year
    Fixed Rate"** block (anchored on `product-type` text + the `tfr-product` anchor),
    extract the two **Rate**-column percentages (not APR, not Points), and return their
    average as a `float`.
  - On any failure (missing env var, network error, markup drift, zero rows parsed):
    raise `ValueError` (mirrors `get_treasury_10yr_yield`'s failure style). The agent
    converts this to the `0.0` failed-source sentinel.
- `@tool`-decorated `get_local_credit_union_30yr_rate_for_agent()` that just calls the
  plain function.
- Register `get_local_credit_union_30yr_rate_for_agent` in the `ToolNode` lists in
  **both** `src/core/agents.py` and `src/core/define_state_and_llm.py` (and in the
  `llm.bind_tools([...])` call).

### 2. State changes — `src/core/define_state_and_llm.py`

Add to the `State` TypedDict:

```python
national_rate: float              # Tavily national average
local_credit_union_rate: float    # DC-area conforming 30yr (avg of two rows)
market_rate_source: str           # human-readable label of the rate used for the math
```

`market_rate` remains and now holds the **effective (lower)** rate.

### 3. `market_expert_agent` changes — `src/core/agents.py`

- Keep the existing Tavily flow (search tool + follow-on LLM numeric extraction) →
  `national_rate`. On failure, `national_rate = 0.0`.
- Add a local-credit-union step using the deterministic tool →
  `local_credit_union_rate`. On failure, `local_credit_union_rate = 0.0`.
- **Consolidation:** from the set of **non-zero** values, `market_rate = min(...)` and
  set `market_rate_source` to the matching label
  (`"Washington DC area"` or `"national average"`).
  - If only one source succeeds, use it (and its label).
  - If both fail, `market_rate = 0.0`, `market_rate_source = "unavailable"`.
- Store `national_rate`, `local_credit_union_rate`, `market_rate`,
  `market_rate_source`.
- Bump `num_tool_calls` (now reflects 2 tool calls) and append `"market_expert_agent"`
  to `path`, as today.

### 4. Workflow & calculator — unchanged

`condition()` in `src/core/workflow.py` and `calculator_agent` keep reading
`market_rate`. Because it is now the **lower** of the two, the "your rate already beats
the market" short-circuit only fires when the user's rate beats **both** sources — the
correct, stricter semantics. In the short-circuit path, `treasury_yield`/`new_payment`/
etc. remain `0`/`None` as today, and both `national_rate` and `local_credit_union_rate`
are still populated (the market agent always runs first), so the finalizer can narrate
them in either path.

### 5. Finalizer prompt changes — `src/prompts/finalizer_prompt.txt`

Add template variables `{national_rate}`, `{local_credit_union_rate}`,
`{market_rate_source}` and a new "RATE SOURCES" section instructing the finalizer to:

- State that it searched **nationwide average** rates and found **{national_rate}%** (via
  web search).
- State the **{local_credit_union_rate}%** figure and that it comes from **a local
  credit union serving the Washington DC area** (do **not** name the institution).
- State which rate it **used for the math** (`{market_rate_source}`, value
  `{market_rate}%`) and that it chose the **lower** of the two as the most favorable
  comparison.
- If a source is `0`/unavailable, say so plainly rather than reporting a 0% rate.

Pass the new variables in the `prompt.format(...)` call in `finalizer_agent`
(`src/core/agents.py`).

### 6. Tests — `tests/test_tools.py`

- New `local_cu` pytest marker (register in `pyproject.toml` markers if markers are
  declared there).
- **Live test** (`@pytest.mark.local_cu`): calls `get_local_credit_union_30yr_rate()`,
  asserts the result is a `float` in `0.0 < rate < 20.0`. Skips gracefully if
  `LOCAL_CREDIT_UNION_RATES_URL` is unset.
- **Deterministic parse test:** parse a committed HTML fixture (a saved copy of the
  partial response, with no identifying host in the filename/content) and assert the
  function returns the expected averaged value (6.3125). This guards against markup
  drift without requiring network.

## Environment

Add to `.env` (gitignored) and document alongside the other keys:

- `LOCAL_CREDIT_UNION_RATES_URL` — the rates partial endpoint. Required for the DC-area
  source; if unset, that source degrades to "unavailable" and the app falls back to the
  national rate.

## Failure handling summary

| Scenario | Behavior |
|----------|----------|
| Tavily fails | `national_rate = 0.0`; effective rate = `local_credit_union_rate`; finalizer notes national unavailable |
| Local CU fails / env var unset | `local_credit_union_rate = 0.0`; effective rate = `national_rate`; finalizer notes DC-area unavailable |
| Both fail | `market_rate = 0.0`; existing zero-handling in finalizer applies |
| Markup drift | Parse raises → treated as local-CU failure; deterministic test flags it in CI |

## Out of scope

- Other products (HomeReady, 100% financing, Jumbo, ARMs, HELOC).
- Caching/rate-limiting the rates fetch.
- Configurable weighting/blending (explicitly rejected in favor of lower-of-two).
- Surfacing both rates in the Streamlit UI beyond what the finalizer text already says.

## Open notes for reviewer

- **Two-row averaging:** we average the 1-point (6.250%) and near-par (6.375%) rows. An
  alternative is to use only the near-par row as more apples-to-apples vs a no-points
  current rate. Defaulted to averaging; flag if the near-par row is preferred.
- **Git history:** the first commit of this spec (34b46f8) named the institution
  explicitly. If keeping that name out of history matters, squash/amend before pushing.
