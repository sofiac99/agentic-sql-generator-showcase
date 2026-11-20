from pathlib import Path

import pytest

from merchant_agent.database import create_demo_database, run_query, validate_readonly_sql
from merchant_agent.graph import MerchantAnalyticsAgent
from merchant_agent.sql_generation import QueryPlan, SQLQueryGenerator


def test_sql_guardrail_rejects_writes():
    with pytest.raises(ValueError):
        validate_readonly_sql("DROP TABLE merchants")
    with pytest.raises(ValueError):
        validate_readonly_sql("SELECT 1; DELETE FROM merchants")


def test_sql_guardrail_adds_limit():
    assert validate_readonly_sql("SELECT merchant_id FROM merchants").endswith("LIMIT 200")


def test_demo_database(tmp_path: Path):
    db = create_demo_database(tmp_path / "demo.db")
    columns, rows = run_query(db, "SELECT COUNT(*) AS count FROM merchants")
    assert columns == ["count"]
    assert rows[0]["count"] == 24


def test_agent_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = MerchantAnalyticsAgent(tmp_path / "demo.db")
    result = agent.analyze("Compare payment success rate by channel this quarter")
    assert result["rows"]
    assert result["insight"]["chart"]["x"] == "acquisition_channel"
    assert "SELECT" in result["sql"]
    assert result["trace"][-1] == "Produced typed dashboard insight"


def test_behavior_analytics_pipeline(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    snapshot = MerchantAnalyticsAgent(tmp_path / "demo.db").dashboard_snapshot()
    assert snapshot["kpis"]["total_views"] > snapshot["kpis"]["total_bookings"] > 0
    assert 0 < snapshot["kpis"]["conversion_rate"] < 100
    assert len(snapshot["categories"]) == 6
    assert len(snapshot["trend"]) == 18
    assert [row["stage"] for row in snapshot["funnel"]] == ["Views", "Clicks", "Wishlists", "Bookings"]
    assert snapshot["summary"]["summary"]


def test_plan_first_sql_generation(tmp_path: Path):
    db = create_demo_database(tmp_path / "demo.db")
    generator = SQLQueryGenerator(db)
    plan = generator.plan("Show monthly booking conversion trend", [])
    draft = generator.generate("Show monthly booking conversion trend", plan, [])
    report = generator.validate(draft.sql, plan)
    assert plan.tables == ["behavior_daily"]
    assert plan.time_grain == "month"
    assert report.valid
    assert report.checks == ["read_only_ast", "schema_grounding", "explicit_columns", "sqlite_explain"]
    assert report.explain_plan


def test_schema_grounding_rejects_hallucinated_table(tmp_path: Path):
    db = create_demo_database(tmp_path / "demo.db")
    generator = SQLQueryGenerator(db)
    plan = QueryPlan(intent="lookup", tables=["merchants"])
    report = generator.validate("SELECT merchant_id FROM imaginary_merchants", plan)
    assert not report.valid
    assert "Unknown tables" in report.error


def test_sql_generator_rejects_select_star(tmp_path: Path):
    db = create_demo_database(tmp_path / "demo.db")
    generator = SQLQueryGenerator(db)
    plan = QueryPlan(intent="lookup", tables=["merchants"])
    report = generator.validate("SELECT * FROM merchants", plan)
    assert not report.valid
    assert "SELECT *" in report.error
