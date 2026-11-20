from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import run_query
from .models import BehaviorKPI, BehaviorSummary


class BehaviorAnalyticsPipeline:
    """Deterministic metrics layer: behavior facts -> governed merchant KPIs."""

    def __init__(self, db_path: str | Path, llm: Any = None):
        self.db_path = db_path
        self.llm = llm

    def aggregate(self) -> dict[str, Any]:
        _, overall = run_query(self.db_path, """
WITH monthly AS (
  SELECT event_date,
    SUM(views) views, SUM(clicks) clicks, SUM(wishlists) wishlists,
    SUM(bookings) bookings, SUM(booking_value) booking_value,
    SUM(unique_visitors) unique_visitors
  FROM behavior_daily GROUP BY event_date
), ranked AS (
  SELECT *, ROW_NUMBER() OVER (ORDER BY event_date DESC) rn FROM monthly
)
SELECT
  SUM(CASE WHEN rn = 1 THEN views ELSE 0 END) total_views,
  SUM(CASE WHEN rn = 1 THEN clicks ELSE 0 END) total_clicks,
  SUM(CASE WHEN rn = 1 THEN wishlists ELSE 0 END) total_wishlists,
  SUM(CASE WHEN rn = 1 THEN bookings ELSE 0 END) total_bookings,
  ROUND(SUM(CASE WHEN rn = 1 THEN booking_value ELSE 0 END), 2) booking_value,
  ROUND(100.0 * SUM(CASE WHEN rn = 1 THEN clicks + wishlists ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 1 THEN views ELSE 0 END), 0), 2) engagement_rate,
  ROUND(100.0 * SUM(CASE WHEN rn = 1 THEN clicks ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 1 THEN views ELSE 0 END), 0), 2) click_through_rate,
  ROUND(100.0 * SUM(CASE WHEN rn = 1 THEN wishlists ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 1 THEN views ELSE 0 END), 0), 2) wishlist_rate,
  ROUND(100.0 * SUM(CASE WHEN rn = 1 THEN bookings ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 1 THEN views ELSE 0 END), 0), 2) conversion_rate,
  ROUND(100.0 * SUM(CASE WHEN rn = 1 THEN bookings ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 1 THEN views ELSE 0 END), 0) -
    100.0 * SUM(CASE WHEN rn = 2 THEN bookings ELSE 0 END) /
    NULLIF(SUM(CASE WHEN rn = 2 THEN views ELSE 0 END), 0), 2) conversion_change_pp
FROM ranked WHERE rn <= 2
""")
        _, categories = run_query(self.db_path, """
SELECT category, SUM(views) views, SUM(clicks) clicks, SUM(wishlists) wishlists,
 SUM(bookings) bookings, ROUND(SUM(booking_value),0) booking_value,
 ROUND(100.0*SUM(clicks + wishlists)/NULLIF(SUM(views),0),2) engagement_rate,
 ROUND(100.0*SUM(bookings)/NULLIF(SUM(views),0),2) conversion_rate
FROM behavior_daily WHERE event_date >= '2026-01-01'
GROUP BY category ORDER BY booking_value DESC
""")
        _, trend = run_query(self.db_path, """
SELECT event_date month, SUM(views) views, SUM(clicks) clicks,
 SUM(wishlists) wishlists, SUM(bookings) bookings,
 ROUND(100.0*SUM(bookings)/NULLIF(SUM(views),0),2) conversion_rate,
 ROUND(SUM(booking_value),0) booking_value
FROM behavior_daily GROUP BY event_date ORDER BY event_date
""")
        _, funnel = run_query(self.db_path, """
WITH latest AS (SELECT MAX(event_date) d FROM behavior_daily)
SELECT 'Views' stage, SUM(views) volume, 1 sort FROM behavior_daily, latest WHERE event_date=d
UNION ALL SELECT 'Clicks', SUM(clicks), 2 FROM behavior_daily, latest WHERE event_date=d
UNION ALL SELECT 'Wishlists', SUM(wishlists), 3 FROM behavior_daily, latest WHERE event_date=d
UNION ALL SELECT 'Bookings', SUM(bookings), 4 FROM behavior_daily, latest WHERE event_date=d
ORDER BY sort
""")
        kpis = BehaviorKPI.model_validate(overall[0])
        return {"kpis": kpis.model_dump(), "categories": categories, "trend": trend, "funnel": funnel}

    def summarize(self, metrics: dict[str, Any]) -> BehaviorSummary:
        if self.llm:
            structured = self.llm.with_structured_output(BehaviorSummary)
            return structured.invoke(
                "You are a merchant growth analyst. Explain only the supplied governed metrics. "
                "State the strongest category opportunity and any funnel risk. Be concise and actionable.\n"
                + json.dumps(metrics, default=str)
            )
        k = metrics["kpis"]
        top = metrics["categories"][0]
        direction = "improved" if k["conversion_change_pp"] >= 0 else "declined"
        return BehaviorSummary(
            headline=f"{top['category']} leads booking value as conversion {direction}",
            summary=(
                f"The latest period generated {k['total_bookings']:,} bookings from {k['total_views']:,} views. "
                f"Engagement is {k['engagement_rate']:.2f}% and conversion is {k['conversion_rate']:.2f}%, "
                f"{abs(k['conversion_change_pp']):.2f} percentage points {'above' if k['conversion_change_pp'] >= 0 else 'below'} the prior month."
            ),
            opportunities=[
                f"Scale {top['category']}: it leads at ${top['booking_value']:,.0f} booking value.",
                "Retarget wishlist users with category-specific offers and availability reminders.",
            ],
            risks=["Investigate high-view categories whose conversion trails the portfolio average."] if any(c["conversion_rate"] < k["conversion_rate"] for c in metrics["categories"]) else [],
        )

    def run(self) -> dict[str, Any]:
        metrics = self.aggregate()
        summary = self.summarize(metrics)
        return {**metrics, "summary": summary.model_dump(), "lineage": [
            "behavior_daily: view, click, wishlist, booking facts",
            "SQL metrics layer: funnel, engagement, category, conversion trend",
            f"Narrative layer: {'LLM structured output' if self.llm else 'deterministic demo summary'}",
            "Streamlit dashboard / admin portal",
        ]}
