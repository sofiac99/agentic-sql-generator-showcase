# Agentic SQL Generator

A production-oriented, plan-first **NL-to-SQL agent** built with RAG and LangGraph, demonstrated through a merchant analytics dashboard. It combines live schema introspection, typed query planning, read-only SQL validation, automatic repair, semantic retrieval, and dashboard-ready structured insights.

This public showcase uses entirely synthetic merchant and behavioral data. No customer data, credentials, or proprietary schemas are included.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB) ![LangGraph](https://img.shields.io/badge/LangGraph-agentic%20workflow-1C3C3C) ![Tests](https://img.shields.io/badge/tests-8%20passing-2E8B57)

## What it does

- Answers natural-language merchant questions with validated SQLite queries
- Aggregates view, click, wishlist, and booking facts into a governed metrics layer
- Calculates engagement, CTR, wishlist rate, conversion trend, funnel, and top categories
- Retrieves relevant business definitions, playbooks, and prior analysis examples
- Produces structured KPIs, chart specifications, findings, and recommended actions
- Uses plan-first SQL generation with live schema introspection and structured query contracts
- Preflights every query with AST policy, schema grounding, and `EXPLAIN QUERY PLAN`
- Shows evidence: generated SQL, retrieved context, confidence, and graph execution trace
- Runs in deterministic demo mode without an API key; uses OpenAI models when configured

## Architecture

```text
Behavior facts -> SQL metrics layer -> Structured LLM summary -> Executive dashboard
                                                                |
Question -> Intent + RAG -> Schema linking -> Safe SQL -> Drill-down insight
```

The graph is intentionally constrained: the model never connects directly to the database, only a validated single-statement `SELECT`/`WITH` query can execute, and result sizes are capped.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

The sample database is generated automatically on first run. Add `OPENAI_API_KEY` to `.env` for LLM SQL generation, semantic embeddings, and narrative synthesis.

## Test and evaluate

```bash
pytest -q
PYTHONPATH=. python scripts/evaluate_sql_agent.py
```

## Suggested questions

- Which merchant segment is growing fastest and where is risk increasing?
- Compare payment success rate by channel this quarter.
- Which merchants should the account team prioritize this week?
- Show monthly GMV and flag material changes.

## Project layout

```text
app.py                       Streamlit dashboard
merchant_agent/database.py   Seed data and safe SQL execution
merchant_agent/retrieval.py  Vector embeddings + semantic retrieval
merchant_agent/models.py     Typed state and structured outputs
merchant_agent/graph.py      LangGraph analytics workflow
merchant_agent/sql_generation.py Plan-first NL-to-SQL and validation
evals/                       NL-to-SQL evaluation cases
scripts/evaluate_sql_agent.py Evaluation runner
docs/ARCHITECTURE.md         Detailed system design
tests/                       Guardrail and end-to-end tests
```

## Production adaptation

Replace SQLite with a read-only warehouse role, persist embeddings in pgvector/Pinecone, add tenant filters before SQL execution, and send graph traces to LangSmith or your observability stack. Keep approval gates for high-impact recommendations.
