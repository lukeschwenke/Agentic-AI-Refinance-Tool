# Agentic Refinance Tool
### Author: Luke Schwenke

A multi-agent Python application that helps users evaluate whether refinancing a mortgage is financially beneficial. The system combines a FastAPI backend with a Streamlit UI and orchestrates multiple agents with LangGraph to retrieve live market context, calculate refinance break-even, and generate a natural-language recommendation. The LLM is OpenAI (model selected via the `OPENAI_MODEL_NAME` env var, e.g. *GPT-5* — not hardcoded).

**Try it out!:** https://refi-agentic-ai.lukeschwenke.com/

**API Docs (Swagger):** http://refi-agentic-ai.lukeschwenke.com:8000/docs

---

## Tech Stack

**Application**
- Python
- LangGraph (multi-agent orchestration)
- FastAPI + Uvicorn (REST API, OpenAPI/Swagger)
- Streamlit (interactive multi-page web UI)
- OpenAI (LLM, via LangChain)
- Tavily (live web search for current mortgage rates)

**Infrastructure & DevOps**
- Docker (containerized builds and runtime)
- Docker Compose (local orchestration)
- Poetry (dependency management)
- AWS EC2 (hosting)
- Amazon ECR (container registry)
- Elastic IP (static endpoint)
- Route 53 (custom domain + DNS)
- **Caddy** (reverse proxy + automatic HTTPS)
- **Let's Encrypt** (auto-issued/renewed TLS certificate)
- **Amazon DynamoDB** (request logging + rate-limit counters)
- **AWS Lambda + EventBridge + SNS** (scheduled daily email recommendation)

---

## High-Level Architecture

![AWS Architecture](src/frontend/images/arch_diagram_v3.png)

1. Users hit the custom domain over **HTTPS**; Route 53 resolves it to the EC2 Elastic IP.
2. A **Caddy** container terminates TLS (ports 80/443) and reverse-proxies to the Streamlit UI container over a private Docker network. HTTP is redirected to HTTPS, and the cert is auto-provisioned/renewed from Let's Encrypt.
3. Users enter mortgage details in the **Streamlit UI**, which calls the **FastAPI** backend (`POST /refinance_agent/recommendation`) on the internal Docker network, forwarding the visitor's IP for rate limiting.
4. FastAPI enforces the daily demo limits, then executes a **LangGraph** multi-agent workflow.
5. Agents retrieve live market data, perform break-even analysis, and return a recommendation.
6. Each request is logged to **DynamoDB**, and a daily **Lambda** (triggered by EventBridge) posts a fixed scenario to the API and publishes the result to an **SNS** email topic.

All three containers (Caddy, Streamlit UI, FastAPI backend) run on a single EC2 instance, connected via a shared Docker network (`refi_network`). The app image is built and pushed to **ECR**, then pulled on EC2 during deploy.

---

## HTTPS with Caddy

Instead of an ALB + ACM certificate (overkill for a single-instance personal project), TLS is handled by a lightweight **Caddy** reverse proxy running as a container on the EC2 host:

- Listens on ports **80 and 443**, redirecting HTTP → HTTPS.
- Automatically obtains and renews a free **Let's Encrypt** certificate for the domain (ACME HTTP-01 challenge).
- Reverse-proxies to the Streamlit UI container (`:3000`), which is **not** exposed on the host — all public traffic flows through Caddy.
- Certificates persist across redeploys in a Docker volume (`caddy_data`), avoiding Let's Encrypt rate limits.

This implements the standard "TLS-terminating reverse proxy in front of the app" pattern with near-zero certificate management.

> **Security group requirements:** inbound TCP **80** and **443** must be open. Port 80 is required for the ACME challenge and the HTTP→HTTPS redirect. The Route 53 record should point at a **stable Elastic IP** so cert renewal survives instance restarts.

---

## Rate Limiting

To bound worst-case OpenAI/Tavily spend on a publicly shared demo link, the FastAPI endpoint enforces two daily limits (resetting at midnight US/Eastern), backed by atomic counters in the existing DynamoDB table:

- **Per-IP limit:** 5 recommendations per visitor IP per day.
- **Global cap:** 25 recommendations per day across all visitors.

Behavior:
- Limits apply **only to UI traffic** (requests that carry a `client_ip`). The scheduled Lambda posts without one, so it can never be locked out.
- The per-IP limit is checked **first**, so a single blocked IP can't exhaust the global budget for everyone else.
- Exceeding either limit returns **HTTP 429** with a friendly message.
- If DynamoDB is unreachable, the limiter **fails open** rather than blocking visitors.

Counters are stored under keys like `ratelimit#<ip>#<date>` and `ratelimit#global#<date>` in the same `LOG_TABLE`, so no extra table is needed.

