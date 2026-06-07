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
make ui         # poetry run streamlit run src/frontend/Agentic_Refinance_Tool.py
make go         # build + run + ui
make rebuild    # stop + build + run + ui
make stop       # stop & remove the container

# Run the API directly without Docker:
poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload

# Deploy: build & push image to ECR, then pull on EC2 (see makefile):
make push-ecr            # login-ecr + buildx build --push
make full-deploy-prod    # push-ecr + connect to EC2

# Tests (pytest markers: treasury, interest_rate, calculation):
poetry run pytest                              # all tests
poetry run pytest tests/test_tools.py -s       # tool tests (hit LIVE endpoints), -s shows prints
poetry run pytest tests/test_tools.py -m treasury -s   # single marked test
```

Note: `tests/test_tools.py` makes **live** calls to CNBC and Tavily, so it needs network access and `TAVILY_API_KEY`. `tests/test_api_server.py` is an interactive script (prompts via `input()`, posts to a running API) — not a standard pytest test.

## Environment

A `.env` file (gitignored) is required and read by both the app and Docker (`--env-file .env`). Keys used in code: `OPENAI_API_KEY`, `OPENAI_MODEL_NAME`, `TAVILY_API_KEY`, `LOG_TABLE` (DynamoDB table), `AWS_REGION`, `LOCAL_CREDIT_UNION_RATES_URL` (the local credit union "today's featured rates" partial endpoint; the DC-area rate source degrades to unavailable if unset), and the client-side `API_BASE_URL` / `API_PORT` / `API_PATH`.

## Architecture

Request flow: **Streamlit UI** ([src/frontend/Agentic_Refinance_Tool.py](src/frontend/Agentic_Refinance_Tool.py)) → **client** ([src/frontend/client.py](src/frontend/client.py), builds the URL from env vars) → **FastAPI** `POST /refinance_agent/recommendation` ([src/api/api_setup.py](src/api/api_setup.py)) → **LangGraph workflow** → recommendation returned and the request logged to DynamoDB.

### The LangGraph workflow ([src/core/workflow.py](src/core/workflow.py))

A `StateGraph` over the `State` TypedDict ([src/core/define_state_and_llm.py](src/core/define_state_and_llm.py)) with four nodes and one **conditional short-circuit**:

```
market ──> condition ──> if market_rate > interest_rate: finalizer (END)
                         else:                            treasury_yield -> calculator -> finalizer
```

The key control-flow rule: if the fetched market rate is *higher* than the user's current rate, refinancing makes no sense, so the workflow skips the treasury and calculator agents and goes straight to `finalizer`. In that path `treasury_yield`/`new_payment`/etc. stay `None`/`0`, and the finalizer prompt is written to handle those zero values.

### Agents ([src/core/agents.py](src/core/agents.py))

Each agent is a plain function `(State) -> State` that mutates and returns shared state (`market_rate`, `treasury_yield`, `new_payment`, `monthly_savings`, `break_even`, `path`, `num_tool_calls`, `recommendation`). Agents do **not** use a prebuilt agent/tool loop — they manually `llm_with_tools.invoke(prompt)`, check `resp.tool_calls`, and execute via a shared `ToolNode` (`tool_nodes.invoke({"messages": [resp]})`), then parse the tool result text. When extending an agent, follow this same manual pattern and remember to append to `state["path"]` and bump `state["num_tool_calls"]`.

- `market_expert_agent` — Tavily search for current avg 30-yr rate; a second LLM call extracts the bare numeric value.
- `treasury_yield_agent` — fetches 10-yr Treasury yield.
- `calculator_agent` — calls the break-even tool; expects JSON-parseable tuple output.
- `finalizer_agent` — loads its prompt from [src/prompts/finalizer_prompt.txt](src/prompts/finalizer_prompt.txt) and writes the final recommendation.

### Tools ([src/core/tools.py](src/core/tools.py)) — dual definitions

Every tool exists **twice**: a plain function (e.g. `get_treasury_10yr_yield`) and a `@tool`-decorated wrapper that just calls it (e.g. `get_treasury_10yr_yield_for_agent`). This split is intentional — pytest cannot call the `@tool`-wrapped versions directly, so tests import the plain functions while agents bind the `_for_agent` variants. If you add a tool, add both versions and register the `_for_agent` one in the `ToolNode` lists in both [agents.py](src/core/agents.py) and [define_state_and_llm.py](src/core/define_state_and_llm.py).

### Gotchas

- **Run from the repo root.** `finalizer_agent` reads `src/prompts/finalizer_prompt.txt` via a relative path, so the working directory must be the project root (this is why the Dockerfile/uvicorn run from `/app`).
- **Imports assume `src` on the path.** Package config exposes `core` (and tests set `pythonpath = ["src"]`), so modules import as `from core...` / `from api...` rather than `from src.core...`.
- The OpenAI model is whatever `OPENAI_MODEL_NAME` resolves to; there is commented-out Ollama support in [define_state_and_llm.py](src/core/define_state_and_llm.py) if running locally without OpenAI.

### Supporting pieces

- **DynamoDB logging** ([src/core/db_logging.py](src/core/db_logging.py)) — each recommendation request is logged to the `LOG_TABLE`; failures are caught and logged but do not fail the request.
- **Scheduled email** ([src/schedule/lambda_function.py](src/schedule/lambda_function.py)) — an AWS Lambda that POSTs fixed inputs to the API daily and publishes the recommendation to an SNS topic (email).
