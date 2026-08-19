# AgentScope Analytics/Report V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared analytics filters, date aliases, pt-BR formatting, period comparison, and a clearer HTML/CLI/export report foundation without changing V1 collection semantics.

**Architecture:** `AnalyticsFilter` is the single filter object consumed by analytics, reporting, exports, and CLI. SQL queries apply the same session/time/dimension predicates, while formatting is isolated in reporting helpers. Empty filters preserve current all-history behavior.

**Tech Stack:** Python 3.11+, sqlite3, dataclasses, datetime/zoneinfo, Typer, pytest, standard-library HTML/CSV/JSON.

**Spec:** `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` — Increment A.

## Global Constraints

- Sources remain read-only.
- Empty filters must preserve V1 all-history behavior.
- Date-only `--to` includes the full selected local day.
- Custom `--from/--to` overrides `--period`.
- Unknown monetary values remain `NULL`/unavailable, never zero.
- Summary money uses pt-BR display with two decimals; technical detail may retain extra precision.
- Standard reports remain safe metadata only.
- No user/machine filter implementation until Increment D; fields may exist on `AnalyticsFilter` as nullable forward-compatible dimensions.
- TDD is required for every task.

---

### Task 1: Shared AnalyticsFilter and period resolution

**Files:**
- Create: `src/agentscope/analytics/filters.py`
- Create: `tests/unit/test_analytics_filters.py`

**Interfaces:**
- Produces: `AnalyticsFilter(from_date: date|None, to_date: date|None, project: str|None, model: str|None, source: str|None, user: str|None, machine: str|None)`
- Produces: `resolve_period(period: str|None, from_date: date|None, to_date: date|None, today: date|None = None) -> AnalyticsFilter`
- Produces: `AnalyticsFilter.previous_period() -> AnalyticsFilter|None`

- [ ] **Step 1: Write failing tests for explicit ranges and aliases**

```python
from datetime import date
from agentscope.analytics.filters import AnalyticsFilter, resolve_period


def test_explicit_range_overrides_period():
    f = resolve_period("7d", date(2026, 8, 1), date(2026, 8, 18), today=date(2026, 8, 18))
    assert f.from_date == date(2026, 8, 1)
    assert f.to_date == date(2026, 8, 18)


def test_period_7d_is_inclusive():
    f = resolve_period("7d", None, None, today=date(2026, 8, 18))
    assert f.from_date == date(2026, 8, 12)
    assert f.to_date == date(2026, 8, 18)


def test_month_starts_on_first_day():
    f = resolve_period("month", None, None, today=date(2026, 8, 18))
    assert f.from_date == date(2026, 8, 1)
    assert f.to_date == date(2026, 8, 18)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/unit/test_analytics_filters.py -q`

Expected: FAIL because `agentscope.analytics.filters` does not exist.

- [ ] **Step 3: Implement the minimal filter model and aliases**

```python
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class AnalyticsFilter:
    from_date: date | None = None
    to_date: date | None = None
    project: str | None = None
    model: str | None = None
    source: str | None = None
    user: str | None = None
    machine: str | None = None

    def previous_period(self) -> "AnalyticsFilter | None":
        if self.from_date is None or self.to_date is None:
            return None
        days = (self.to_date - self.from_date).days + 1
        previous_to = self.from_date - timedelta(days=1)
        return replace(
            self,
            from_date=previous_to - timedelta(days=days - 1),
            to_date=previous_to,
        )


def resolve_period(period, from_date, to_date, today=None):
    today = today or date.today()
    if from_date is not None or to_date is not None:
        return AnalyticsFilter(from_date=from_date, to_date=to_date)
    if period is None:
        return AnalyticsFilter()
    if period == "today":
        return AnalyticsFilter(today, today)
    if period == "7d":
        return AnalyticsFilter(today - timedelta(days=6), today)
    if period == "30d":
        return AnalyticsFilter(today - timedelta(days=29), today)
    if period == "month":
        return AnalyticsFilter(today.replace(day=1), today)
    raise ValueError(f"Unsupported period: {period}")
```

- [ ] **Step 4: Add previous-period boundary tests and verify GREEN**

Run: `python -m pytest tests/unit/test_analytics_filters.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentscope/analytics/filters.py tests/unit/test_analytics_filters.py
git commit -m "feat: add analytics filters and periods"
```

