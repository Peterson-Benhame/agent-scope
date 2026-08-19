from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from agentscope.analytics.service import AnalyticsService
from agentscope.storage.repository import Repository


def _money(value: float | None) -> str:
    return "N/A" if value is None else f"US$ {value:,.6f}"


def _num(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.4f}"
    if isinstance(value, int):
        return f"{value:,}"
    return escape(str(value))


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">No data available.</p>'
    keys = list(rows[0].keys())
    head = "".join(f"<th>{escape(str(k))}</th>" for k in keys)
    body = "".join(
        "<tr>" + "".join(f"<td>{_num(row.get(k))}</td>" for k in keys) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bar_chart(title: str, rows: list[dict[str, Any]], label_key: str, value_key: str) -> str:
    values = [float(row.get(value_key) or 0) for row in rows]
    maximum = max(values, default=0)
    if maximum <= 0:
        return f'<div class="chart"><h4>{escape(title)}</h4><p class="muted">No data available.</p></div>'
    bars = []
    for row, value in zip(rows, values):
        width = max(1.0, value / maximum * 100.0)
        bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{escape(str(row.get(label_key) or "(unknown)"))}</span>'
            f'<span class="bar"><span style="width:{width:.2f}%"></span></span>'
            f'<span class="bar-value">{_num(value)}</span>'
            '</div>'
        )
    return f'<div class="chart"><h4>{escape(title)}</h4>{"".join(bars)}</div>'


def generate_html_report(repository: Repository, analytics: AnalyticsService, output: Path) -> Path:
    summary = analytics.summary()
    projects = analytics.by_project()
    models = analytics.by_model()
    agents = analytics.by_agent()
    skills = analytics.by_skill()
    tools = analytics.by_tool()
    optimizers = analytics.optimizer_summary()
    for row in optimizers:
        row["optimizer"] = str(row["optimizer"]).title()
    by_day = analytics.by_day()
    savings_day = analytics.savings_by_day()
    cost_day = analytics.cost_by_day()

    with repository.database.connect() as conn:
        errors = conn.execute("SELECT COUNT(*) AS n FROM import_errors").fetchone()["n"]
        confidence = [dict(row) for row in conn.execute(
            "SELECT correlation_confidence, COUNT(*) AS events FROM optimizations GROUP BY correlation_confidence ORDER BY correlation_confidence"
        ).fetchall()]

    cache_pct = summary.cache_ratio * 100.0
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentScope Report</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1180px;margin:0 auto;padding:28px;background:#f6f7f9;color:#16181d}}
h1,h2,h3,h4{{margin-top:1.2em}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.card,.section,.chart{{background:white;border:1px solid #dde1e7;border-radius:10px;padding:16px;margin:12px 0}} .value{{font-size:1.45rem;font-weight:700}}
.muted{{color:#68707c}} table{{width:100%;border-collapse:collapse;background:white}} th,td{{padding:8px 10px;border-bottom:1px solid #e7e9ed;text-align:left;font-size:.9rem}} th{{background:#f0f2f5}}
.bar-row{{display:grid;grid-template-columns:160px 1fr 100px;gap:8px;align-items:center;margin:7px 0}} .bar{{height:12px;background:#eceff3;border-radius:8px;overflow:hidden}} .bar span{{display:block;height:100%;background:#5d6b82}} .bar-value{{text-align:right;font-variant-numeric:tabular-nums}}
code{{background:#eef0f3;padding:2px 5px;border-radius:4px}}
</style></head><body>
<h1>AgentScope</h1><p class="muted">Local-first execution analytics. Safe metadata report: message bodies and tool payloads are excluded.</p>
<section class="section"><h2>Executive Summary</h2><div class="grid">
<div class="card"><div>Sessions</div><div class="value">{summary.sessions}</div></div>
<div class="card"><div>Total tokens</div><div class="value">{summary.total_tokens:,}</div></div>
<div class="card"><div>Tokens saved</div><div class="value">{summary.tokens_saved:,}</div></div>
<div class="card"><div>Observed cost</div><div class="value">{_money(summary.observed_cost_usd)}</div></div>
<div class="card"><div>Total savings</div><div class="value">{_money(summary.total_savings_usd)}</div></div>
</div></section>
<section class="section"><h2>Tokens</h2>{_table([{
    'input_tokens':summary.input_tokens,'cached_input_tokens':summary.cached_input_tokens,
    'output_tokens':summary.output_tokens,'reasoning_output_tokens':summary.reasoning_output_tokens,
    'total_tokens':summary.total_tokens,'tokens_saved':summary.tokens_saved}])}</section>
<section class="section"><h2>Cache</h2><p>Cached input ratio: <strong>{cache_pct:.2f}%</strong></p></section>
<section class="section"><h2>Costs</h2><p>Estimated raw cost: <strong>{_money(summary.estimated_raw_cost_usd)}</strong></p><p>Observed/source-reported cost: <strong>{_money(summary.observed_cost_usd)}</strong></p>{_bar_chart('Cost by day', cost_day, 'day', 'observed_cost_usd')}</section>
<section class="section"><h2>Savings</h2><p>Compression: <strong>{_money(summary.compression_savings_usd)}</strong> · Cache: <strong>{_money(summary.cache_savings_usd)}</strong> · Total: <strong>{_money(summary.total_savings_usd)}</strong></p>{_bar_chart('Savings by day', savings_day, 'day', 'compression_savings_usd')}</section>
<section class="section"><h2>Models</h2>{_table(models)}{_bar_chart('Model distribution', models, 'model', 'input_tokens')}</section>
<section class="section"><h2>Projects</h2>{_table(projects)}{_bar_chart('Project distribution', projects, 'project', 'input_tokens')}</section>
<section class="section"><h2>Agents</h2>{_table(agents)}</section>
<section class="section"><h2>Skills</h2>{_table(skills)}</section>
<section class="section"><h2>Tools / MCPs</h2>{_table(tools)}</section>
<section class="section"><h2>Optimizers</h2>{_table(optimizers)}</section>
<section class="section"><h2>Temporal Trends</h2>{_bar_chart('Tokens by day', by_day, 'day', 'input_tokens')}{_table(by_day)}</section>
<section class="section"><h2>Data Quality</h2><p>Import errors: <strong>{errors}</strong></p><h3>Optimization correlation confidence</h3>{_table(confidence)}</section>
</body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
