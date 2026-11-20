from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

from .database import validate_readonly_sql


class QueryPlan(BaseModel):
    """A model-independent semantic contract created before SQL generation."""

    intent: Literal["aggregate", "comparison", "trend", "ranking", "lookup"]
    tables: list[str]
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    time_grain: Literal["none", "day", "week", "month", "quarter", "year"] = "none"
    sort: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=200)
    assumptions: list[str] = Field(default_factory=list)


class QueryDraft(BaseModel):
    sql: str
    rationale: str


class ValidationReport(BaseModel):
    valid: bool
    normalized_sql: str = ""
    checks: list[str] = Field(default_factory=list)
    error: str = ""
    explain_plan: list[str] = Field(default_factory=list)


@dataclass
class SchemaCatalog:
    tables: dict[str, list[dict[str, str]]]
    foreign_keys: list[dict[str, str]]

    @classmethod
    def from_sqlite(cls, db_path: str | Path) -> "SchemaCatalog":
        uri = f"file:{Path(db_path).resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            table_names = [
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            tables: dict[str, list[dict[str, str]]] = {}
            foreign_keys: list[dict[str, str]] = []
            for table in table_names:
                safe_table = table.replace('"', '""')
                tables[table] = [
                    {"name": row["name"], "type": row["type"], "nullable": str(not row["notnull"])}
                    for row in conn.execute(f'PRAGMA table_info("{safe_table}")')
                ]
                foreign_keys.extend(
                    {"from_table": table, "from_column": row["from"], "to_table": row["table"], "to_column": row["to"]}
                    for row in conn.execute(f'PRAGMA foreign_key_list("{safe_table}")')
                )
            return cls(tables=tables, foreign_keys=foreign_keys)
        finally:
            conn.close()

    def prompt_text(self, selected_tables: list[str] | None = None) -> str:
        selected = selected_tables or list(self.tables)
        lines = []
        for table in selected:
            if table not in self.tables:
                continue
            cols = ", ".join(f"{c['name']} {c['type']}" for c in self.tables[table])
            lines.append(f"{table}({cols})")
        for fk in self.foreign_keys:
            if fk["from_table"] in selected and fk["to_table"] in selected:
                lines.append(f"FK {fk['from_table']}.{fk['from_column']} -> {fk['to_table']}.{fk['to_column']}")
        return "\n".join(lines)

    @property
    def columns(self) -> set[str]:
        return {column["name"] for columns in self.tables.values() for column in columns}


