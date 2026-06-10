# Agentic Refinance Tool
### Author: Luke Schwenke

A multi-agent Python application that helps users evaluate whether refinancing a mortgage is financially beneficial. The system combines a FastAPI backend with a Streamlit UI and orchestrates multiple agents with LangGraph to retrieve market context, calculate refinance break-even, and generate a final recommendation. LLM being leveraged: *OpenAI GPT-5*

**Try it out!:** https://refi-agentic-ai.lukeschwenke.com/

**API Docs (Swagger):** http://refi-agentic-ai.lukeschwenke.com:8000/docs

---

## Tech Stack

**Application**
- Python
- LangGraph (multi-agent orchestration)
- FastAPI + Uvicorn (REST API, OpenAPI/Swagger)
- Streamlit (interactive web UI)

**Infrastructure & DevOps**
- Docker (containerized builds and runtime)
- Docker Compose (local orchestration)
- Poetry (dependency management)
- AWS EC2 (hosting)
- Amazon ECR (container registry)
- Elastic IP (static endpoint)
- Route 53 (custom domain + DNS)

---

## High-Level Architecture

1. Users enter mortgage details in the Streamlit UI
2. The UI calls a FastAPI endpoint to request a recommendation
3. FastAPI executes a LangGraph-powered multi-agent workflow
4. Agents retrieve market data, perform financial analysis, and return a recommendation to the UI

---

## Agents

Agent implementations live in `src/core/agents.py`.

The system uses **three cooperating agents**, coordinated via a LangGraph workflow:

### 1. Market Rate Agent
- Retrieves current mortgage and market interest-rate data from external APIs
- Normalizes and validates rate inputs for downstream analysis

### 2. Treasury / Benchmark Agent
- Fetches benchmark indicators such as the U.S. 10-year Treasury yield
- Provides macro-rate context used in recommendation logic and explanation

### 3. Refinance Analysis & Recommendation Agent
- Computes refinance break-even based on user inputs (interest rate, payment, balance) and cost assumptions
- Synthesizes results into a final, user-facing recommendation payload

---

## API

**Base URL**
- `http://<host>:8000`

**Swagger / OpenAPI**
- `http://<host>:8000/docs`

**Recommendation Endpoint**
- `POST /refinance_agent/recommendation/`

Example request:
```json
{
  "interest_rate": 6.5,
  "current_payment": 5243.26,
  "mortgage_balance": 768000
}