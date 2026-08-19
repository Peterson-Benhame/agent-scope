from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from agentscope.analytics.filters import AnalyticsFilter
from agentscope.analytics.service import AnalyticsService
from agentscope.reporting.formatters import (
    format_decimal,
    format_integer,
    format_percentage,
    format_usd,
)
from agentscope.storage.repository import Repository


_HEADER_LABELS = {
    "project": "Projeto",
    "model": "Modelo",
    "user": "Usuário",
    "machine": "Máquina",
    "identity_confidence": "Confiança da identidade",
    "sessions": "Sessões",
    "input_tokens": "Tokens de entrada",
    "cached_input_tokens": "Tokens de entrada em cache",
    "output_tokens": "Tokens de saída",
    "reasoning_output_tokens": "Tokens de raciocínio",
    "total_tokens": "Total de tokens",
    "tokens_saved": "Tokens economizados",
    "agent": "Agente",
    "agent_type": "Tipo",
    "evidence_count": "Evidências",
    "skill": "Habilidade",
    "usage_type": "Uso",
    "tool": "Ferramenta",
    "category": "Categoria",
    "calls": "Chamadas",
    "successful_calls": "Chamadas com sucesso",
    "average_duration_ms": "Duração média (ms)",
    "input_size": "Entrada",
    "output_size": "Saída",
    "optimizer": "Otimizador",
    "events": "Eventos",
    "original_tokens": "Tokens originais",
    "optimized_tokens": "Tokens otimizados",
    "compression_savings_usd": "Economia de compressão (US$)",
    "cache_savings_usd": "Economia de cache (US$)",
    "observed_cost_usd": "Custo observado (US$)",
    "estimated_raw_cost_usd": "Custo estimado bruto (US$)",
    "day": "Dia",
    "correlation_confidence": "Confiança de correlação",
}


def _num(value: Any) -> str:
    if value is None:
        return "Não disponível"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, int):
        return format_integer(value)
    if isinstance(value, float):
        return format_decimal(value, 4)
    return escape(str(value))


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">Não há dados disponíveis.</p>'
    keys = list(rows[0].keys())
    head = "".join(
        f"<th>{escape(_HEADER_LABELS.get(key, key.replace('_', ' ').title()))}</th>"
        for key in keys
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{_num(row.get(key))}</td>" for key in keys) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bar_chart(
    title: str,
    rows: list[dict[str, Any]],
    label_key: str,
    value_key: str,
) -> str:
    values = [float(row.get(value_key) or 0) for row in rows]
    maximum = max(values, default=0)
    if maximum <= 0:
        return (
            f'<div class="chart"><h4>{escape(title)}</h4>'
            '<p class="muted">Não há dados disponíveis.</p></div>'
        )

    bars: list[str] = []
    for row, value in zip(rows, values):
        width = max(1.0, value / maximum * 100.0)
        label = escape(str(row.get(label_key) or "(desconhecido)"))
        bars.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{label}</span>'
            f'<span class="bar"><span style="width:{width:.2f}%"></span></span>'
            f'<span class="bar-value">{_num(value)}</span>'
            '</div>'
        )
    return f'<div class="chart"><h4>{escape(title)}</h4>{"".join(bars)}</div>'