### Task 2: Apply filters consistently to analytics SQL

**Files:**
- Modify: `src/agentscope/analytics/service.py`
- Modify: `tests/unit/test_analytics.py`

**Interfaces:**
- Consumes: `AnalyticsFilter`
- Changes constructor to: `AnalyticsService(repository: Repository, filters: AnalyticsFilter | None = None)`
- Produces: `summary()`, `by_project()`, `by_model()`, `by_agent()`, `by_skill()`, `by_tool()`, `by_day()`, `optimizer_summary()`, `savings_by_day()`, `cost_by_day()` respecting the active filter.
- Produces: `comparison() -> dict[str, float|int|None] | None` using the previous equivalent period.

- [ ] **Step 1: Write failing filtered-summary test**

Extend fixture data in the test database with one token event on `2026-08-17` and assert a filter for `2026-08-18` excludes it:

```python
analytics = AnalyticsService(
    repo,
    AnalyticsFilter(from_date=date(2026, 8, 18), to_date=date(2026, 8, 18)),
)
summary = analytics.summary()
assert summary.input_tokens == 18019
```

Also test `project`, `model`, and `source` predicates against the synthetic fixture.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/unit/test_analytics.py -q`

Expected: FAIL because `AnalyticsService` does not accept filters.

- [ ] **Step 3: Implement parameterized WHERE helpers**

Add private helpers that return SQL fragments and parameters. Date predicates use `substr(timestamp, 1, 10)` for event tables and `substr(s.started_at, 1, 10)` for session counts. Project/model/source predicates join normalized tables rather than parsing paths.

```python
def _date_bounds(self, column: str) -> tuple[list[str], list[object]]:
    clauses, params = [], []
    if self.filters.from_date:
        clauses.append(f"substr({column}, 1, 10) >= ?")
        params.append(self.filters.from_date.isoformat())
    if self.filters.to_date:
        clauses.append(f"substr({column}, 1, 10) <= ?")
        params.append(self.filters.to_date.isoformat())
    return clauses, params
```

Dimension predicates must use bound parameters only.

- [ ] **Step 4: Add comparison test**

Create equal-length current/previous periods and assert `comparison()` returns deltas for at least sessions, total_tokens, cache_ratio, observed_cost_usd, and total_savings_usd. If no bounded period is selected, assert `comparison() is None`.

- [ ] **Step 5: Run targeted analytics tests**

Run: `python -m pytest tests/unit/test_analytics.py tests/unit/test_analytics_filters.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agentscope/analytics/service.py tests/unit/test_analytics.py
git commit -m "feat: filter analytics by period and dimensions"
```

### Task 3: Centralized pt-BR formatting

**Files:**
- Create: `src/agentscope/reporting/formatters.py`
- Create: `tests/unit/test_formatters.py`

**Interfaces:**
- Produces: `format_integer(value: int|None) -> str`
- Produces: `format_decimal(value: float|None, decimals: int = 2) -> str`
- Produces: `format_percentage(value: float|None, decimals: int = 2) -> str`
- Produces: `format_usd(value: float|None, decimals: int = 2) -> str`

- [ ] **Step 1: Write failing locale-format tests**

```python
assert format_integer(1465312344) == "1.465.312.344"
assert format_decimal(4.3144, 4) == "4,3144"
assert format_percentage(0.9463) == "94,63%"
assert format_usd(13.777432) == "US$ 13,78"
assert format_usd(None) == "Não disponível"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/unit/test_formatters.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement formatting without process-global locale state**

Use Python numeric formatting and separator swapping; do not call `locale.setlocale`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/unit/test_formatters.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agentscope/reporting/formatters.py tests/unit/test_formatters.py
git commit -m "feat: add pt-br report formatting"
```

### Task 4: Report V2 summary, terminology, and period comparison

**Files:**
- Modify: `src/agentscope/reporting/html_report.py`
- Modify: `tests/unit/test_reporting.py`

**Interfaces:**
- Changes: `generate_html_report(repository, analytics, output, filters: AnalyticsFilter | None = None) -> Path`
- Consumes centralized formatters and `analytics.comparison()`.

- [ ] **Step 1: Write failing HTML assertions**

Assert the report contains:

```text
Resumo executivo
Período
Total de tokens
Tokens economizados
Taxa de cache
Custo observado/reportado pela fonte
Economia estimada
US$ 0,08
95,19%
```

For all-history reports, period label must be `Todo o histórico`. For bounded filters, display `18/08/2026 a 18/08/2026`. Existing privacy assertions for prompt/tool-output sentinels remain.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/unit/test_reporting.py -q`

