# RefiAI Finalization Plan

**Date:** 2026-06-12
**Goal:** Finalize RefiAI as a clean, easy-to-use, extremely reliable refinance advisor — leaning on current best practices in AI agents (deterministic math, structured outputs, narrow LLM responsibilities, graceful degradation) without adding complexity for its own sake.

**Guiding principles**
1. **LLMs decide and explain; Python computes.** Every number must come from deterministic code. (Already true for the calculator/strategy/treasury — finish the job for the market agent.)
2. **Every external call can fail; the user should never see a wrong answer because of it.** Degrade to "unavailable," never to a fabricated number.
3. **The UI should read like a fintech product, not like an AI demo.** Plain language, visible assumptions, restrained decoration.

---

## P0 — Reliability bugs (fix before anything else)

### P0.1 The "no market rate" path produces a bogus recommendation
If **both** rate sources fail, `consolidate_rates` returns `0.0` and `condition()` in `src/core/workflow.py` evaluates `0.0 > interest_rate` → **False → CONTINUE**. The workflow then builds scenarios at a 0% market rate (`monthly_payment` degenerates to `balance/360`), producing huge fake "savings," and the finalizer's decision rule (`interest_rate > market_rate`) calls it a refinancing opportunity.

**Fix:** add a third branch to `condition()`: if `market_rate <= 0` → route straight to `finalizer` (reuse the END path) and have the finalizer state that live rates couldn't be retrieved and no analysis was performed. Add an offline test that runs the graph with both sources stubbed to fail and asserts no scenarios are produced.

### P0.2 Retries on the three live fetches
`get_treasury_10yr_quote`, `get_local_credit_union_30yr_rate`, and the two Tavily searches are single-shot. One transient network blip silently degrades the answer.

**Fix:** small shared helper (e.g. `_get_with_retry`) — 2 retries, short backoff, keep the existing 8s timeouts. No new dependency needed (a 6-line loop), or use `tenacity` if preferred.

### P0.3 Cache market data briefly
Every demo request re-fetches Tavily + CU + CNBC + outlook (~4 network calls, 2 paid Tavily searches). Rates don't move minute-to-minute.

**Fix:** in-process TTL cache (15 min) around the four fetchers in `src/core/tools.py`. Cuts latency, cost, and rate-source flakiness for repeat visitors; the daily Lambda is unaffected.

---

## P1 — Code cleanup & tightening

### P1.1 Remove dead code
- `src/core/agents.py`: the ~40-line commented-out old finalizer template (lines ~284–321).
- `src/core/workflow.py`: unused `IPython.display` / `PIL` / `BytesIO` imports and the commented-out graph-drawing block.
- `src/core/define_state_and_llm.py`: unused `ChatOllama` import (keep the commented Ollama block only if local-LLM support is still wanted; otherwise delete both).

### P1.2 Prune the tool registry to match reality
After the scenario refactor, **only `get_rates_search_tool_for_agent` is actually invoked through the LLM tool loop.** The other four `_for_agent` registrations in `ToolNode` (agents.py:8–12) and `bind_tools` (define_state_and_llm.py:62–66) are dead weight that (a) confuses readers and (b) puts unused tool schemas in every LLM call's context.

**Fix:** register only the tools an LLM can actually call. Keep the plain/`_for_agent` dual pattern documented in CLAUDE.md for the one that remains. (Alternative considered: make the market agent deterministic too — see P1.5 — after which `ToolNode`/`bind_tools` can be deleted entirely. Recommended.)

### P1.3 Fix `num_tool_calls` semantics
It now counts "agent steps," not tool calls (treasury/calculator/strategy increment it without calling tools). Either rename the concept to `steps` end-to-end, or count actual external calls. The UI label ("Agentic tool calls") should match whatever it truly is — see P3.4.

