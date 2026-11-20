from __future__ import annotations

import json
from pathlib import Path

import sqlglot
from sqlglot import exp

from merchant_agent.database import create_demo_database
from merchant_agent.sql_generation import SQLQueryGenerator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    db = create_demo_database(root / "data" / "merchant_analytics.db")
    generator = SQLQueryGenerator(db)
    cases = json.loads((root / "evals" / "sql_questions.json").read_text())
    passed = 0
    for case in cases:
        plan = generator.plan(case["question"], [])
        draft = generator.generate(case["question"], plan, [])
        report = generator.validate(draft.sql, plan)
        tree = sqlglot.parse_one(report.normalized_sql, read="sqlite") if report.valid else None
        tables = {table.name for table in tree.find_all(exp.Table)} if tree else set()
        columns = {alias.alias_or_name for alias in tree.expressions} if tree else set()
        ok = report.valid and set(case["required_tables"]).issubset(tables) and set(case["required_columns"]).issubset(columns)
        passed += int(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {case['question']}")
        if not ok:
            print(f"  plan={plan.model_dump()} error={report.error} tables={tables} columns={columns}")
    print(f"\n{passed}/{len(cases)} evaluation cases passed")
    raise SystemExit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()

