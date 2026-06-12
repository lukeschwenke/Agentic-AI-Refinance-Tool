# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Multi-agent tool that advises whether a user should refinance their mortgage. A Streamlit UI collects mortgage details and calls a FastAPI backend, which runs a LangGraph workflow of cooperating agents that fetch live market data, compute break-even, and produce a natural-language recommendation. The LLM is OpenAI (selected via the `OPENAI_MODEL_NAME` env var, not hardcoded).

## Commands

Dependencies are managed with Poetry. Run app/Python entrypoints through `poetry run`.

```bash
# Local dev loop (Docker for API + Streamlit UI), defined in `makefile`:
make build      # docker buildx build the API image (linux/amd64)
make run        # run the API container, reading .env, on port 8000
make ui         # poetry run streamlit run src/frontend/RefiAI_Main_Page.py
make go         # build + run + ui
make rebuild    # stop + build + run + ui
make stop       # stop & remove the container

# Run the API directly without Docker:
poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload

# Deploy: build & push image to ECR, then pull on EC2 (see makefile):
make push-ecr            # login-ecr + buildx build --push
make full-deploy-prod    # push-ecr + connect to EC2

# Tests (pytest markers: treasury, interest_rate, rate_outlook, local_cu = LIVE;
# calculation = offline math; finalizer_eval = live-LLM prompt evals, opt-in):
poetry run pytest -m calculation               # offline unit tests (fast, no network)
poetry run pytest tests/test_workflow.py       # offline graph-path tests (LLMs stubbed)
poetry run pytest tests/test_tools.py -m treasury -s   # single live marked test
poetry run pytest -m finalizer_eval -s         # live finalizer prompt evals (costs LLM calls)
```

Note: the live-marked tests call CNBC and Tavily, so they need network access and `TAVILY_API_KEY`. `scripts/test_api_server.py` is an interactive script (prompts via `input()`, posts to a running API) — not a pytest test.

## Environment

A `.env` file (gitignored) is required and read by both the app and Docker (`--env-file .env`). Keys used in code: `OPENAI_API_KEY`, `OPENAI_MODEL_NAME`, `TAVILY_API_KEY`, `LOG_TABLE` (DynamoDB table), `AWS_REGION`, `LOCAL_CREDIT_UNION_RATES_URL` (the local credit union "today's featured rates" partial endpoint; the DC-area rate source degrades to unavailable if unset), and the client-side `API_BASE_URL` / `API_PORT` / `API_PATH`.

## Architecture

Request flow: **Streamlit UI** ([src/frontend/RefiAI_Main_Page.py](src/frontend/RefiAI_Main_Page.py)) → **client** ([src/frontend/client.py](src/frontend/client.py), builds the URL from env vars) → **FastAPI** `POST /refinance_agent/recommendation` ([src/api/api_setup.py](src/api/api_setup.py)) → **LangGraph workflow** → recommendation returned and the request logged to DynamoDB.

### The LangGraph workflow ([src/core/workflow.py](src/core/workflow.py))

A `StateGraph` over the `State` TypedDict ([src/core/define_state_and_llm.py](src/core/define_state_and_llm.py)) with six nodes and one **conditional short-circuit**:

```
market ──> condition ──> market_rate unavailable (<= 0) OR > interest_rate: finalizer (END)
                         else: treasury_yield -> rate_outlook -> calculator -> strategy -> finalizer
```

Two control-flow rules: (1) if the fetched market rate is *higher* than the user's current rate, refinancing makes no sense; (2) if **both** rate sources failed (`market_rate <= 0`), there is nothing valid to analyze. Either way the workflow jumps straight to `finalizer`, downstream state stays `None`/empty, and the finalizer's precomputed `decision_hint` makes it report honestly (DO_NOT_REFINANCE vs RATES_UNAVAILABLE).

### Agents ([src/core/agents.py](src/core/agents.py))

Each agent is a plain function `(State) -> State` that mutates and returns shared state. The design rule: **LLMs decide and explain; Python computes.** Every number comes from deterministic code in [tools.py](src/core/tools.py); LLM calls are single-shot and, where they return data, use `llm.with_structured_output(<Pydantic model>)` so values are guaranteed valid (see `RateOutlookRead`, `StrategyPick`). When extending an agent: append to `state["path"]`, and bump `state["num_tool_calls"]` **only for successful external data fetches** (it is a fetch counter, not a step counter).

- `market_expert_agent` — two deterministic sources: Tavily answer parsed by `parse_rate_from_text` (LLM extraction only as fallback) + the local credit union scrape; lower non-zero rate wins (`consolidate_rates`).
- `treasury_yield_agent` — CNBC quote (yield + 52-wk hi/lo + prev close) → `classify_rate_timing` range/direction/spread labels. No LLM.
- `rate_outlook_agent` — Tavily search of Fed/forecaster commentary → structured classification (falling/stable/rising, act/wait/neutral).
- `calculator_agent` — builds the scenario set deterministically via `build_refinance_scenarios` (keep-payoff-date / 30-yr reset / 15-yr), resolving defaults (term solved from the payment, ~2% closing costs, 7-yr horizon). No LLM.
- `strategy_agent` — one structured LLM call that picks a scenario (or "none") and explains; copies the pick's numbers into the primary state fields.
- `finalizer_agent` — loads [src/prompts/finalizer_prompt.txt](src/prompts/finalizer_prompt.txt); **all values are pre-formatted in Python** (`_fmt_*` helpers) and the verdict branch is precomputed (`_decision_hint`) so the LLM only narrates — never recompute or reformat numbers in the prompt.

### Tools ([src/core/tools.py](src/core/tools.py))

Plain functions only (the old `@tool`/`ToolNode` layer was removed when the agents went deterministic). The three live fetchers (CNBC, credit union page, Tavily searches) are wrapped with `_with_retries` (3 attempts, linear backoff) and `_ttl_cache` (~15 min) — failures are never cached. Pure math (`monthly_payment`, `build_refinance_scenarios`, `classify_rate_timing`, `parse_rate_from_text`, etc.) is fully unit-tested offline via the `calculation` marker.

### Gotchas

- **Run from the repo root.** `finalizer_agent` reads `src/prompts/finalizer_prompt.txt` via a relative path, so the working directory must be the project root (this is why the Dockerfile/uvicorn run from `/app`).
- **Imports assume `src` on the path.** Package config exposes `core` (and tests set `pythonpath = ["src"]`), so modules import as `from core...` / `from api...` rather than `from src.core...`.
- The OpenAI model is whatever `OPENAI_MODEL_NAME` resolves to; there is commented-out Ollama support in [define_state_and_llm.py](src/core/define_state_and_llm.py) if running locally without OpenAI.

### Supporting pieces

- **DynamoDB logging** ([src/core/db_logging.py](src/core/db_logging.py)) — each recommendation request is logged to the `LOG_TABLE`; failures are caught and logged but do not fail the request.
- **Scheduled email** ([src/schedule/lambda_function.py](src/schedule/lambda_function.py)) — an AWS Lambda that POSTs fixed inputs to the API daily and publishes the recommendation to an SNS topic (email).
