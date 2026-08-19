from datetime import date

from agentscope.analytics.budget import calculate_budget_status


def test_no_budget_returns_no_status():
    assert calculate_budget_status(None, 10.0, date(2026, 8, 15)) is None


def test_budget_without_observed_cost_preserves_unavailable_spend():
    status = calculate_budget_status(100.0, None, date(2026, 8, 15))

    assert status is not None
    assert status.budget_usd == 100.0
    assert status.observed_spend_usd is None
    assert status.consumed_ratio is None
    assert status.projected_end_of_month_usd is None
    assert status.days_elapsed == 15
    assert status.days_in_month == 31


def test_budget_consumption_and_projection_use_elapsed_month_average():
    status = calculate_budget_status(100.0, 50.0, date(2026, 8, 15))

    assert status is not None
    assert status.consumed_ratio == 0.5
    assert status.projected_end_of_month_usd == 50.0 / 15 * 31
    assert status.days_elapsed == 15
    assert status.days_in_month == 31
