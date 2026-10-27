"""Spaced repetition: a simplified SM-2 with Again / Hard / Good / Easy.

- Again: the card resets (reps 0, lapses + 1), ease drops by 0.2, and it is due
  again today, so it comes back later in the same session.
- Hard: interval × 1.2 (at least 1 day), ease drops by 0.15.
- Good: 1 day, then 3 days, then interval × ease.
- Easy: 3 days for a new card, else interval × ease × 1.3; ease rises by 0.15.
Ease never falls below 1.3. Nothing is scheduled on or after the interview day:
the due date is capped at the day before, so every card is seen again in time.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Grade = Literal["again", "hard", "good", "easy"]
MIN_EASE = 1.3


@dataclass
class CardState:
    ease: float = 2.5
    interval_days: int = 0
    reps: int = 0
    lapses: int = 0


def review(state: CardState, grade: Grade, today: date, interview: date | None = None) -> tuple[CardState, date]:
    ease, interval, reps, lapses = state.ease, state.interval_days, state.reps, state.lapses
    if grade == "again":
        reps, lapses, interval = 0, lapses + 1, 0
        ease = max(MIN_EASE, ease - 0.2)
    else:
        if grade == "hard":
            interval = max(1, round(max(interval, 1) * 1.2))
            ease = max(MIN_EASE, ease - 0.15)
        elif grade == "good":
            interval = 1 if reps == 0 else 3 if reps == 1 else round(interval * ease)
        else:  # easy
            interval = 3 if reps == 0 else round(max(interval, 1) * ease * 1.3)
            ease += 0.15
        reps += 1
    due = today + timedelta(days=interval)
    if interview is not None and interview > today:
        due = min(due, interview - timedelta(days=1))
    return CardState(round(ease, 2), interval, reps, lapses), due
