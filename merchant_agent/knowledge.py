KNOWLEDGE_BASE = [
    {
        "title": "GMV definition",
        "source": "Metric catalog",
        "content": "GMV is gross merchandise value processed before refunds and chargebacks. Growth comparisons should use SUM(monthly_performance.gmv) and comparable time windows.",
    },
    {
        "title": "Payment success rate",
        "source": "Metric catalog",
        "content": "Payment success rate equals SUM(successful_payments) / SUM(payment_attempts), never the unweighted average of merchant-level rates. Below 94% merits checkout investigation.",
    },
    {
        "title": "Refund and chargeback risk",
        "source": "Risk playbook",
        "content": "Refund rate is refunds / GMV and chargeback rate is chargebacks / GMV. Chargeback rate above 1% is high risk; analyze with merchant risk tier and recent interaction sentiment.",
    },
    {
        "title": "Merchant prioritization",
        "source": "Success playbook",
        "content": "Prioritize high-GMV merchants with declining GMV, payment success below 94%, high risk tier, or negative support sentiment. Recommended owners come from merchants.account_owner.",
    },
    {
        "title": "Segment strategy",
        "source": "2026 planning memo",
        "content": "Enterprise retention is the first priority. Mid-market expansion is the second. SMB interventions should be programmatic unless revenue or risk is unusually high.",
    },
    {
        "title": "Monthly trend example",
        "source": "Verified query library",
        "content": "For monthly GMV trends: SELECT month, SUM(gmv) AS gmv FROM monthly_performance GROUP BY month ORDER BY month. Time-series charts should use month on x and gmv on y.",
    },
    {
        "title": "Segment performance example",
        "source": "Verified query library",
        "content": "Join monthly_performance p to merchants m on merchant_id, then group by m.segment. Aggregate payments before calculating success rate.",
    },
]
