from __future__ import annotations

from html import escape
from pathlib import Path

from agentscope.analytics.budget import BudgetStatus
from agentscope.analytics.team_service import TeamAnalyticsService
from agentscope.reporting.formatters import (
    format_integer,
    format_percentage,
    format_usd,
)
from agentscope.storage.repository import Repository


def _cell(value: object) -> str:
    return escape("" if value is None else str(value))


def _usage_table(rows: list[dict], dimension: str, title: str) -> str:
    body = "".join(
        "<tr>"
        f"<td>{_cell(row.get(dimension))}</td>"
        f"<td>{format_integer(int(row.get('sessions') or 0))}</td>"
        f"<td>{format_integer(int(row.get('total_tokens') or 0))}</td>"
        f"<td>{format_integer(int(row.get('cached_input_tokens') or 0))}</td>"
        "</tr>"
        for row in rows
    )
    if not body:
        body = '<tr><td colspan="4">Nenhum dado disponível.</td></tr>'
    return (
        f"<section><h2>{escape(title)}</h2><table>"
        "<thead><tr><th>Dimensão</th><th>Sessões</th><th>Tokens</th><th>Cache</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def _daily_table(rows: list[dict]) -> str:
    body = "".join(
        "<tr>"
        f"<td>{_cell(row.get('day'))}</td>"
        f"<td>{format_integer(int(row.get('sessions') or 0))}</td>"
        f"<td>{format_integer(int(row.get('total_tokens') or 0))}</td>"
        "</tr>"
        for row in rows
    )
    if not body:
        body = '<tr><td colspan="3">Nenhum dado disponível.</td></tr>'
    return (
        "<section><h2>Tendência diária</h2><table>"
        "<thead><tr><th>Dia</th><th>Sessões</th><th>Tokens</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def _budget_section(budget: BudgetStatus | None) -> str:
    if budget is None:
        return ""
    return (
        "<section><h2>Orçamento mensal</h2><div class='cards'>"
        f"<div class='card'><span>Orçamento</span><strong>{format_usd(budget.budget_usd)}</strong></div>"
        f"<div class='card'><span>Gasto observado</span><strong>{format_usd(budget.observed_spend_usd)}</strong></div>"
        f"<div class='card'><span>Consumo</span><strong>{format_percentage(budget.consumed_ratio)}</strong></div>"
        f"<div class='card'><span>Projeção até o fim do mês</span><strong>{format_usd(budget.projected_end_of_month_usd)}</strong></div>"
        "</div><p class='note'>A projeção usa a média diária do período transcorrido e não representa uma fatura futura garantida.</p></section>"
    )


def _quality_section(quality: dict) -> str:
    identity = ", ".join(
        f"{_cell(row['confidence'])}: {format_integer(int(row['users']))}"
        for row in quality["identity_confidence"]
    ) or "Não disponível"
    correlation = ", ".join(
        f"{_cell(row['confidence'])}: {format_integer(int(row['events']))}"
        for row in quality["optimization_confidence"]
    ) or "Não disponível"
    coverage_rows = "".join(
        "<tr>"
        f"<td>{_cell(row['source'])}</td>"
        f"<td>{format_integer(int(row['sessions']))}</td>"
        f"<td>{'Sim' if row['has_tokens'] else 'Não'}</td>"
        f"<td>{'Sim' if row['has_cache'] else 'Não'}</td>"
        f"<td>{'Sim' if row['has_cost'] else 'Não'}</td>"
        "</tr>"
        for row in quality["source_coverage"]
    )
    if not coverage_rows:
        coverage_rows = '<tr><td colspan="5">Nenhum dado disponível.</td></tr>'
    return (
        "<section><h2>Qualidade dos dados</h2>"
        "<div class='cards'>"
        f"<div class='card'><span>Tokens sem modelo</span><strong>{format_percentage(quality['unknown_model_ratio'])}</strong></div>"
        f"<div class='card'><span>Erros de importação</span><strong>{format_integer(int(quality['import_errors']))}</strong></div>"
        "</div>"
        f"<p><strong>Confiança de identidade:</strong> {identity}</p>"
        f"<p><strong>Confiança de correlação:</strong> {correlation}</p>"
        "<h3>Cobertura observada por fonte</h3>"
        "<table><thead><tr><th>Fonte</th><th>Sessões</th><th>Tokens</th><th>Cache</th><th>Custo</th></tr></thead>"
        f"<tbody>{coverage_rows}</tbody></table>"
        f"<p class='note'>Diagnósticos de provider: {_cell(quality['diagnostics_note'])}.</p>"
        "<p class='note'>Cobertura observada indica dados presentes no banco consolidado; não substitui a declaração de capabilities do adapter.</p>"
        "</section>"
    )


def generate_team_html_report(
    repository: Repository,
    analytics: TeamAnalyticsService,
    output: Path,
    *,
    budget: BudgetStatus | None = None,
) -> Path:
    del repository
    summary = analytics.summary()
    quality = analytics.data_quality()
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>AgentScope — Relatório da equipe</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 32px; color: #1f2937; }}
h1, h2 {{ margin-bottom: 12px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; }}
.card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; }}
.card span {{ display:block; font-size: 12px; color:#666; }}
.card strong {{ display:block; margin-top:6px; font-size:22px; }}
section {{ margin-top: 28px; }}
table {{ width:100%; border-collapse: collapse; }}
th, td {{ text-align:left; padding:8px; border-bottom:1px solid #e5e7eb; }}
.note {{ color:#555; font-size:13px; }}
</style>
</head>
<body>
<h1>Resumo da equipe</h1>
<p class="note">Volume de tokens mede uso, não produtividade ou desempenho individual.</p>
<div class="cards">
<div class="card"><span>Desenvolvedores</span><strong>{format_integer(summary.users)}</strong></div>
<div class="card"><span>Máquinas</span><strong>{format_integer(summary.machines)}</strong></div>
<div class="card"><span>Sessões</span><strong>{format_integer(summary.sessions)}</strong></div>
<div class="card"><span>Tokens</span><strong>{format_integer(summary.total_tokens)}</strong></div>
<div class="card"><span>Cache</span><strong>{format_percentage(summary.cache_ratio)}</strong></div>
<div class="card"><span>Custos — observado</span><strong>{format_usd(summary.observed_cost_usd)}</strong></div>
<div class="card"><span>Custos — estimado</span><strong>{format_usd(summary.estimated_raw_cost_usd)}</strong></div>
<div class="card"><span>Economia</span><strong>{format_usd(summary.total_savings_usd)}</strong></div>
</div>
{_budget_section(budget)}
{_usage_table(analytics.by_user(), 'user', 'Por usuário')}
{_usage_table(analytics.by_project(), 'project', 'Por projeto')}
{_usage_table(analytics.by_source(), 'source', 'Por fonte')}
{_usage_table(analytics.by_model(), 'model', 'Por modelo')}
{_daily_table(analytics.by_day())}
{_quality_section(quality)}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