Expected: FAIL on new labels/formatting.

- [ ] **Step 3: Replace inline `_money`/`_num` formatting with centralized helpers**

Update headings to Portuguese terminology, add cache ratio to executive cards, and render previous-period percentage/delta only when `comparison()` is available. Keep observed/source-reported and estimated semantics visually distinct.

- [ ] **Step 4: Keep technical tables precise where required**

Summary USD uses two decimals. Detailed optimizer/cost rows may use four to six decimals through `format_decimal`/`format_usd(..., decimals=4|6)` where small values would otherwise round to zero.

- [ ] **Step 5: Run reporting tests**

Run: `python -m pytest tests/unit/test_reporting.py tests/unit/test_formatters.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agentscope/reporting/html_report.py tests/unit/test_reporting.py
git commit -m "feat: improve analytics html report"
```

### Task 5: Filtered exports and CLI options

**Files:**
- Modify: `src/agentscope/reporting/export.py`
- Modify: `src/agentscope/cli.py`
- Modify: `tests/integration/test_cli_flow.py`
- Modify: `tests/unit/test_reporting.py`

**Interfaces:**
- Changes: `export_datasets(..., filters: AnalyticsFilter | None = None, include_content: bool = False)`
- CLI options on `analyze`, `export`, `report`: `--from`, `--to`, `--period`, `--project`, `--model`, `--source`.
- `--from/--to` parse ISO `YYYY-MM-DD`; invalid values exit non-zero with a clear message.

- [ ] **Step 1: Write failing CLI integration tests**

```python
result = runner.invoke(app, [
    "report", "--database", str(db), "--output", str(report_path),
    "--from", "2026-08-18", "--to", "2026-08-18",
])
assert result.exit_code == 0
assert "18/08/2026" in report_path.read_text(encoding="utf-8")
```

Add `analyze --period 7d` and `export --project demo` coverage. Add an invalid `--period 90d` assertion that exits non-zero.

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/integration/test_cli_flow.py -q`

Expected: FAIL because the options do not exist.

- [ ] **Step 3: Add one CLI filter builder**

Create a private `_analytics_filter(...)` helper in `cli.py` that parses dates once and is reused by all three commands. Do not duplicate period logic in command handlers.

- [ ] **Step 4: Apply filters to safe exports**

Replace raw unfiltered export queries with parameterized queries constrained by the same session/event predicates. `messages_full.json` remains opt-in and must also obey the selected filters.

- [ ] **Step 5: Run CLI/reporting regression suite**

Run: `python -m pytest tests/integration/test_cli_flow.py tests/unit/test_reporting.py tests/unit/test_analytics.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agentscope/cli.py src/agentscope/reporting/export.py tests/integration/test_cli_flow.py tests/unit/test_reporting.py
git commit -m "feat: expose analytics filters in cli"
```

### Task 6: Documentation and full Increment A verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md` only to mark Increment A implementation status if the project convention uses status tracking.

- [ ] **Step 1: Document commands**

Add exact examples:

```powershell
agentscope report --period today
agentscope report --period 7d
agentscope report --from 2026-08-01 --to 2026-08-18
agentscope analyze --project example-project --period 30d
agentscope export --model gpt-5.6-terra --period month
```

Document that `--from/--to` overrides `--period`, dates are inclusive, empty filters mean all history, and money in the UI is display-formatted without changing stored precision.

- [ ] **Step 2: Run the complete test suite**

Run: `python -m pytest -q`

Expected: all tests PASS.

- [ ] **Step 3: Run a smoke flow against synthetic fixtures/fresh database**

Run collection, filtered report, filtered export, and all-history report. Verify no prompt/tool-output sentinel appears in safe outputs.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md docs/superpowers/specs/2026-08-18-multi-source-team-analytics-design.md
git commit -m "docs: document analytics report filters"
```

- [ ] **Step 5: Fresh final verification**

Run: `python -m pytest -q`

Expected: all tests PASS with a fresh result immediately before review/publication.
