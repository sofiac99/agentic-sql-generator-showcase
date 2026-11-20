from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from merchant_agent import MerchantAnalyticsAgent

load_dotenv()

st.set_page_config(page_title="Pulse · Merchant Intelligence", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700&display=swap');
:root { --ink:#17221d; --muted:#66716b; --mint:#e6f5ed; --green:#147d52; --lime:#b9e76f; --paper:#f6f7f3; }
.stApp { background: var(--paper); color: var(--ink); font-family:'DM Sans',sans-serif; }
[data-testid="stSidebar"] { background:#17241e; border-right:0; }
[data-testid="stSidebar"] * { color:#eaf2ed !important; }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; letter-spacing:-.03em; }
.block-container { padding-top:2rem; max-width:1500px; }
.eyebrow { color:#147d52; text-transform:uppercase; letter-spacing:.14em; font-weight:700; font-size:.72rem; }
.hero { padding:.5rem 0 1.3rem; }
.hero h1 { font-size:2.4rem; margin:.25rem 0; }
.hero p { color:#66716b; max-width:680px; font-size:1.02rem; }
.status { display:inline-flex;align-items:center;gap:.45rem;border:1px solid #cfd8d2;border-radius:999px;padding:.35rem .7rem;background:white;font-size:.78rem;color:#526058; }
.dot { width:7px;height:7px;border-radius:50%;background:#2ca66f;box-shadow:0 0 0 3px #dff4e9; }
.metric-card { background:white;border:1px solid #e0e5e1;border-radius:14px;padding:1.05rem 1.1rem;min-height:112px;box-shadow:0 2px 10px rgba(28,51,39,.03); }
.metric-label { color:#738078;font-size:.77rem;text-transform:uppercase;letter-spacing:.07em;font-weight:600; }
.metric-value { color:#17221d;font-family:'Manrope';font-size:1.65rem;font-weight:700;margin-top:.35rem; }
.metric-delta { color:#147d52;font-size:.78rem;margin-top:.15rem; }
.summary { background:#e5f2ea;border:1px solid #cfe4d7;border-radius:16px;padding:1.25rem 1.35rem;margin:.7rem 0 1rem; }
.summary h3 { margin:0 0 .4rem;color:#164f38; }
.summary p { margin:0;color:#375c4b;line-height:1.6; }
.action { background:white;border:1px solid #e0e5e1;border-left:4px solid #b9e76f;border-radius:10px;padding:.8rem 1rem;margin:.55rem 0; }
.action b { color:#243129; }.action span { color:#758078;font-size:.86rem; }
.source { background:white;border:1px solid #e0e5e1;border-radius:10px;padding:.75rem .9rem;margin:.45rem 0; }
.source-title {font-weight:600}.source-meta {color:#7a857e;font-size:.76rem}
div[data-testid="stChatInput"] { background:white;border-radius:14px; }
.stButton button { border-radius:10px;border-color:#d5ddd8;background:white; }
.stButton button:hover { border-color:#147d52;color:#147d52; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_agent() -> MerchantAnalyticsAgent:
    return MerchantAnalyticsAgent(os.getenv("MERCHANT_DB_PATH", "data/merchant_analytics.db"))


agent = get_agent()

with st.sidebar:
    st.markdown("## ◈ PULSE")
    st.caption("MERCHANT INTELLIGENCE")
    st.markdown("---")
    st.markdown("**Workspace**")
    st.markdown("▣ Executive overview")
    st.markdown("◎ Ask the analyst")
    st.markdown("◇ Merchant portfolio")
    st.markdown("△ Risk signals")
    st.markdown("---")
    st.markdown("**Agent pipeline**")
    st.caption("1  Aggregate behavior events")
    st.caption("2  Compute governed metrics")
    st.caption("3  LLM structured summary")
    st.caption("4  Dashboard + SQL drill-down")
    st.markdown("---")
    st.caption(f"MODE · {agent.mode.upper()}")
    if agent.mode == "Demo":
        st.info("Add OPENAI_API_KEY to enable live LLM reasoning and embeddings.")

st.markdown(
    f"""<div class="hero"><div class="eyebrow">AI analytics workspace</div>
    <h1>Merchant performance, explained.</h1>
    <p>Ask a business question. Pulse retrieves the right operating context, writes safe SQL, and turns the result into a decision-ready brief.</p>
    <div class="status"><span class="dot"></span> Agent online · {agent.mode} mode</div></div>""",
    unsafe_allow_html=True,
)

@st.cache_data(ttl=300)
def get_behavior_snapshot() -> dict:
    return agent.dashboard_snapshot()


snapshot = get_behavior_snapshot()
behavior = snapshot["kpis"]
st.markdown("<div class='eyebrow'>Portfolio behavior pipeline · Latest month</div>", unsafe_allow_html=True)
overview_cols = st.columns(5)
overview_metrics = [
    ("Views", f"{behavior['total_views']:,}", "Behavior input"),
    ("Engagement rate", f"{behavior['engagement_rate']:.2f}%", "Clicks + wishlists / views"),
    ("Wishlist rate", f"{behavior['wishlist_rate']:.2f}%", "Intent signal"),
    ("Conversion rate", f"{behavior['conversion_rate']:.2f}%", f"{behavior['conversion_change_pp']:+.2f} pp MoM"),
    ("Booking value", f"${behavior['booking_value']:,.0f}", f"{behavior['total_bookings']:,} bookings"),
]
for col, (label, value, delta) in zip(overview_cols, overview_metrics):
    col.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div><div class='metric-delta'>{delta}</div></div>", unsafe_allow_html=True)

summary = snapshot["summary"]
st.markdown(f"<div class='summary'><h3>{summary['headline']}</h3><p>{summary['summary']}</p></div>", unsafe_allow_html=True)

funnel_col, trend_col, category_col = st.columns([.8, 1.35, 1.1], gap="large")
with funnel_col:
    funnel_df = pd.DataFrame(snapshot["funnel"])
    fig = px.funnel(funnel_df, y="stage", x="volume", title="Latest behavior funnel")
    fig.update_traces(marker_color=["#1d6549", "#3d916b", "#75b98f", "#b9e76f"])
    fig.update_layout(template="plotly_white", margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
with trend_col:
    trend_df = pd.DataFrame(snapshot["trend"])
    fig = px.line(trend_df, x="month", y="conversion_rate", markers=True, title="Conversion trend")
    fig.update_traces(line_color="#147d52", fill="tozeroy", fillcolor="rgba(20,125,82,.10)")
    fig.update_layout(template="plotly_white", margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
with category_col:
    cat_df = pd.DataFrame(snapshot["categories"])
    fig = px.bar(cat_df, x="booking_value", y="category", orientation="h", title="Top categories by booking value")
    fig.update_traces(marker_color="#547b68")
    fig.update_layout(template="plotly_white", yaxis={"categoryorder":"total ascending"}, margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Pipeline lineage & metric definitions"):
    line_cols = st.columns(4)
    for col, (index, item) in zip(line_cols, enumerate(snapshot["lineage"], 1)):
        col.markdown(f"**{index}**")
        col.caption(item)
    st.markdown("**LLM-detected opportunities**")
    for item in summary.get("opportunities", []):
        st.markdown(f"- {item}")
    for item in summary.get("risks", []):
        st.warning(item)

st.markdown("---")
st.markdown("### Ask the analytics agent")
st.caption("Use natural language to drill into merchant, channel, segment, payment, or risk data with validated read-only SQL.")

examples = [
    "Which merchant segment is growing fastest and where is risk increasing?",
    "Compare payment success rate by channel this quarter.",
    "Which merchants should the account team prioritize this week?",
    "Show monthly GMV and flag material changes.",
]

if "question" not in st.session_state:
    st.session_state.question = examples[0]
if "result" not in st.session_state:
    st.session_state.result = None

st.markdown("#### Start with a question")
cols = st.columns(4)
for i, example in enumerate(examples):
    if cols[i].button(example, use_container_width=True, key=f"example-{i}"):
        st.session_state.question = example
        st.session_state.result = agent.analyze(example)

question = st.chat_input("Ask about growth, payment performance, risk, or merchant priorities…")
if question:
    st.session_state.question = question
    with st.spinner("Retrieving context and analyzing merchant data…"):
        st.session_state.result = agent.analyze(question)

if st.session_state.result is None:
    with st.spinner("Preparing the executive view…"):
        st.session_state.result = agent.analyze(st.session_state.question)

result = st.session_state.result
insight = result["insight"]
st.markdown(f"<div class='eyebrow' style='margin-top:1.4rem'>Analysis · {st.session_state.question}</div>", unsafe_allow_html=True)
st.markdown(f"## {insight['headline']}")

kpis = insight.get("kpis", [])
if kpis:
    metric_cols = st.columns(min(4, len(kpis)))
    for col, item in zip(metric_cols, kpis[:4]):
        delta = item.get("delta") or ("Primary signal" if item.get("direction") == "up" else "Observed")
        col.markdown(f"<div class='metric-card'><div class='metric-label'>{item['label']}</div><div class='metric-value'>{item['value']}</div><div class='metric-delta'>{delta}</div></div>", unsafe_allow_html=True)

st.markdown(f"<div class='summary'><h3>Executive readout</h3><p>{insight['executive_summary']}</p></div>", unsafe_allow_html=True)

left, right = st.columns([1.75, 1], gap="large")
with left:
    chart = insight.get("chart")
    df = pd.DataFrame(result.get("rows", []))
    if chart and not df.empty and chart["x"] in df.columns:
        valid_y = [y for y in chart["y"] if y in df.columns]
        if valid_y:
            if chart["chart_type"] in ("line", "area"):
                fig = px.line(df, x=chart["x"], y=valid_y, title=chart["title"], markers=True)
            else:
                fig = px.bar(df, x=chart["x"], y=valid_y, title=chart["title"])
            fig.update_layout(template="plotly_white", legend_title_text="", margin=dict(l=20,r=20,t=55,b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white", colorway=["#147d52", "#9ccf54", "#547b68"])
            fig.update_xaxes(showgrid=False)
            fig.update_yaxes(gridcolor="#e8ece9")
            st.plotly_chart(fig, use_container_width=True)
    st.markdown("#### What stands out")
    for finding in insight.get("findings", []):
        st.markdown(f"- {finding}")
with right:
    st.markdown("#### Recommended next moves")
    for action in insight.get("actions", []):
        st.markdown(f"<div class='action'><b>{action['title']}</b><br><span>{action['rationale']} · Owner: {action.get('owner','Merchant Success')}</span></div>", unsafe_allow_html=True)
    st.progress(float(insight.get("confidence", .8)), text=f"Answer confidence · {insight.get('confidence', .8):.0%}")

with st.expander("Evidence & agent reasoning"):
    ev1, ev2 = st.columns([1, 1])
    with ev1:
        st.markdown("**Retrieved business context**")
        for ctx in result.get("contexts", []):
            st.markdown(f"<div class='source'><div class='source-title'>{ctx['title']}</div><div class='source-meta'>{ctx['source']} · semantic score {ctx['score']:.2f}</div></div>", unsafe_allow_html=True)
        st.markdown("**Execution trace**")
        for step in result.get("trace", []):
            st.caption(f"✓ {step}")
    with ev2:
        st.markdown("**Validated SQL**")
        st.code(result.get("sql", "No SQL generated"), language="sql")
        if result.get("query_plan"):
            st.markdown("**Typed query plan**")
            st.json(result["query_plan"])
        if result.get("validation_checks"):
            st.caption("Validation · " + " → ".join(result["validation_checks"]))
        if result.get("explain_plan"):
            st.markdown("**SQLite EXPLAIN preflight**")
            for line in result["explain_plan"]:
                st.caption(line)
        st.markdown("**Result preview**")
        st.dataframe(pd.DataFrame(result.get("rows", [])), use_container_width=True, hide_index=True)

if insight.get("caveats"):
    st.caption("Notes · " + " · ".join(insight["caveats"]))
