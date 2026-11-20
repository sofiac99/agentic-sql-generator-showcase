from __future__ import annotations

import math
import random
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp


SCHEMA = """
merchants(merchant_id, merchant_name, segment, region, acquisition_channel,
          onboarded_date, account_owner, risk_tier)
monthly_performance(month, merchant_id, gmv, orders, refunds, chargebacks,
                    payment_attempts, successful_payments, active_customers)
interactions(interaction_date, merchant_id, channel, topic, sentiment, notes)
behavior_daily(event_date, merchant_id, category, views, clicks, wishlists,
               bookings, booking_value, unique_visitors)
""".strip()


def create_demo_database(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _ensure_behavior_data(path)
        return path
    rng = random.Random(42)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE merchants (
          merchant_id INTEGER PRIMARY KEY, merchant_name TEXT, segment TEXT,
          region TEXT, acquisition_channel TEXT, onboarded_date TEXT,
          account_owner TEXT, risk_tier TEXT
        );
        CREATE TABLE monthly_performance (
          month TEXT, merchant_id INTEGER, gmv REAL, orders INTEGER, refunds REAL,
          chargebacks REAL, payment_attempts INTEGER, successful_payments INTEGER,
          active_customers INTEGER, FOREIGN KEY(merchant_id) REFERENCES merchants(merchant_id)
        );
        CREATE TABLE interactions (
          interaction_date TEXT, merchant_id INTEGER, channel TEXT, topic TEXT,
          sentiment TEXT, notes TEXT
        );
        CREATE TABLE behavior_daily (
          event_date TEXT, merchant_id INTEGER, category TEXT, views INTEGER,
          clicks INTEGER, wishlists INTEGER, bookings INTEGER,
          booking_value REAL, unique_visitors INTEGER,
          FOREIGN KEY(merchant_id) REFERENCES merchants(merchant_id)
        );
        """
    )
    segments = ["Enterprise", "Mid-market", "SMB"]
    regions = ["North America", "Europe", "APAC", "LATAM"]
    channels = ["Partner", "Inbound", "Outbound", "Self-serve"]
    owners = ["Maya Chen", "Noah Williams", "Sofia Patel", "Liam Brooks"]
    names = [
        "Atlas Outfitters", "Bloom Market", "Copper & Co", "Drift Coffee",
        "Evergreen Supply", "Fable Home", "Glow Beauty", "Harbor Goods",
        "Indigo Labs", "Juniper Foods", "Kite Travel", "Lumen Fitness",
        "Mosaic Works", "Northstar Tech", "Olive Kitchen", "Peak Learning",
        "Quartz Health", "Rivet Auto", "Solace Living", "Tandem Media",
        "Union Craft", "Vela Mobility", "Willow Pets", "Yellow Finch",
    ]
    merchants: list[tuple[Any, ...]] = []
    for i, name in enumerate(names, 1):
        segment = segments[(i - 1) % 3]
        risk = "High" if i in (6, 11, 17, 22) else "Medium" if i % 4 == 0 else "Low"
        merchants.append((i, name, segment, regions[i % 4], channels[i % 4], f"2023-{(i%12)+1:02d}-01", owners[i % 4], risk))
    conn.executemany("INSERT INTO merchants VALUES (?,?,?,?,?,?,?,?)", merchants)

    perf = []
    for month_idx in range(18):
        year = 2025 + month_idx // 12
        month = month_idx % 12 + 1
        month_key = f"{year}-{month:02d}-01"
        seasonality = 1 + 0.12 * math.sin(month / 12 * math.pi * 2)
        for mid, _, segment, _, _, _, _, risk in merchants:
            base = {"Enterprise": 420000, "Mid-market": 150000, "SMB": 42000}[segment]
            merchant_growth = 0.009 + (mid % 5) * 0.004
            if mid in (6, 11, 17, 22):
                merchant_growth = -0.012
            gmv = base * (1 + merchant_growth) ** month_idx * seasonality * rng.uniform(.88, 1.12)
            orders = max(1, int(gmv / ({"Enterprise": 180, "Mid-market": 105, "SMB": 62}[segment])))
            attempts = int(orders * rng.uniform(1.04, 1.13))
            success_rate = rng.uniform(.91, .985) - (.035 if risk == "High" else 0)
            successes = int(attempts * success_rate)
            refund_rate = rng.uniform(.012, .048) + (.02 if risk == "High" else 0)
            cb_rate = rng.uniform(.001, .007) + (.01 if risk == "High" else 0)
            perf.append((month_key, mid, round(gmv, 2), orders, round(gmv*refund_rate, 2), round(gmv*cb_rate, 2), attempts, successes, int(orders*rng.uniform(.55,.8))))
    conn.executemany("INSERT INTO monthly_performance VALUES (?,?,?,?,?,?,?,?,?)", perf)
    interaction_rows = []
    topics = ["payment failures", "growth planning", "refund spike", "new market", "checkout optimization"]
    for mid in range(1, 25):
        sentiment = "negative" if mid in (6, 11, 17, 22) else "positive" if mid % 3 else "neutral"
        interaction_rows.append((date(2026, 6, (mid % 27) + 1).isoformat(), mid, "Email" if mid % 2 else "Call", topics[mid % len(topics)], sentiment, "Follow-up requested by merchant."))
    conn.executemany("INSERT INTO interactions VALUES (?,?,?,?,?,?)", interaction_rows)
    _seed_behavior_rows(conn, rng)
    conn.commit()
    conn.close()
    return path


def _seed_behavior_rows(conn: sqlite3.Connection, rng: random.Random) -> None:
    categories = ["Apparel", "Beauty", "Electronics", "Food & Drink", "Home", "Travel"]
    rows = []
    for month_idx in range(18):
        year = 2025 + month_idx // 12
        month = month_idx % 12 + 1
        event_date = f"{year}-{month:02d}-01"
        trend = 1 + month_idx * .025
        for merchant_id in range(1, 25):
            category = categories[(merchant_id - 1) % len(categories)]
            base = 18000 + (merchant_id % 6) * 4200
            views = int(base * trend * rng.uniform(.88, 1.12))
            click_rate = .20 + (merchant_id % 4) * .018
            wishlist_rate = .055 + (merchant_id % 3) * .012
            conversion_rate = .018 + (merchant_id % 5) * .004
            if merchant_id in (6, 11, 17, 22):
                conversion_rate *= .68
            clicks = int(views * click_rate)
            wishlists = int(views * wishlist_rate)
            bookings = int(views * conversion_rate * (1 + month_idx * .006))
            booking_value = bookings * rng.uniform(82, 235)
            visitors = int(views / rng.uniform(2.1, 3.4))
            rows.append((event_date, merchant_id, category, views, clicks, wishlists, bookings, round(booking_value, 2), visitors))
    conn.executemany("INSERT INTO behavior_daily VALUES (?,?,?,?,?,?,?,?,?)", rows)


def _ensure_behavior_data(path: Path) -> None:
    """Non-destructively migrate databases created by earlier demo versions."""
    conn = sqlite3.connect(path)
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='behavior_daily'").fetchone()
    if not exists:
        conn.execute("""CREATE TABLE behavior_daily (
          event_date TEXT, merchant_id INTEGER, category TEXT, views INTEGER,
          clicks INTEGER, wishlists INTEGER, bookings INTEGER,
          booking_value REAL, unique_visitors INTEGER,
          FOREIGN KEY(merchant_id) REFERENCES merchants(merchant_id))""")
        _seed_behavior_rows(conn, random.Random(84))
        conn.commit()
    conn.close()


def validate_readonly_sql(sql: str, max_rows: int = 200) -> str:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise ValueError("Empty SQL query")
    try:
        statements = sqlglot.parse(cleaned, read="sqlite")
    except Exception as exc:
        raise ValueError(f"Invalid SQL: {exc}") from exc
    if len(statements) != 1:
        raise ValueError("Only one SQL statement is allowed")
    tree = statements[0]
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Attach, exp.Pragma)
    if any(tree.find(node) is not None for node in forbidden):
        raise ValueError("Only read-only SELECT queries are allowed")
    if not isinstance(tree, (exp.Select, exp.Union)) and tree.find(exp.Select) is None:
        raise ValueError("Query must contain SELECT")
    if tree.args.get("limit") is None:
        cleaned += f" LIMIT {max_rows}"
    return cleaned


def run_query(path: str | Path, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    safe_sql = validate_readonly_sql(sql)
    uri = f"file:{Path(path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(safe_sql)
        rows = [dict(row) for row in cursor.fetchall()]
        columns = [item[0] for item in cursor.description or []]
        return columns, rows
    finally:
        conn.close()
