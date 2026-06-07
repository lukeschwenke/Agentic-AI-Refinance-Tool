# Dual-Source Market Rate (national + DC-area local CU) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `market_expert_agent` to gather two mortgage rates — a national average (Tavily) and a Washington DC-area rate from an unnamed local credit union — store both, use the lower as the effective `market_rate`, and have the finalizer narrate both and say which it used.

**Architecture:** A new deterministic tool fetches a server-rendered "today's featured rates" HTML partial (URL from `LOCAL_CREDIT_UNION_RATES_URL`) via `requests.get` and parses the Conforming 30-Year Fixed rows with stdlib `re`. Two pure helpers live in `tools.py` (no LLM imports, so they unit-test without an API key): `parse_conforming_30yr_avg(html)` and `consolidate_rates(national, local)`. `market_expert_agent` calls the Tavily flow and the new tool, then `consolidate_rates` picks the lower non-zero rate. The finalizer prompt gains three variables.

**Tech Stack:** Python, LangGraph/LangChain, `requests`, stdlib `re`, pytest, Poetry.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/core/tools.py` | Data-fetch + pure rate logic (no LLM) | Add `parse_conforming_30yr_avg`, `consolidate_rates`, `get_local_credit_union_30yr_rate`, `get_local_credit_union_30yr_rate_for_agent` |
| `src/core/define_state_and_llm.py` | `State` shape + bound LLM tools | Add 3 state fields; register tool in `bind_tools` |
| `src/core/agents.py` | Agent functions + `ToolNode` | Register tool in `ToolNode`; rewrite `market_expert_agent`; add `_get_national_rate_via_tavily` helper |
| `src/api/api_setup.py` | Initial state construction | Add 3 fields to `initial_state` |
| `src/prompts/finalizer_prompt.txt` | Finalizer instructions | Add RATE SOURCES section + 3 vars |
| `tests/test_tools.py` | Tool/logic tests | Add parser, consolidation, and live-fetch tests |
| `pyproject.toml` | pytest markers | Add `local_cu` marker |
| `.env` | Secrets/config (gitignored) | Add `LOCAL_CREDIT_UNION_RATES_URL` |

---

## Task 1: HTML parser — `parse_conforming_30yr_avg`

**Files:**
- Modify: `src/core/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tools.py` (update the import line to include the new name):

```python
from core.tools import (
    get_treasury_10yr_yield,
    get_rates_search_tool,
    calculate_estimates_and_breakeven,
    parse_conforming_30yr_avg,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_tools.py -k parse_conforming -s`
Expected: FAIL — `ImportError: cannot import name 'parse_conforming_30yr_avg'`.

- [ ] **Step 3: Write minimal implementation**

In `src/core/tools.py`, add `import re` near the top (after `import requests`), then add this function above the `@tool` section (e.g., after `get_rates_search_tool`):

```python
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
    rates = [float(m) for m in re.findall(r'aria-label="Rate (\d+\.\d+)%"', block)]
    if not rates:
        raise ValueError("No Rate values parsed from Conforming 30-Year block")

    return sum(rates) / len(rates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_tools.py -k parse_conforming -s`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/core/tools.py tests/test_tools.py
git commit -m "feat: parse local CU conforming 30yr rate average from rates HTML"
```

---

## Task 2: Consolidation logic — `consolidate_rates`

**Files:**
- Modify: `src/core/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Add `consolidate_rates` to the `from core.tools import (...)` block, then add:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/test_tools.py -k consolidate -s`
Expected: FAIL — `ImportError: cannot import name 'consolidate_rates'`.

- [ ] **Step 3: Write minimal implementation**

In `src/core/tools.py`, add module-level label constants and the function (place near `parse_conforming_30yr_avg`):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/test_tools.py -k consolidate -s`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/core/tools.py tests/test_tools.py
git commit -m "feat: consolidate national + local rates by lowest available"
```

---

## Task 3: Network tool — `get_local_credit_union_30yr_rate` (+ `_for_agent`)

**Files:**
- Modify: `src/core/tools.py`
- Modify: `pyproject.toml`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Add the `local_cu` pytest marker**

In `pyproject.toml`, change the markers line under `[tool.pytest.ini_options]` from:

```toml
markers = ["integration: tests that hit live endpoints"]
```

to:

```toml
markers = [
    "integration: tests that hit live endpoints",
    "local_cu: live test for the local credit union rate fetch",
]
```

- [ ] **Step 2: Write the failing live test**

Add `get_local_credit_union_30yr_rate` to the `from core.tools import (...)` block, and add `import os` at the top of `tests/test_tools.py`. Then add:

```python
@pytest.mark.local_cu
def test_live_local_credit_union_30yr_rate():
    """Live: fetch + parse the local CU conforming 30yr rate. Skips if URL unset."""
    if not os.getenv("LOCAL_CREDIT_UNION_RATES_URL"):
        pytest.skip("LOCAL_CREDIT_UNION_RATES_URL not set")
    val = get_local_credit_union_30yr_rate()
    print(f"TEST - Local CU 30yr Rate = {val}")
    assert isinstance(val, float)
    assert 0.0 < val < 20.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `poetry run pytest tests/test_tools.py -k local_credit_union -s`
Expected: FAIL — `ImportError: cannot import name 'get_local_credit_union_30yr_rate'`.

- [ ] **Step 4: Write minimal implementation**

In `src/core/tools.py`, add a User-Agent constant near the top and the two functions. Put the plain function near `parse_conforming_30yr_avg`, and the `@tool` wrapper in the `@tool` section next to `get_rates_search_tool_for_agent`:

```python
LOCAL_CU_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.5993.89 Safari/537.36"
)


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
```

And in the `@tool` section:

```python
@tool
def get_local_credit_union_30yr_rate_for_agent() -> float:
    """Get the local credit union's (Washington DC area) average 30-year fixed rate."""
    return get_local_credit_union_30yr_rate()
```

- [ ] **Step 5: Run test to verify it passes (or skips cleanly)**

Run (without the env var set): `poetry run pytest tests/test_tools.py -k local_credit_union -s`
Expected: SKIPPED ("LOCAL_CREDIT_UNION_RATES_URL not set") — confirms import works and the skip guard fires.

Run (with the env var set, to exercise the live path):
`LOCAL_CREDIT_UNION_RATES_URL=<url> poetry run pytest tests/test_tools.py -m local_cu -s`
Expected: PASS, prints a rate in (0, 20).

- [ ] **Step 6: Commit**

```bash
git add src/core/tools.py tests/test_tools.py pyproject.toml
git commit -m "feat: add local CU 30yr rate tool (env-driven URL) + live test"
```

---

## Task 4: Register the tool with the agent toolset

**Files:**
- Modify: `src/core/agents.py:8-10`
- Modify: `src/core/define_state_and_llm.py:37-39`

- [ ] **Step 1: Add to the `ToolNode` in agents.py**

Replace the `tool_nodes = ToolNode([...])` block (`src/core/agents.py:8-10`) with:

```python
tool_nodes = ToolNode([get_treasury_10yr_yield_for_agent,
                       get_rates_search_tool_for_agent,
                       get_local_credit_union_30yr_rate_for_agent,
                       calculate_estimates_and_breakeven_for_agent])
```

- [ ] **Step 2: Add to `bind_tools` in define_state_and_llm.py**

Replace the `llm_with_tools = llm.bind_tools([...])` block (`src/core/define_state_and_llm.py:37-39`) with:

```python
llm_with_tools = llm.bind_tools([get_treasury_10yr_yield_for_agent,
                                 get_rates_search_tool_for_agent,
                                 get_local_credit_union_30yr_rate_for_agent,
                                 calculate_estimates_and_breakeven_for_agent])
```

- [ ] **Step 3: Verify the modules import cleanly**

Run: `poetry run python -c "import core.agents; print('agents import OK')"`
Expected: prints `agents import OK` (requires `OPENAI_API_KEY` in env/.env, since importing agents constructs the LLM clients). If it fails only due to a missing key, set it from `.env` first.

- [ ] **Step 4: Commit**

```bash
git add src/core/agents.py src/core/define_state_and_llm.py
git commit -m "chore: register local CU rate tool in ToolNode and bound tools"
```

---

## Task 5: Add state fields + initialize them

**Files:**
- Modify: `src/core/define_state_and_llm.py:10-21`
- Modify: `src/api/api_setup.py:52-64`

- [ ] **Step 1: Add fields to the `State` TypedDict**

In `src/core/define_state_and_llm.py`, inside `class State(TypedDict):`, add these three lines after `market_rate: float`:

```python
    national_rate: float
    local_credit_union_rate: float
    market_rate_source: str
```

- [ ] **Step 2: Initialize them in the API's `initial_state`**

In `src/api/api_setup.py`, in the `initial_state` dict, add after `"market_rate": None,`:

```python
            "national_rate": None,
            "local_credit_union_rate": None,
            "market_rate_source": "",
```

- [ ] **Step 3: Verify imports**

Run: `poetry run python -c "import core.define_state_and_llm; import api.api_setup; print('state import OK')"`
Expected: prints `state import OK`.

- [ ] **Step 4: Commit**

```bash
git add src/core/define_state_and_llm.py src/api/api_setup.py
git commit -m "feat: add national_rate, local_credit_union_rate, market_rate_source to state"
```

---

## Task 6: Rewrite `market_expert_agent` to use both sources

**Files:**
- Modify: `src/core/agents.py:12-41`

- [ ] **Step 1: Replace `market_expert_agent` and add the Tavily helper**

Replace the entire `market_expert_agent` function (`src/core/agents.py:12-41`) with the following two functions:

```python
def _get_national_rate_via_tavily() -> float:
    """National average via Tavily search + a follow-on LLM numeric extraction.
    Returns 0.0 on any failure so the source can be ignored downstream."""
    prompt = PromptTemplate(template="""
                            You are a mortgage market expert. You should summarize some recent articles to get 
                            an average mortgage interest rate people are seeing right now by 
                            calling the `get_rates_search_tool_for_agent`.
                            """)
    try:
        resp = llm_with_tools.invoke(prompt.format())
        if not resp.tool_calls:
            return 0.0
        tool_result = tool_nodes.invoke({"messages": [resp]})
        message = tool_result["messages"][0].content
        follow_on_prompt = f"""Extract the average mortgage interest rate value from this body of text: {message}
                              You must ONLY return the numerical value up to two decimal places.
                              Example answer: 5.32"""
        updated_resp = llm.invoke(follow_on_prompt)
        return float(updated_resp.content)
    except Exception:
        return 0.0


# Agent #1
def market_expert_agent(state: State) -> dict:
    # Source 1: national average (Tavily search + LLM extraction)
    national_rate = _get_national_rate_via_tavily()

    # Source 2: local credit union, Washington DC area (deterministic fetch + parse)
    try:
        local_rate = get_local_credit_union_30yr_rate()
    except Exception:
        local_rate = 0.0

    # Effective market rate = lower of the available (non-zero) sources
    market_rate, source = consolidate_rates(national_rate, local_rate)
    if market_rate > 0:
        print("===SUCCESSFULLY EXECUTED MARKET RESEARCH AGENT TOOL CALL===")

    state["national_rate"] = national_rate
    state["local_credit_union_rate"] = local_rate
    state["market_rate"] = market_rate
    state["market_rate_source"] = source
    state["num_tool_calls"] += 2
    state["path"].append("market_expert_agent")
    return state
```

Note: `consolidate_rates` and `get_local_credit_union_30yr_rate` are imported via the
existing `from core.tools import *` at the top of `agents.py` (both names are
underscore-free, so `import *` exports them).

- [ ] **Step 2: Verify the module imports**

Run: `poetry run python -c "import core.agents; print('agents OK')"`
Expected: prints `agents OK`.

- [ ] **Step 3: Smoke-test the consolidation wiring without network/LLM**

Run:
```bash
poetry run python -c "
from core.tools import consolidate_rates
assert consolidate_rates(6.55, 6.3125) == (6.3125, 'Washington DC area')
assert consolidate_rates(0.0, 0.0) == (0.0, 'unavailable')
print('consolidation wiring OK')
"
```
Expected: prints `consolidation wiring OK`.

- [ ] **Step 4: Commit**

```bash
git add src/core/agents.py
git commit -m "feat: market_expert_agent gathers national + DC-area rates, lower wins"
```

---

## Task 7: Finalizer narrates both rates

**Files:**
- Modify: `src/prompts/finalizer_prompt.txt`
- Modify: `src/core/agents.py` (the `finalizer_agent` `PromptTemplate` input_variables and `prompt.format(...)` call)

- [ ] **Step 1: Add a RATE SOURCES section to the prompt**

In `src/prompts/finalizer_prompt.txt`, insert this block immediately after the `# FORMAT RULES` section (before `# CORE DECISION RULES`):

```
# RATE SOURCES — you MUST report all of the following
- State that you searched nationwide average mortgage rates and found a national average of {national_rate}%.
- State that you also obtained a rate of {local_credit_union_rate}% from a local credit union serving the Washington DC area. Do NOT name the institution.
- State that the figure used for all calculations is the {market_rate_source} rate of {market_rate}%, and explain you selected the LOWER of the two available rates because it is the most favorable comparison for the user.
- If any of these rate values is 0 (or the source is "unavailable"), say that source could not be retrieved instead of reporting a 0% rate.
```

- [ ] **Step 2: Add the new variables to the finalizer `PromptTemplate`**

In `src/core/agents.py`, in `finalizer_agent`, update the `PromptTemplate(input_variables=[...])` list to include the three new names. The list should read:

```python
    prompt = PromptTemplate(input_variables=["interest_rate",
                                             "treasury_yield",
                                             "market_rate",
                                             "current_payment",
                                             "monthly_savings",
                                             "break_even",
                                             "new_payment",
                                             "mortgage_balance",
                                             "national_rate",
                                             "local_credit_union_rate",
                                             "market_rate_source"],
                              template=FINALIZER_PROMPT)
```

- [ ] **Step 3: Pass the new variables in `prompt.format(...)`**

In `finalizer_agent`, update the `final_prompt = prompt.format(...)` call to add the three new arguments:

```python
    final_prompt = prompt.format(
        interest_rate=state['interest_rate'],
        current_payment=state['current_payment'],
        mortgage_balance=state['mortgage_balance'],
        market_rate=state['market_rate'],
        treasury_yield=state['treasury_yield'],
        monthly_savings=state['monthly_savings'],
        break_even=state['break_even'],
        new_payment=state['new_payment'],
        national_rate=state['national_rate'],
        local_credit_union_rate=state['local_credit_union_rate'],
        market_rate_source=state['market_rate_source'],
    )
```

- [ ] **Step 4: Verify the prompt formats without missing-key errors**

Run:
```bash
poetry run python -c "
from pathlib import Path
from langchain_core.prompts import PromptTemplate
tmpl = Path('src/prompts/finalizer_prompt.txt').read_text()
p = PromptTemplate(input_variables=['interest_rate','treasury_yield','market_rate','current_payment','monthly_savings','break_even','new_payment','mortgage_balance','national_rate','local_credit_union_rate','market_rate_source'], template=tmpl)
print(p.format(interest_rate=7.1, treasury_yield=4.0, market_rate=6.31, current_payment=3200, monthly_savings=150, break_even=20, new_payment=3050, mortgage_balance=500000, national_rate=6.55, local_credit_union_rate=6.31, market_rate_source='Washington DC area')[:200])
print('PROMPT FORMAT OK')
"
```
Expected: prints the first 200 chars of the rendered prompt then `PROMPT FORMAT OK` (no `KeyError`).

- [ ] **Step 5: Commit**

```bash
git add src/prompts/finalizer_prompt.txt src/core/agents.py
git commit -m "feat: finalizer reports national + DC-area rates and which drove the math"
```

---

## Task 8: Configure the rates URL env var

**Files:**
- Modify: `.env` (gitignored — local only)
- Modify: `CLAUDE.md` (document the new key)

- [ ] **Step 1: Add the URL to `.env`**

Append to `.env` (replace `<rates-partial-url>` with the actual endpoint discovered during design — the `.../responsive/todaysfeaturedrates/partial` URL):

```
LOCAL_CREDIT_UNION_RATES_URL=<rates-partial-url>
```

- [ ] **Step 2: Document the key in CLAUDE.md**

In `CLAUDE.md`, in the `## Environment` section, add `LOCAL_CREDIT_UNION_RATES_URL` to the list of keys used in code, described as: "the local credit union 'today's featured rates' partial endpoint; the DC-area rate source degrades to unavailable if unset."

- [ ] **Step 3: Confirm `.env` is gitignored (no secret committed)**

Run: `git check-ignore .env && echo "ignored OK"`
Expected: prints `.env` then `ignored OK`.

- [ ] **Step 4: Commit (docs only — `.env` is ignored)**

```bash
git add CLAUDE.md
git commit -m "docs: document LOCAL_CREDIT_UNION_RATES_URL env var"
```

---

## Task 9: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite (no network/LLM)**

Run: `poetry run pytest tests/test_tools.py -m calculation -s`
Expected: all parser + consolidation tests PASS.

- [ ] **Step 2: Run the live local-CU test**

Run: `LOCAL_CREDIT_UNION_RATES_URL=<url> poetry run pytest tests/test_tools.py -m local_cu -s`
Expected: PASS, prints a plausible rate (~6.3).

- [ ] **Step 3: Exercise the API end-to-end**

With `.env` populated (OpenAI + Tavily + `LOCAL_CREDIT_UNION_RATES_URL`), start the API:
`poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload`

In another shell, POST a request where the user's rate is high enough to continue past the short-circuit:
```bash
curl -s -X POST http://127.0.0.1:8000/refinance_agent/recommendation \
  -H "Content-Type: application/json" \
  -d '{"interest_rate": 7.5, "current_payment": 3500, "mortgage_balance": 500000}' | python -m json.tool
```
Expected: HTTP 200; `recommendation` text mentions **both** a national average rate and a Washington DC-area rate, states which rate it used for the math, and does **not** name the institution. `num_tool_calls` ≥ 2; `path` includes `market_expert_agent`.

- [ ] **Step 4: Confirm the short-circuit path still narrates both rates**

POST a request where the user's rate already beats the market (low rate):
```bash
curl -s -X POST http://127.0.0.1:8000/refinance_agent/recommendation \
  -H "Content-Type: application/json" \
  -d '{"interest_rate": 3.0, "current_payment": 2100, "mortgage_balance": 500000}' | python -m json.tool
```
Expected: HTTP 200; recommendation tells the user NOT to refinance, still reports the national and DC-area rates, and notes treasury/savings were not computed.

- [ ] **Step 5: Final commit (if any verification tweaks were needed)**

```bash
git add -A
git commit -m "test: verify dual-source market rate end-to-end"
```

---

## Self-Review

**Spec coverage:**
- New tool fetching `/todaysfeaturedrates/partial` via `requests.get`, URL from env var → Task 3. ✓
- stdlib `re` parse of Conforming 30yr, average two rows → Task 1. ✓
- Dual-definition tool + register in both ToolNode/bind_tools → Tasks 3, 4. ✓
- State fields `national_rate`, `local_credit_union_rate`, `market_rate_source` → Task 5. ✓
- `market_expert_agent` gathers both, lower-of-two effective rate, failure handling → Tasks 2, 6. ✓
- Workflow/calculator unchanged → no task needed (verified unaffected; they read `market_rate`). ✓
- Finalizer narrates both + which used, institution unnamed → Task 7. ✓
- Tests: live `local_cu` marker + deterministic fixture parse → Tasks 1, 3. ✓
- Env doc → Task 8. ✓
- Failure matrix (Tavily/local/both fail) → covered by `consolidate_rates` tests (Task 2) + try/except in agent (Task 6). ✓

**Placeholder scan:** Only `<rates-partial-url>` / `<url>` placeholders remain, intentionally (the URL is a secret kept out of the repo, supplied at runtime). No code placeholders.

**Type consistency:** `consolidate_rates(national, local) -> (float, str)` used consistently in Tasks 2 and 6. Label strings (`"national average"`, `"Washington DC area"`, `"unavailable"`) match between `consolidate_rates` constants (Task 2) and the test expectations (Tasks 2, 6) and the finalizer narration (Task 7). `parse_conforming_30yr_avg(html) -> float` consistent across Tasks 1 and 3.
