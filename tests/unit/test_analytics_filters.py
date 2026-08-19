from datetime import date

from agentscope.analytics.filters import AnalyticsFilter, resolve_period


def test_explicit_range_overrides_period():
    filters = resolve_period(
        "7d",
        date(2026, 8, 1),
        date(2026, 8, 18),
        today=date(2026, 8, 18),
    )

    assert filters.from_date == date(2026, 8, 1)
    assert filters.to_date == date(2026, 8, 18)


def test_period_7d_is_inclusive():
    filters = resolve_period("7d", None, None, today=date(2026, 8, 18))

    assert filters.from_date == date(2026, 8, 12)
    assert filters.to_date == date(2026, 8, 18)


def test_period_30d_is_inclusive():
    filters = resolve_period("30d", None, None, today=date(2026, 8, 18))

    assert filters.from_date == date(2026, 7, 20)
    assert filters.to_date == date(2026, 8, 18)


def test_month_starts_on_first_day():
    filters = resolve_period("month", None, None, today=date(2026, 8, 18))

    assert filters.from_date == date(2026, 8, 1)
    assert filters.to_date == date(2026, 8, 18)


def test_today_selects_single_day():
    filters = resolve_period("today", None, None, today=date(2026, 8, 18))

    assert filters.from_date == date(2026, 8, 18)
    assert filters.to_date == date(2026, 8, 18)


def test_empty_period_preserves_all_history():
    filters = resolve_period(None, None, None, today=date(2026, 8, 18))

    assert filters == AnalyticsFilter()


def test_previous_period_uses_same_inclusive_length():
    filters = AnalyticsFilter(
        from_date=date(2026, 8, 12),
        to_date=date(2026, 8, 18),
        project="demo",
    )

    previous = filters.previous_period()

    assert previous is not None
    assert previous.from_date == date(2026, 8, 5)
    assert previous.to_date == date(2026, 8, 11)
    assert previous.project == "demo"


def test_unbounded_filter_has_no_previous_period():
    assert AnalyticsFilter().previous_period() is None