class SQLQueryGenerator:
    """Plan-first, schema-grounded SQL generation with compile-time validation."""

    def __init__(self, db_path: str | Path, llm: Any = None):
        self.db_path = Path(db_path)
        self.llm = llm
        self.catalog = SchemaCatalog.from_sqlite(db_path)

    def plan(self, question: str, contexts: list[dict[str, Any]]) -> QueryPlan:
        if self.llm:
            planner = self.llm.with_structured_output(QueryPlan)
            return planner.invoke(
                "Create a minimal analytics query plan grounded only in this schema. "
                "Use metric definitions in the retrieved context. Never invent fields.\n"
                f"QUESTION:\n{question}\nSCHEMA:\n{self.catalog.prompt_text()}\n"
                f"CONTEXT:\n{json.dumps(contexts, default=str)}"
            )
        return self._demo_plan(question)

    def _demo_plan(self, question: str) -> QueryPlan:
        q = question.lower()
        if any(term in q for term in ["category", "wishlist", "click", "view", "booking", "conversion", "engagement"]):
            intent = "trend" if any(term in q for term in ["trend", "monthly", "over time"]) else "ranking" if "top" in q else "comparison"
            return QueryPlan(intent=intent, tables=["behavior_daily"], dimensions=["event_date" if intent == "trend" else "category"], metrics=["views", "clicks", "wishlists", "bookings", "conversion_rate"], time_grain="month" if intent == "trend" else "none")
        if "channel" in q:
            return QueryPlan(intent="comparison", tables=["monthly_performance", "merchants"], dimensions=["acquisition_channel"], metrics=["gmv", "payment_success_rate"], filters=["2026 year-to-date"])
        if "segment" in q:
            return QueryPlan(intent="comparison", tables=["monthly_performance", "merchants"], dimensions=["segment"], metrics=["current_gmv", "prior_gmv", "growth_pct", "chargeback_rate"])
        if any(term in q for term in ["merchant", "risk", "prioritize", "owner"]):
            return QueryPlan(intent="ranking", tables=["monthly_performance", "merchants"], dimensions=["merchant_name", "segment", "risk_tier", "account_owner"], metrics=["gmv", "payment_success_rate", "chargeback_rate"], filters=["2026 year-to-date"], sort=["risk_tier", "gmv DESC"], limit=12)
        return QueryPlan(intent="trend", tables=["monthly_performance"], dimensions=["month"], metrics=["gmv", "orders", "payment_success_rate", "refund_rate"], time_grain="month")

    def generate(self, question: str, plan: QueryPlan, contexts: list[dict[str, Any]], previous_error: str = "") -> QueryDraft:
        if not self.llm:
            return QueryDraft(sql=self._demo_sql(plan), rationale="Deterministic query selected from the verified query library.")
        generator = self.llm.with_structured_output(QueryDraft)
        rules = """SQLite rules:
- Return exactly one read-only SELECT/WITH query.
- Use only listed tables and columns; use explicit JOIN conditions.
- Compute ratios after aggregation: SUM(numerator)/NULLIF(SUM(denominator),0).
- Never use SELECT *; alias every computed metric; cap results at the plan limit.
- Use ISO date literals and state any unavoidable assumption in rationale."""
        return generator.invoke(
            f"{rules}\nQUESTION:\n{question}\nQUERY PLAN:\n{plan.model_dump_json()}\n"
            f"RELEVANT SCHEMA:\n{self.catalog.prompt_text(plan.tables)}\n"
            f"RETRIEVED EXAMPLES AND DEFINITIONS:\n{json.dumps(contexts, default=str)}\n"
            f"PREVIOUS VALIDATION ERROR:\n{previous_error or 'none'}"
        )

    @staticmethod
    def _demo_sql(plan: QueryPlan) -> str:
        if plan.tables == ["behavior_daily"]:
            if plan.intent == "trend":
                return """SELECT event_date AS month, SUM(views) AS views, SUM(clicks) AS clicks,
 SUM(wishlists) AS wishlists, SUM(bookings) AS bookings,
 ROUND(100.0*SUM(bookings)/NULLIF(SUM(views),0),2) AS conversion_rate
FROM behavior_daily GROUP BY event_date ORDER BY event_date LIMIT 100"""
            return """SELECT category, SUM(views) AS views, SUM(clicks) AS clicks,
 SUM(wishlists) AS wishlists, SUM(bookings) AS bookings,
 ROUND(100.0*SUM(clicks+wishlists)/NULLIF(SUM(views),0),2) AS engagement_rate,
 ROUND(100.0*SUM(bookings)/NULLIF(SUM(views),0),2) AS conversion_rate
FROM behavior_daily GROUP BY category ORDER BY bookings DESC LIMIT 100"""
        if "merchants" in plan.tables and "merchant_name" in plan.dimensions:
            return """WITH recent AS (
 SELECT merchant_id, SUM(gmv) AS gmv,
 100.0*SUM(successful_payments)/NULLIF(SUM(payment_attempts),0) AS payment_success_rate,
 100.0*SUM(chargebacks)/NULLIF(SUM(gmv),0) AS chargeback_rate
 FROM monthly_performance WHERE month >= '2026-01-01' GROUP BY merchant_id)
SELECT m.merchant_name, m.segment, m.region, m.account_owner, m.risk_tier,
 ROUND(r.gmv,0) AS gmv, ROUND(r.payment_success_rate,2) AS payment_success_rate,
 ROUND(r.chargeback_rate,2) AS chargeback_rate
FROM recent r JOIN merchants m ON r.merchant_id=m.merchant_id
ORDER BY CASE m.risk_tier WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, r.gmv DESC LIMIT 12"""
        if "acquisition_channel" in plan.dimensions:
            return """SELECT m.acquisition_channel, ROUND(SUM(p.gmv),0) AS gmv,
 ROUND(100.0*SUM(p.successful_payments)/NULLIF(SUM(p.payment_attempts),0),2) AS payment_success_rate,
 COUNT(DISTINCT p.merchant_id) AS merchants
FROM monthly_performance p JOIN merchants m ON p.merchant_id=m.merchant_id
WHERE p.month >= '2026-01-01' GROUP BY m.acquisition_channel ORDER BY gmv DESC LIMIT 100"""
        if "segment" in plan.dimensions:
            return """SELECT m.segment,
 ROUND(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END),0) AS current_gmv,
 ROUND(SUM(CASE WHEN p.month BETWEEN '2026-01-01' AND '2026-03-01' THEN p.gmv ELSE 0 END),0) AS prior_gmv,
 ROUND(100.0*(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END)/NULLIF(SUM(CASE WHEN p.month BETWEEN '2026-01-01' AND '2026-03-01' THEN p.gmv ELSE 0 END),0)-1),1) AS growth_pct,
 ROUND(100.0*SUM(CASE WHEN p.month >= '2026-04-01' THEN p.chargebacks ELSE 0 END)/NULLIF(SUM(CASE WHEN p.month >= '2026-04-01' THEN p.gmv ELSE 0 END),0),2) AS chargeback_rate
FROM monthly_performance p JOIN merchants m ON p.merchant_id=m.merchant_id
GROUP BY m.segment ORDER BY growth_pct DESC LIMIT 100"""
        return """SELECT month, ROUND(SUM(gmv),0) AS gmv, SUM(orders) AS orders,
 ROUND(100.0*SUM(successful_payments)/NULLIF(SUM(payment_attempts),0),2) AS payment_success_rate,
 ROUND(100.0*SUM(refunds)/NULLIF(SUM(gmv),0),2) AS refund_rate
FROM monthly_performance GROUP BY month ORDER BY month LIMIT 100"""

    def validate(self, sql: str, plan: QueryPlan) -> ValidationReport:
        checks: list[str] = []
        try:
            normalized = validate_readonly_sql(re.sub(r"^```(?:sql)?|```$", "", sql.strip(), flags=re.I))
            checks.append("read_only_ast")
            tree = sqlglot.parse_one(normalized, read="sqlite")
            referenced_tables = {table.name for table in tree.find_all(exp.Table)}
            cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
            physical_tables = referenced_tables - cte_names
            unknown_tables = physical_tables - set(self.catalog.tables)
            if unknown_tables:
                raise ValueError(f"Unknown tables: {', '.join(sorted(unknown_tables))}")
            if physical_tables - set(plan.tables):
                raise ValueError(f"SQL used tables outside query plan: {', '.join(sorted(physical_tables - set(plan.tables)))}")
            checks.append("schema_grounding")
            if any(isinstance(node, exp.Star) for node in tree.walk()):
                raise ValueError("SELECT * is not allowed; select explicit columns")
            checks.append("explicit_columns")
            uri = f"file:{self.db_path.resolve()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            try:
                explain_rows = conn.execute(f"EXPLAIN QUERY PLAN {normalized}").fetchall()
            finally:
                conn.close()
            checks.append("sqlite_explain")
            return ValidationReport(valid=True, normalized_sql=normalized, checks=checks, explain_plan=[str(row[3]) for row in explain_rows])
        except Exception as exc:
            return ValidationReport(valid=False, checks=checks, error=str(exc))
