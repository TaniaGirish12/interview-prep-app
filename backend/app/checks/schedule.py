"""Study time available before an interview. Computed here, not by the LLM; the
study plan builds on these numbers."""

from datetime import date, datetime, time

# An interview at or after this time leaves the morning for a short review.
MORNING_REVIEW_FROM = time(13, 0)
MORNING_REVIEW_MAX_HOURS = 2.0


def study_budget(interview_date: date, interview_time: time | None, hours_per_day: float | None,
                 now: datetime) -> dict:
    """Study days run from today up to the day before the interview; today counts
    as a full day. With an afternoon interview, the interview morning adds a short
    review (at most 2 hours, never more than the daily hours)."""
    today = now.date()
    days_until = (interview_date - today).days
    hours_until = None
    if interview_time is not None:
        hours_until = round((datetime.combine(interview_date, interview_time) - now).total_seconds() / 3600, 1)

    past = days_until < 0 or (hours_until is not None and hours_until <= 0)
    study_days = max(days_until, 0) if not past else 0
    review_hours = 0.0
    if not past and interview_time is not None and interview_time >= MORNING_REVIEW_FROM and hours_per_day:
        review_hours = min(hours_per_day, MORNING_REVIEW_MAX_HOURS)
    total_hours = round(study_days * hours_per_day + review_hours, 1) if hours_per_day else None

    return {
        "days_until": days_until,
        "hours_until": hours_until,
        "past": past,
        "study_days": study_days,
        "review_hours": review_hours,
        "total_hours": total_hours,
    }