### P1.4 Brand & docs staleness
- `src/schedule/lambda_function.py:44`: email subject still says "Refi with Agentic AI" → "RefiAI Daily Recommendation".
- `README.md`: still documents the old 4-agent workflow and old DAG (`treasury_yield -> calculator -> finalizer`); update to the 6-node graph, the dual-source market rate, the timing signals, and the scenario/strategy model.
- `CLAUDE.md`: says "four nodes"; the agent pattern description ("manually invoke llm_with_tools…") no longer matches most agents. Update both.
- `src/frontend/pages/1_Agent_Workflow_Details.py:87–88`: source links point to `github.com/lukeschwenke/Agentic-AI` — verify that's still the published repo; fix if renamed.

### P1.5 Make the market expert deterministic (biggest prompt-layer win)
`_get_national_rate_via_tavily` currently burns **three** LLM round-trips for one number: (1) an LLM call whose only job is to decide to call the tool we always want called, (2) the Tavily search, (3) a second LLM call to extract the number — with a brittle bare `float(resp.content)` parse. The prompt itself is vague ("summarize some recent articles…").

**Fix:** call `get_rates_search_tool()` directly (Tavily's `include_answer` already returns the answer string; the query already demands a bare number), then extract with a regex (`\d+\.\d+`) and a range sanity check (3–12%); fall back to one structured-output LLM extraction only if regex fails. Result: faster, cheaper, and two fewer failure modes. This also lets P1.2 delete `ToolNode`/`bind_tools` completely.

---

## P2 — Agent / prompt quality (clarity + maximizing the LLM)

| Agent | Assessment | Action |
|---|---|---|
| Market expert | 3 LLM hops for 1 number; vague prompt | Replace with deterministic fetch (P1.5) |
| Treasury | No LLM — pure Python | None (this is the model to follow) |
| Rate outlook | Good prompt; hand-rolled JSON parsing via `_extract_json` | Use `llm.with_structured_output(<Pydantic model>)` with `Literal` enums for `label`/`action` — guaranteed-valid output, deletes the regex fence-stripping |
| Strategy | Good guidance; one gap | Same structured-output treatment; **add a rule for the all-negative case**: "If no scenario has positive monthly savings AND none breaks even within the horizon, recommend NOT refinancing rather than picking the least-bad structure." Today it always picks one |
| Finalizer | Solid structure; two issues | (a) **Pre-format every number in Python** before injecting (e.g. `lifetime_interest_delta` → `−$81,933` / `+$54,593`): the live run rendered the awkward "saves $-81,933.26" because the LLM was handed a raw float. Format money, percents, and months in `finalizer_agent` so the LLM only narrates. (b) Inject booleans as words ("yes"/"no"/"not evaluated") instead of Python `True/False/None` |

**Cross-cutting:** all three remaining LLM calls (outlook, strategy, finalizer) should use structured output or tightly pre-formatted inputs. Temperature is already pinned at 0.1 — good.

---

## P3 — UI clarity (without the "an AI made this" smell)

The current telltales of LLM-styled UI: decorative emoji in functional UI (🌐 📊 ⚡ pills, 📈 outlook chip, ⭐ table marker), exclamation-y microcopy, and em-dash-heavy copy. Restraint reads as professionally designed.

1. **Emoji audit.** Drop emojis from the hero pills (plain text chips), the outlook caption, and replace the table's "⭐ " with a real "Recommended" tag in the Structure cell (e.g. "Keep your current payoff date · Recommended") or a separate boolean column rendered as a badge.
2. **Show the assumptions.** When defaults were used, users don't know it. Add one quiet caption under the metric row: *"Assumes ~$9,600 closing costs (2% of balance), 22 years left (estimated from your payment), and a 7-year stay — open Advanced details to change these."* The API already returns everything needed except the resolved defaults — add `remaining_term_years`, `stay_horizon_years`, `closing_costs` (resolved values) to `RefiAdviceResponse` so the UI can display what was actually used. **This is the single highest-trust UI change.**
3. **Humanize "Agent run details".** Map node names to plain labels ("Market rates → Treasury context → Rate outlook → Scenario math → Strategy → Final write-up") instead of `market_expert_agent → …`, and retitle "Agentic tool calls" per P1.3 (or drop the metric — it's developer telemetry, not user value).
4. **Input guardrails.** Soft validation with friendly messages: rate outside 1–15% ("double-check your rate — it's usually between 2% and 10%"), payment that can't amortize the balance (we can detect this — `estimate_remaining_term_years` returns `None`), balance < $10k. Warn, don't block.
5. **Metric labels.** "Break-even (mo)" → "Break-even" with the value rendered as "28 months"; "New payment (est.)" is fine.
6. **Progress feedback.** The 30–60s spinner is a black box. Cheapest fix: rotate the spinner text through the actual stages. Proper fix is streaming (P4.4).

---

## P4 — New capabilities (tiered; all optional for "finalized")

1. **FRED `MORTGAGE30US` as the national-rate source/fallback** *(recommended — biggest reliability win per effort)*. Freddie Mac's weekly 30-yr average via the free FRED API: deterministic JSON, no scraping, no LLM, no Tavily cost. Use Tavily as fallback (or drop it for the national number entirely and keep Tavily only for the outlook search). New env var `FRED_API_KEY`, degrade gracefully if unset.
2. **Verifier node (LLM-as-judge), cheap model.** After the finalizer, a small model checks the draft against the state values ("does every number in the text match the state? does the verdict match the decision rule?") and triggers one regeneration on mismatch. Catches the only remaining hallucination surface. Adds ~1–2s.
3. **Parallel fan-out for latency.** `treasury_yield` and `rate_outlook` are independent — run them as parallel branches after `market`. Requires `Annotated` reducers (`operator.add`) on the shared `path`/`num_tool_calls` keys. Do after P1.3 renames settle.
4. **Stream the finalizer to the UI.** FastAPI `StreamingResponse` + `st.write_stream` — the verdict starts appearing in ~5s instead of after the full run. Largest perceived-speed win; medium effort (touches API contract, client, UI).
5. **(Deferred, unchanged)** PMI-removal analysis and personalized-rate estimation — both need home-value/credit inputs; revisit only if the input form is allowed to grow.

---

## P5 — Testing & operability

1. **Offline workflow tests** (`tests/test_workflow.py`): run the compiled graph with all fetchers/LLMs monkeypatched — assert the three paths (CONTINUE, short-circuit END, and the new P0.1 unavailable path), scenario math wiring, and that primary metrics mirror the recommended scenario.
2. **Finalizer eval set.** 4–6 recorded state fixtures (strong-refi, marginal, don't-refi, rates-unavailable, term-reset-trap, sell-before-breakeven) + assertions on must-contain/must-not-contain strings (e.g. must not say "0%", must state the recommended structure verbatim). Run with `pytest -m finalizer_eval` (live LLM, opt-in) — this is the lightweight version of modern prompt-eval practice and will catch prompt regressions when you edit `finalizer_prompt.txt`.
3. **Observability.** Log per-node duration + outcome labels (market_rate_source, outlook label, recommended structure) to the existing DynamoDB record; optional `LANGSMITH_TRACING` env flag for tracing.
4. **`tests/test_api_server.py`** is an interactive script, not a test — move to `scripts/` or convert to a real test against a TestClient.

---

## Suggested execution order

| Milestone | Contents | Outcome |
|---|---|---|
| 1. "Never wrong" | P0.1–P0.3, P1.5 | No fabricated answers, resilient fetches, fewer LLM hops |
| 2. "Clean core" | P1.1–P1.4, P2 table items | Dead code gone, prompts tight, numbers pre-formatted |
| 3. "Trustworthy UI" | P3.1–P3.6 | Assumptions visible, plain-language polish, no AI-smell |
| 4. "Tested" | P5.1, P5.2, P5.4 | Regression-proof workflow + prompts |
| 5. "Best-in-class" (optional) | P4.1–P4.4, P5.3 | FRED source, verifier, parallelism, streaming |

Milestones 1–4 are the "finalized" bar. Milestone 5 is where the app would go from solid to genuinely impressive; FRED (P4.1) is the one I'd pull forward if you only pick one.

---

## Explicitly out of scope
- Auth/accounts, payment, multi-loan portfolios.
- Replacing Streamlit (it's serving the product fine).
- Switching LLM providers or adding local-model support beyond the existing commented Ollama stub.
