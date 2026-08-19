# AgentScope Team Analytics/Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggregate imported team telemetry by user, machine, project, source, model, period, costs, savings, and cache, with optional budget consumption/projection.

**Architecture:** Reuse the normalized database and shared `AnalyticsFilter`. Team-specific analytics add user/machine/team dimensions and budget calculations; the HTML report consumes those methods without interpreting token volume as productivity.

**Tech Stack:** Python 3.11+, sqlite3, dataclasses, datetime, Typer, pytest, standard-library HTML.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment G.

## Global Constraints

- Token volume must never be labeled productivity/performance.
- Observed/source-reported cost, estimated cost, and unavailable values remain distinct.
- Team report obeys the same date/dimension filter object as local analytics.
- Budget is optional and is not treated as a billing fact.
- Projection is a simple elapsed-period average and must be labeled as projection.
- TDD is required.

---

### Task 1: Team analytics summary and dimensions

**Files:**
- Create: `src/agentscope/analytics/team_service.py`
- Create: `tests/unit/test_team_analytics.py`

**Interfaces:**
- `TeamAnalyticsSummary(users: int, machines: int, sessions: int, input_tokens: int, cached_input_tokens: int, output_tokens: int, total_tokens: int, observed_cost_usd: float|None, estimated_raw_cost_usd: float|None, total_savings_usd: float|None)`
- `TeamAnalyticsService(repository: Repository, filters: AnalyticsFilter|None=None)`
- Methods: `summary()`, `by_user()`, `by_machine()`, `by_project()`, `by_source()`, `by_model()`, `by_day()`.

- [ ] Write RED tests importing two synthetic team bundles from different users/machines.
- [ ] Assert user/machine counts and token aggregation by each dimension.
- [ ] Implement parameterized SQL over normalized tables.
- [ ] Preserve nullable cost semantics.
- [ ] Run tests and commit.

### Task 2: Cost and savings attribution by dimension

**Files:**
- Modify: `src/agentscope/analytics/team_service.py`
- Modify: `tests/unit/test_team_analytics.py`

**Interfaces:**
- Add `cost_by_user()`, `cost_by_project()`, `cost_by_source()`, `cost_by_model()`.
- Add `savings_by_user()`, `savings_by_project()`, `savings_by_source()`, `savings_by_model()`.

- [ ] Write RED tests where one source has observed cost, another only estimated cost, and another none.
- [ ] Ensure group rows expose separate columns rather than summing observed+estimated into one ambiguous value.
- [ ] Implement joins using session/source/user/project/model relations and optimization provenance.
- [ ] Run tests and commit.

### Task 3: Budget configuration and projection

**Files:**
- Modify: `src/agentscope/config.py`
- Create: `src/agentscope/analytics/budget.py`
- Modify: `tests/unit/test_config.py`
- Create: `tests/unit/test_budget.py`

**Interfaces:**
- Config adds `monthly_budget_usd: float|None` from `AGENTSCOPE_MONTHLY_BUDGET_USD`.
- `BudgetStatus(budget_usd, observed_spend_usd, consumed_ratio, projected_end_of_month_usd, days_elapsed, days_in_month)`.
- `calculate_budget_status(budget_usd: float|None, observed_spend_usd: float|None, as_of: date) -> BudgetStatus|None`.

- [ ] Write RED tests for no budget/no cost, 50% consumption, and month projection.
- [ ] Implement projection: `observed_spend / days_elapsed * days_in_month` when inputs are available.
- [ ] Reject negative budget configuration with clear error.
- [ ] Run tests and commit.

### Task 4: Team HTML report

**Files:**
- Create: `src/agentscope/reporting/team_html_report.py`
- Create: `tests/unit/test_team_reporting.py`

**Interfaces:**
- `generate_team_html_report(repository, analytics: TeamAnalyticsService, output: Path, budget: BudgetStatus|None=None) -> Path`.

- [ ] Write RED assertions for `Resumo da equipe`, `Desenvolvedores`, `Máquinas`, `Tokens`, `Cache`, `Custos`, `Economia`, `Por usuário`, `Por projeto`, `Por fonte`, `Por modelo`, `Tendência diária`, `Qualidade dos dados`.
- [ ] Assert pt-BR numeric/money formatting from shared formatters.
- [ ] Assert report contains disclaimer that token volume is usage, not productivity/performance.
- [ ] Render optional budget card only when configured.
- [ ] Run tests and commit.

### Task 5: Team data-quality coverage

**Files:**
- Modify: `src/agentscope/analytics/team_service.py`
- Modify: `src/agentscope/reporting/team_html_report.py`
- Modify: `tests/unit/test_team_analytics.py`
- Modify: `tests/unit/test_team_reporting.py`

**Interfaces:**
- `data_quality()` reports identity confidence distribution, unknown model share, sources with missing cost/token/cache capability, import errors, unsupported provider diagnostics, and optimization correlation confidence.

- [ ] Write RED quality-metric tests.
- [ ] Implement SQL/capability aggregation.
- [ ] Render unavailable coverage explicitly, never as zero.
- [ ] Run tests and commit.

### Task 6: Add team report CLI and filters

**Files:**
- Modify: `src/agentscope/cli.py`
- Modify: `tests/integration/test_cli_flow.py`

**Interfaces:**
- `agentscope team report --database <db> --output <html>` with shared options `--from`, `--to`, `--period`, `--project`, `--model`, `--source`, `--user`, `--machine`.
- Optional `--monthly-budget-usd` overrides config for that invocation.

- [ ] Write RED CLI integration test after importing two bundles.
- [ ] Implement command using `TeamAnalyticsService`, shared filter builder, shared formatting/budget logic.
- [ ] Run integration tests and commit.

### Task 7: Full team end-to-end acceptance test

**Files:**
- Create: `tests/integration/test_team_report_flow.py`

- [ ] Build two local synthetic databases representing two developers/machines.
- [ ] Export sanitized bundles from each.
- [ ] Import both into one fresh team database.
- [ ] Generate team report for all history and one filtered period/user.
- [ ] Assert totals equal sum of safe source metrics, costs remain semantically separate, no privacy sentinel leaks, and duplicate reimport leaves report totals unchanged.
- [ ] Run targeted test and commit.

### Task 8: Documentation and complete V2 verification

**Files:**
- Modify: `README.md`
- Create: `docs/team-analytics.md`
- Modify: `docs/provider-support.md`

- [ ] Document team workflow: local collect -> team export -> transfer bundle -> team import -> team report.
- [ ] Document per-user/project/source/model metrics, budget semantics, limitations, and privacy.
- [ ] Run `python -m pytest -q`.
- [ ] Generate a complete synthetic team report and inspect it.
- [ ] Verify GitHub Actions on supported Python versions.
- [ ] Update Issue #4 checklist only for items proven complete.
- [ ] Commit docs and fresh verification.
