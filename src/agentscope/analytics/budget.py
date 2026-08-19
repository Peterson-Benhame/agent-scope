from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    budget_usd: float
    observed_spend_usd: float | None
    consumed_ratio: float | None
    projected_end_of_month_usd: float | None
    days_elapsed: int
    days_in_month: int


def calculate_budget_status(
    budget_usd: float | None,
    observed_spend_usd: float | None,
    as_of: date,
) -> BudgetStatus | None:
    if budget_usd is None:
        return None
    if budget_usd < 0:
        raise ValueError("monthly budget must be non-negative")

    days_elapsed = as_of.day
    days_in_month = calendar.monthrange(as_of.year, as_of.month)[1]
    consumed_ratio = None
    projected = None

    if observed_spend_usd is not None:
        if budget_usd > 0:
            consumed_ratio = observed_spend_usd / budget_usd
        projected = observed_spend_usd / days_elapsed * days_in_month

    return BudgetStatus(
        budget_usd=float(budget_usd),
        observed_spend_usd=(
            float(observed_spend_usd)
            if observed_spend_usd is not None
            else None
        ),
        consumed_ratio=consumed_ratio,
        projected_end_of_month_usd=projected,
        days_elapsed=days_elapsed,
        days_in_month=days_in_month,
    )