---

## Agents

Agent implementations live in `src/core/agents.py`. The workflow is a LangGraph `StateGraph` with a **conditional short-circuit**: if the fetched market rate is *higher* than the user's current rate, refinancing makes no sense, so the treasury and calculator steps are skipped and the workflow jumps straight to the finalizer.

```
market ──> condition ──> if market_rate > interest_rate: finalizer (END)
                         else:                            treasury_yield -> calculator -> finalizer
```

### 1. Market Rate Agent
- Uses Tavily search to retrieve the current average 30-year mortgage rate.
- Gathers both a **national** rate and a **DC-area local credit union** rate; the lower available rate drives the analysis.
- A second LLM call extracts the bare numeric value for downstream use.

### 2. Treasury / Benchmark Agent
- Fetches the U.S. **10-year Treasury yield** as macro-rate context.

### 3. Calculator Agent
- Computes the refinance **break-even** from user inputs (interest rate, payment, balance) and cost assumptions.

### 4. Finalizer Agent
- Loads its prompt from `src/prompts/finalizer_prompt.txt` and synthesizes the final, user-facing recommendation, including which rate source drove the math.

---

## API

**Base URL**
- `http://<host>:8000`

**Swagger / OpenAPI**
- `http://<host>:8000/docs`

**Recommendation Endpoint**
- `POST /refinance_agent/recommendation`

Example request:
```json
{
  "interest_rate": 6.5,
  "current_payment": 5243.26,
  "mortgage_balance": 768000,
  "client_ip": "203.0.113.42"
}
```

`client_ip` is optional — the Streamlit UI sends the visitor's IP (from the `X-Forwarded-For` header set by Caddy) so the API can enforce per-IP limits. Requests without it (e.g. the scheduled Lambda) skip rate limiting.

Example response:
```json
{
  "recommendation": "Refinancing now would lower your payment by ...",
  "market_rate": 5.875,
  "treasury_yield": 4.21,
  "num_tool_calls": 3,
  "path": ["market", "treasury_yield", "calculator", "finalizer"],
  "new_payment": 4892.10,
  "monthly_savings": 351.16,
  "break_even": 14.2
}
```

---

## UI

The Streamlit app is multi-page (sidebar navigation):

- **RefiAI Main Page** — enter mortgage details and get a recommendation.
- **Agent Workflow Details** — visualizes the LangGraph workflow and describes each agent.
- **Architecture Diagram** — the AWS infrastructure diagram.
- **Project Inspiration** — background and the daily-email feature.

Shared theming (the dark-emerald look, decorative palm trees, and the legal footer) lives in `src/frontend/ui.py` and is applied on every page.

---

## Environment

A `.env` file (gitignored) is required and read by both the app and Docker. Keys used in code:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI authentication |
| `OPENAI_MODEL_NAME` | Which OpenAI model to use (not hardcoded) |
| `TAVILY_API_KEY` | Tavily web search |
| `LOG_TABLE` | DynamoDB table for request logs + rate-limit counters |
| `AWS_REGION` | AWS region (default `us-east-1`) |
| `LOCAL_CREDIT_UNION_RATES_URL` | DC-area credit union "featured rates" endpoint (degrades to unavailable if unset) |
| `API_BASE_URL` / `API_PORT` / `API_PATH` | Client-side API URL construction |

---

## Local Development

Dependencies are managed with Poetry. Common `make` targets:

```bash
make build      # build the API Docker image (linux/amd64)
make run        # run the API container, reading .env, on port 8000
make ui         # run the Streamlit UI locally
make go         # build + run + ui
make rebuild    # stop + build + run + ui
make stop       # stop & remove the container
```

Run the API directly without Docker:
```bash
poetry run uvicorn api.api_setup:app --host 127.0.0.1 --port 8000 --reload
```

Run tests (some hit live endpoints and need network access + `TAVILY_API_KEY`):
```bash
poetry run pytest
poetry run pytest tests/test_tools.py -m treasury -s
```

---

## Deployment

The app is deployed to EC2 via ECR:

```bash
make push-ecr            # build & push the image to ECR
make full-deploy-prod    # push to ECR, then pull & restart containers on EC2
```

`full-deploy-prod` connects to the EC2 instance, pulls the latest image, and (re)starts the FastAPI backend, Streamlit UI, and Caddy proxy containers on the shared Docker network. Regenerate the architecture diagram with `python docs/generate_arch_diagram.py` (requires the `diagrams` package and Graphviz).

---

> **Disclaimer:** RefiAI is a personal demo project for educational purposes. It does not provide financial, legal, or tax advice, and nothing in it is a loan offer or commitment to lend.