def _date_label(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _period_label(filters: AnalyticsFilter) -> str:
    if filters.from_date is None and filters.to_date is None:
        return "Todo o histórico"
    if filters.from_date is not None and filters.to_date is not None:
        return f"{_date_label(filters.from_date)} a {_date_label(filters.to_date)}"
    if filters.from_date is not None:
        return f"A partir de {_date_label(filters.from_date)}"
    return f"Até {_date_label(filters.to_date)}"


def _delta(value: float | None, *, points: bool = False) -> str:
    if value is None:
        return ""
    arrow = "↑" if value > 0 else "↓" if value < 0 else "→"
    suffix = " p.p." if points else "%"
    return (
        '<div class="delta">'
        f"{arrow} {format_decimal(abs(value), 2)}{suffix} vs. período anterior"
        "</div>"
    )


def _card(label: str, value: str, delta: str = "") -> str:
    return (
        '<div class="card">'
        f'<div class="card-label">{escape(label)}</div>'
        f'<div class="value">{value}</div>'
        f"{delta}"
        "</div>"
    )


def _quality_section(quality: dict[str, object]) -> str:
    confidence = quality.get("optimization_confidence") or {}
    confidence_rows = [
        {"correlation_confidence": name, "events": count}
        for name, count in sorted(dict(confidence).items())
    ]
    unknown_share = quality.get("unknown_model_token_share")
    unknown_share_text = (
        format_percentage(float(unknown_share))
        if unknown_share is not None
        else "Não disponível"
    )
    return (
        '<section class="section"><h2>Qualidade dos dados</h2>'
        f'<p>Erros de importação: <strong>{format_integer(int(quality["import_errors"]))}</strong></p>'
        '<h3>Modelos desconhecidos</h3>'
        '<p>Sessões sem modelo identificado: '
        f'<strong>{format_integer(int(quality["unknown_model_sessions"]))}</strong></p>'
        '<p>Participação de tokens sem modelo identificado: '
        f'<strong>{unknown_share_text}</strong></p>'
        '<p>Evidências de habilidades: '
        f'<strong>{format_integer(int(quality["skill_evidence_rows"]))}</strong></p>'
        '<p>Evidências de agentes: '
        f'<strong>{format_integer(int(quality["agent_evidence_rows"]))}</strong></p>'
        '<h3>Confiança de correlação das otimizações</h3>'
        f'{_table(confidence_rows)}</section>'
    )


def generate_html_report(
    repository: Repository,
    analytics: AnalyticsService,
    output: Path,
    *,
    filters: AnalyticsFilter | None = None,
) -> Path:
    active_filters = filters or analytics.filters
    if active_filters != analytics.filters:
        analytics = AnalyticsService(repository, active_filters)

    summary = analytics.summary()
    comparison = analytics.comparison()
    projects = analytics.by_project()
    models = analytics.by_model()
    users = analytics.by_user()
    machines = analytics.by_machine()
    agents = analytics.by_agent()
    skills = analytics.by_skill()
    tools = analytics.by_tool()
    optimizers = analytics.optimizer_summary()
    for row in optimizers:
        row["optimizer"] = str(row["optimizer"]).title()
    by_day = analytics.by_day()
    savings_day = analytics.savings_by_day()
    cost_day = analytics.cost_by_day()
    quality = analytics.data_quality()

    comparison = comparison or {}
    cards = "".join(
        [
            _card(
                "Sessões",
                format_integer(summary.sessions),
                _delta(comparison.get("sessions_pct")),
            ),
            _card(
                "Total de tokens",
                format_integer(summary.total_tokens),
                _delta(comparison.get("total_tokens_pct")),
            ),
            _card("Tokens economizados", format_integer(summary.tokens_saved)),
            _card(
                "Taxa de cache",
                format_percentage(summary.cache_ratio),
                _delta(comparison.get("cache_ratio_pp"), points=True),
            ),
            _card(
                "Custo observado/reportado pela fonte",
                format_usd(summary.observed_cost_usd),
                _delta(comparison.get("observed_cost_usd_pct")),
            ),
            _card(
                "Economia estimada",
                format_usd(summary.total_savings_usd),
                _delta(comparison.get("total_savings_usd_pct")),
            ),
        ]
    )

    token_rows = [
        {
            "input_tokens": summary.input_tokens,
            "cached_input_tokens": summary.cached_input_tokens,
            "output_tokens": summary.output_tokens,
            "reasoning_output_tokens": summary.reasoning_output_tokens,
            "total_tokens": summary.total_tokens,
            "tokens_saved": summary.tokens_saved,
        }
    ]

    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Relatório AgentScope</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1180px;margin:0 auto;padding:28px;background:#f6f7f9;color:#16181d}}
h1,h2,h3,h4{{margin-top:1.2em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.card,.section,.chart{{background:white;border:1px solid #dde1e7;border-radius:10px;padding:16px;margin:12px 0}}
.card-label{{font-size:.86rem;color:#68707c;margin-bottom:6px}}
.value{{font-size:1.45rem;font-weight:700;font-variant-numeric:tabular-nums}}
.delta{{font-size:.78rem;color:#68707c;margin-top:6px}}
.muted{{color:#68707c}}
.period{{display:inline-block;background:#eef0f3;border-radius:6px;padding:5px 8px;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:white}}
th,td{{padding:8px 10px;border-bottom:1px solid #e7e9ed;text-align:left;font-size:.9rem}}
th{{background:#f0f2f5}}
.bar-row{{display:grid;grid-template-columns:180px 1fr 120px;gap:8px;align-items:center;margin:7px 0}}
.bar{{height:12px;background:#eceff3;border-radius:8px;overflow:hidden}}
.bar span{{display:block;height:100%;background:#5d6b82}}
.bar-value{{text-align:right;font-variant-numeric:tabular-nums}}
code{{background:#eef0f3;padding:2px 5px;border-radius:4px}}
</style>
</head>
<body>
<h1>AgentScope</h1>
<p class="muted">Análise local de execução. O relatório seguro exclui corpos de mensagens e payloads de ferramentas.</p>
<section class="section">
<h2>Resumo executivo</h2>
<p><strong>Período:</strong> <span class="period">{escape(_period_label(active_filters))}</span></p>
<div class="grid">{cards}</div>
</section>
<section class="section"><h2>Tokens</h2>{_table(token_rows)}</section>
<section class="section"><h2>Cache</h2><p>Taxa de cache: <strong>{format_percentage(summary.cache_ratio)}</strong></p></section>
<section class="section">
<h2>Custos</h2>
<p>Custo estimado bruto: <strong>{format_usd(summary.estimated_raw_cost_usd)}</strong></p>
<p>Custo observado/reportado pela fonte: <strong>{format_usd(summary.observed_cost_usd)}</strong></p>
{_bar_chart('Custo por dia', cost_day, 'day', 'observed_cost_usd')}
</section>
<section class="section">
<h2>Economia</h2>
<p>Compressão: <strong>{format_usd(summary.compression_savings_usd)}</strong> · Cache: <strong>{format_usd(summary.cache_savings_usd)}</strong> · Economia estimada: <strong>{format_usd(summary.total_savings_usd)}</strong></p>
{_bar_chart('Economia por dia', savings_day, 'day', 'compression_savings_usd')}
</section>
<section class="section"><h2>Modelos</h2>{_table(models)}{_bar_chart('Distribuição por modelo', models, 'model', 'input_tokens')}</section>
<section class="section"><h2>Projetos</h2>{_table(projects)}{_bar_chart('Distribuição por projeto', projects, 'project', 'input_tokens')}</section>
<section class="section"><h2>Usuários</h2>{_table(users)}{_bar_chart('Tokens por usuário', users, 'user', 'input_tokens')}</section>
<section class="section"><h2>Máquinas</h2>{_table(machines)}{_bar_chart('Tokens por máquina', machines, 'machine', 'input_tokens')}</section>
<section class="section"><h2>Agentes</h2>{_table(agents)}</section>
<section class="section"><h2>Habilidades</h2>{_table(skills)}</section>
<section class="section"><h2>Ferramentas / MCPs</h2>{_table(tools)}</section>
<section class="section"><h2>Otimizadores</h2>{_table(optimizers)}</section>
<section class="section"><h2>Tendências temporais</h2>{_bar_chart('Tokens por dia', by_day, 'day', 'input_tokens')}{_table(by_day)}</section>
{_quality_section(quality)}
</body>
</html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
