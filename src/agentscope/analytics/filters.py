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
        previous_from = previous_to - timedelta(days=days - 1)
        return replace(self, from_date=previous_from, to_date=previous_to)


def resolve_period(
    period: str | None,
    from_date: date | None,
    to_date: date | None,
    *,
    today: date | None = None,
) -> AnalyticsFilter:
    current_day = today or date.today()

    if from_date is not None or to_date is not None:
        return AnalyticsFilter(from_date=from_date, to_date=to_date)

    if period is None:
        return AnalyticsFilter()
    if period == "today":
        return AnalyticsFilter(from_date=current_day, to_date=current_day)
    if period == "7d":
        return AnalyticsFilter(
            from_date=current_day - timedelta(days=6),
            to_date=current_day,
        )
    if period == "30d":
        return AnalyticsFilter(
            from_date=current_day - timedelta(days=29),
            to_date=current_day,
        )
    if period == "month":
        return AnalyticsFilter(
            from_date=current_day.replace(day=1),
            to_date=current_day,
        )

    raise ValueError(f"Unsupported period: {period}")
