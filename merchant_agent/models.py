from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class RetrievedContext(BaseModel):
    title: str
    content: str
    score: float = Field(ge=0, le=1)
    source: str


class KPI(BaseModel):
    label: str
    value: str
    delta: str | None = None
    direction: Literal["up", "down", "flat", "neutral"] = "neutral"


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "area", "scatter", "table"]
    title: str
    x: str
    y: list[str]
    color: str | None = None


class Action(BaseModel):
    priority: Literal["high", "medium", "low"]
    title: str
    rationale: str
    owner: str = "Merchant Success"


class InsightResponse(BaseModel):
    headline: str
    executive_summary: str
    kpis: list[KPI] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    chart: ChartSpec | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)
    caveats: list[str] = Field(default_factory=list)


class BehaviorKPI(BaseModel):
    total_views: int
    total_clicks: int
    total_wishlists: int
    total_bookings: int
    booking_value: float
    engagement_rate: float
    click_through_rate: float
    wishlist_rate: float
    conversion_rate: float
    conversion_change_pp: float


class BehaviorSummary(BaseModel):
    headline: str
    summary: str
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    question: str
    intent: str
    contexts: list[dict[str, Any]]
    schema: str
    sql: str
    sql_error: str
    rows: list[dict[str, Any]]
    columns: list[str]
    insight: dict[str, Any]
    trace: list[str]
    attempts: int
    query_plan: dict[str, Any]
    sql_rationale: str
    validation_checks: list[str]
    explain_plan: list[str]
