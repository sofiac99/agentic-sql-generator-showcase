from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from .database import SCHEMA, create_demo_database, run_query, validate_readonly_sql
from .models import AgentState, InsightResponse
from .retrieval import SemanticRetriever
from .analytics_pipeline import BehaviorAnalyticsPipeline
from .sql_generation import QueryPlan, SQLQueryGenerator


class MerchantAnalyticsAgent:
    def __init__(self, db_path: str | Path = "data/merchant_analytics.db"):
        self.db_path = create_demo_database(db_path)
        self.retriever = SemanticRetriever()
        self.llm = None
        if os.getenv("OPENAI_API_KEY"):
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), temperature=0)
        self.behavior_pipeline = BehaviorAnalyticsPipeline(self.db_path, self.llm)
        self.sql_generator = SQLQueryGenerator(self.db_path, self.llm)
        self.graph = self._build_graph()

    @property
    def mode(self) -> str:
        return "OpenAI" if self.llm else "Demo"

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("link_schema", self._link_schema)
        workflow.add_node("plan_query", self._plan_query)
        workflow.add_node("generate_sql", self._generate_sql)
        workflow.add_node("validate_sql", self._validate_sql)
        workflow.add_node("execute_sql", self._execute_sql)
        workflow.add_node("synthesize_insight", self._synthesize_insight)
        workflow.add_edge(START, "retrieve_context")
        workflow.add_edge("retrieve_context", "link_schema")
        workflow.add_edge("link_schema", "plan_query")
        workflow.add_edge("plan_query", "generate_sql")
        workflow.add_edge("generate_sql", "validate_sql")
        workflow.add_conditional_edges("validate_sql", self._after_validation, {"execute": "execute_sql", "repair": "generate_sql", "stop": "synthesize_insight"})
        workflow.add_conditional_edges("execute_sql", self._after_execution, {"repair": "generate_sql", "finish": "synthesize_insight"})
        workflow.add_edge("synthesize_insight", END)
        return workflow.compile()

    @staticmethod
    def _trace(state: AgentState, item: str) -> list[str]:
        return [*state.get("trace", []), item]

    def _retrieve_context(self, state: AgentState) -> dict[str, Any]:
        contexts = self.retriever.search(state["question"], k=3)
        return {"contexts": contexts, "trace": self._trace(state, f"Retrieved {len(contexts)} business context items")}

    def _link_schema(self, state: AgentState) -> dict[str, Any]:
        catalog = self.sql_generator.catalog
        return {"schema": catalog.prompt_text(), "trace": self._trace(state, f"Introspected {len(catalog.tables)} tables and {len(catalog.columns)} columns")}

    def _plan_query(self, state: AgentState) -> dict[str, Any]:
        plan = self.sql_generator.plan(state["question"], state["contexts"])
        return {
            "intent": plan.intent,
            "query_plan": plan.model_dump(),
            "trace": self._trace(state, f"Planned {plan.intent} query on: {', '.join(plan.tables)}"),
        }

    def _generate_sql(self, state: AgentState) -> dict[str, Any]:
        attempts = state.get("attempts", 0) + 1
        plan = QueryPlan.model_validate(state["query_plan"])
        draft = self.sql_generator.generate(state["question"], plan, state["contexts"], state.get("sql_error", ""))
        return {"sql": draft.sql, "sql_rationale": draft.rationale, "attempts": attempts, "sql_error": "", "trace": self._trace(state, f"Generated schema-grounded SQL (attempt {attempts})")}

    @staticmethod
    def _demo_sql(question: str, intent: str) -> str:
        q = question.lower()
        if intent == "merchant_prioritization":
            return """WITH recent AS (
 SELECT merchant_id, SUM(gmv) gmv, 100.0*SUM(successful_payments)/NULLIF(SUM(payment_attempts),0) payment_success_rate,
 100.0*SUM(chargebacks)/NULLIF(SUM(gmv),0) chargeback_rate
 FROM monthly_performance WHERE month >= '2026-01-01' GROUP BY merchant_id)
SELECT m.merchant_name, m.segment, m.region, m.account_owner, m.risk_tier,
 ROUND(r.gmv,0) gmv, ROUND(r.payment_success_rate,2) payment_success_rate,
 ROUND(r.chargeback_rate,2) chargeback_rate
FROM recent r JOIN merchants m USING(merchant_id)
ORDER BY CASE m.risk_tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, r.gmv DESC LIMIT 12"""
        if "channel" in q:
            return """SELECT m.acquisition_channel, ROUND(SUM(p.gmv),0) gmv,
 ROUND(100.0*SUM(p.successful_payments)/NULLIF(SUM(p.payment_attempts),0),2) payment_success_rate,
 COUNT(DISTINCT p.merchant_id) merchants
FROM monthly_performance p JOIN merchants m USING(merchant_id)
WHERE p.month >= '2026-01-01' GROUP BY m.acquisition_channel ORDER BY gmv DESC"""
        if "segment" in q or "fastest" in q:
            return """SELECT m.segment, ROUND(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END),0) current_gmv,
 ROUND(SUM(CASE WHEN p.month BETWEEN '2026-01-01' AND '2026-03-01' THEN p.gmv ELSE 0 END),0) prior_gmv,
 ROUND(100.0*(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END)/NULLIF(SUM(CASE WHEN p.month BETWEEN '2026-01-01' AND '2026-03-01' THEN p.gmv ELSE 0 END),0)-1),1) growth_pct,
 ROUND(100.0*SUM(CASE WHEN p.month >= '2026-04-01' THEN p.chargebacks ELSE 0 END)/NULLIF(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END),0),2) chargeback_rate
FROM monthly_performance p JOIN merchants m USING(merchant_id) GROUP BY m.segment ORDER BY growth_pct DESC"""
        return """SELECT month, ROUND(SUM(gmv),0) gmv, SUM(orders) orders,
 ROUND(100.0*SUM(successful_payments)/NULLIF(SUM(payment_attempts),0),2) payment_success_rate,
 ROUND(100.0*SUM(refunds)/NULLIF(SUM(gmv),0),2) refund_rate
FROM monthly_performance GROUP BY month ORDER BY month"""

    def _validate_sql(self, state: AgentState) -> dict[str, Any]:
        plan = QueryPlan.model_validate(state["query_plan"])
        report = self.sql_generator.validate(state["sql"], plan)
        if report.valid:
            return {
                "sql": report.normalized_sql,
                "sql_error": "",
                "validation_checks": report.checks,
                "explain_plan": report.explain_plan,
                "trace": self._trace(state, f"SQL passed {len(report.checks)} checks and EXPLAIN preflight"),
            }
        return {"sql_error": report.error, "validation_checks": report.checks, "trace": self._trace(state, f"SQL validation rejected query: {report.error}")}

    @staticmethod
    def _after_validation(state: AgentState) -> str:
        if not state.get("sql_error"):
            return "execute"
        return "repair" if state.get("attempts", 0) < 3 else "stop"

    def _execute_sql(self, state: AgentState) -> dict[str, Any]:
        try:
            columns, rows = run_query(self.db_path, state["sql"])
            return {"columns": columns, "rows": rows, "sql_error": "", "trace": self._trace(state, f"Executed safely: {len(rows)} rows")}
        except Exception as exc:
            return {"sql_error": str(exc), "trace": self._trace(state, f"Execution error: {exc}")}

    @staticmethod
    def _after_execution(state: AgentState) -> str:
        return "repair" if state.get("sql_error") and state.get("attempts", 0) < 3 else "finish"

    def _synthesize_insight(self, state: AgentState) -> dict[str, Any]:
        if state.get("sql_error"):
            insight = InsightResponse(headline="The analysis could not be completed safely", executive_summary=state["sql_error"], confidence=0.2, caveats=["No database result was used."])
        elif self.llm:
            structured_llm = self.llm.with_structured_output(InsightResponse)
            prompt = f"""Create a concise, decision-ready merchant analysis.
Question: {state['question']}
SQL result: {json.dumps(state.get('rows', [])[:50], default=str)}
Columns: {state.get('columns', [])}
Retrieved context: {json.dumps(state.get('contexts', []))}
Choose a chart with valid result column names. Include 2-4 KPIs and 2-4 actions. Do not invent facts."""
            insight = structured_llm.invoke(prompt)
        else:
            insight = self._demo_insight(state)
        return {"insight": insight.model_dump(), "trace": self._trace(state, "Produced typed dashboard insight")}

    @staticmethod
    def _demo_insight(state: AgentState) -> InsightResponse:
        rows = state.get("rows", [])
        columns = state.get("columns", [])
        if not rows:
            return InsightResponse(headline="No matching merchant data", executive_summary="Try broadening the time window or removing a filter.", confidence=.6)
        numeric = [c for c in columns if isinstance(rows[0].get(c), (int, float))]
        category = next((c for c in columns if c not in numeric), columns[0])
        y = numeric[:2] or [columns[-1]]
        lead = rows[0]
        label = str(lead.get(category, "Top result"))
        main_metric = y[0]
        main_value = lead.get(main_metric)
        formatted = f"${main_value:,.0f}" if "gmv" in main_metric and isinstance(main_value, (int, float)) else f"{main_value:,.1f}" if isinstance(main_value, float) else str(main_value)
        chart_type = "line" if category == "month" else "bar"
        return InsightResponse(
            headline=f"{label} leads the current analysis",
            executive_summary=f"The result set contains {len(rows)} decision-relevant observations. {label} ranks first on {main_metric.replace('_', ' ')} at {formatted}.",
            kpis=[{"label": main_metric.replace("_", " ").title(), "value": formatted, "direction": "up"}, {"label": "Rows analyzed", "value": str(len(rows)), "direction": "neutral"}],
            findings=[f"{label} is the leading result by {main_metric.replace('_', ' ')}.", "Review the full result table before taking account-level action."],
            actions=[{"priority": "high", "title": "Review the leading cohort", "rationale": "Validate the primary driver and assign a clear owner."}, {"priority": "medium", "title": "Monitor next-month movement", "rationale": "Confirm whether this is a sustained pattern or normal volatility."}],
            chart={"chart_type": chart_type, "title": f"{main_metric.replace('_', ' ').title()} by {category.replace('_', ' ')}", "x": category, "y": y},
            confidence=.82,
            caveats=["Demo mode uses deterministic analysis; add an API key for contextual narrative synthesis."],
        )

    def analyze(self, question: str) -> dict[str, Any]:
        return self.graph.invoke({"question": question, "trace": [], "attempts": 0})

    def dashboard_snapshot(self) -> dict[str, Any]:
        """Run the governed behavior analytics pipeline for the admin overview."""
        return self.behavior_pipeline.run()
