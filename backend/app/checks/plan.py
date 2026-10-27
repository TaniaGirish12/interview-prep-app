"""Day-by-day study plan, built deterministically in Python (no LLM call).

Inputs: the study-next ranking (tier × gap × confidence), the optional gap learning
plan (its steps and hour estimates), hours already logged as done, and the study
budget (days until the interview, hours per day, interview time).

Rules:
- Time is planned in half-hour units.
- Requirements are taken in study-next order. Partial matches and gaps get a learn
  phase and a practise phase; strong matches get one short review at the end.
- Learn hours come from the gap plan when it exists, otherwise from a default
  estimate by status and tier.
- Each requirement that was learned gets a 30-minute spaced review two days later,
  if there is room.
- With three or more study days, the last study day keeps 1 hour for a final review
  of tier 1 likely questions. An afternoon interview gets a morning warm-up.
- Hours already logged count against a requirement's needs; anything that does not
  fit before the interview is listed as unscheduled, never silently dropped.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

UNIT = 0.5  # hours

# Default hours when there is no gap plan for a requirement.
BASE_HOURS = {"gap": 4.0, "partial": 2.0}
TIER_SCALE = {1: 1.0, 2: 0.75, 3: 0.5, 4: 0.25}
LEARN_SHARE = 0.6
STRONG_REVIEW_HOURS = {1: 1.0, 2: 0.5, 3: 0.5, 4: 0.5}
SPACED_REVIEW_HOURS = 0.5
SPACED_REVIEW_AFTER_DAYS = 2
FINAL_REVIEW_HOURS = 1.0

PRACTISE_LABEL = "Practise: answer the likely questions out loud and work through the code examples"
LEARN_LABEL = "Learn: read the topic notes from fundamentals to interview level"
STRONG_LABEL = "Review: refresh the notes and connect them to your resume evidence"
SPACED_LABEL = "Spaced review: re-answer the likely questions without notes"


def _units(hours: float) -> int:
    return max(1, round(hours / UNIT))


@dataclass
class Task:
    jd_id: str
    name: str
    tier: int
    status: str
    kind: str  # learn | practise | review
    units: int
    label: str


@dataclass
class Block:
    id: str
    jd_id: str | None
    name: str
    tier: int | None
    status: str | None
    kind: str  # learn | practise | review | final
    hours: float
    label: str


@dataclass
class Day:
    date: str
    capacity_units: int
    interview_day: bool = False
    blocks: list[Block] = field(default_factory=list)

    @property
    def used_units(self) -> int:
        return sum(_units(b.hours) for b in self.blocks)

    @property
    def free_units(self) -> int:
        return self.capacity_units - self.used_units


def build_tasks(study_next: list[dict], gap_plans: dict[str, list[dict]], done_units: dict[tuple[str, str], int]) -> list[Task]:
    """Tasks in priority order, with hours already done subtracted."""
    tasks: list[Task] = []
    active = [r for r in study_next if r["status"] != "strong"]
    strong = [r for r in study_next if r["status"] == "strong"]
    for row in active:
        steps = gap_plans.get(row["jd_id"])
        if steps:
            learn = [(_units(s["est_hours"]), f"Learn: {s['what']}") for s in sorted(steps, key=lambda s: s["order"])]
            total = sum(u for u, _ in learn)
            practise = max(1, round(total * (1 - LEARN_SHARE) / LEARN_SHARE))
        else:
            total = _units(BASE_HOURS[row["status"]] * TIER_SCALE[row["tier"]])
            learn_units = max(1, round(total * LEARN_SHARE))
            learn = [(learn_units, LEARN_LABEL)]
            practise = max(1, total - learn_units)
        for kind, parts in (("learn", learn), ("practise", [(practise, PRACTISE_LABEL)])):
            remaining_done = done_units.get((row["jd_id"], kind), 0)
            for units, label in parts:
                cut = min(units, remaining_done)
                remaining_done -= cut
                if units - cut > 0:
                    tasks.append(Task(row["jd_id"], row["name"], row["tier"], row["status"], kind, units - cut, label))
    for row in strong:
        units = _units(STRONG_REVIEW_HOURS[row["tier"]]) - done_units.get((row["jd_id"], "review"), 0)
        if units > 0:
            tasks.append(Task(row["jd_id"], row["name"], row["tier"], row["status"], "review", units, STRONG_LABEL))
    return tasks


def build_plan(
    *,
    today: date,
    budget: dict | None,
    interview_date: date | None,
    hours_per_day: float | None,
    study_next: list[dict],
    gap_plans: dict[str, list[dict]],
    done_units: dict[tuple[str, str], int],
    done_today_units: int,
) -> dict:
    missing = [name for name, value in (("interview_date", interview_date), ("hours_per_day", hours_per_day)) if not value]
    tasks = build_tasks(study_next, gap_plans, done_units)
    needed_units = sum(t.units for t in tasks)
    base = {"missing": missing, "needed_hours": needed_units * UNIT, "days": [], "unscheduled": [],
            "available_hours": 0.0, "scheduled_hours": 0.0, "past": bool(budget and budget["past"])}
    if missing or budget is None or budget["past"]:
        base["unscheduled"] = _summarise(tasks)
        return base

    per_day = _units(hours_per_day)
    days = [Day((today + timedelta(days=i)).isoformat(), per_day) for i in range(budget["study_days"])]
    if days:
        days[0].capacity_units = max(0, per_day - done_today_units)
    if budget["review_hours"] > 0:
        days.append(Day(interview_date.isoformat(), _units(budget["review_hours"]), interview_day=True))
    counter = iter(range(1, 1_000_000))

    def add(day: Day, task_like: Task | None, kind: str, units: int, label: str) -> None:
        day.blocks.append(Block(
            id=f"{day.date}-{task_like.jd_id if task_like else 'all'}-{kind}-{next(counter)}",
            jd_id=task_like.jd_id if task_like else None, name=task_like.name if task_like else "Tier 1 topics",
            tier=task_like.tier if task_like else None, status=task_like.status if task_like else None,
            kind=kind, hours=units * UNIT, label=label,
        ))

    study_days = [d for d in days if not d.interview_day]
    # Reserve the end of the last study day for a final review.
    final_units = _units(FINAL_REVIEW_HOURS)
    final_day = study_days[-1] if len(study_days) >= 3 and study_days[-1].capacity_units > final_units else None
    if final_day:
        final_day.capacity_units -= final_units

    # Greedy fill in priority order; a task may be split across days.
    learned_on: dict[str, int] = {}
    leftovers: list[Task] = []
    i = 0
    for task in tasks:
        units = task.units
        while units > 0 and i < len(study_days):
            day = study_days[i]
            if day.free_units <= 0:
                i += 1
                continue
            take = min(units, day.free_units)
            add(day, task, task.kind, take, task.label)
            units -= take
            if task.kind == "learn":
                learned_on[task.jd_id] = i
        if units > 0:
            leftovers.append(Task(**{**asdict(task), "units": units}))

    # Spaced reviews go into whatever room is left, two or more days after learning.
    by_id = {t.jd_id: t for t in tasks}
    for jd_id, day_index in sorted(learned_on.items(), key=lambda kv: kv[1]):
        for day in study_days[day_index + SPACED_REVIEW_AFTER_DAYS:]:
            if day.free_units >= _units(SPACED_REVIEW_HOURS):
                add(day, by_id[jd_id], "review", _units(SPACED_REVIEW_HOURS), SPACED_LABEL)
                break

    if final_day:
        final_day.capacity_units += final_units
        add(final_day, None, "final", final_units,
            "Final review: answer the likely questions for every tier 1 topic out loud")
    for day in days:
        if day.interview_day:
            add(day, None, "final", day.capacity_units,
                "Warm-up: skim your tier 1 notes and rehearse two experience stories")

    available = sum(d.capacity_units for d in days)
    scheduled = sum(d.used_units for d in days)
    base.update(
        available_hours=available * UNIT,
        scheduled_hours=scheduled * UNIT,
        days=[{"date": d.date, "interview_day": d.interview_day, "capacity_hours": d.capacity_units * UNIT,
               "used_hours": d.used_units * UNIT, "blocks": [asdict(b) for b in d.blocks]} for d in days],
        unscheduled=_summarise(leftovers),
    )
    return base


def _summarise(tasks: list[Task]) -> list[dict]:
    """Remaining hours per requirement, in priority order."""
    out: dict[str, dict] = {}
    for t in tasks:
        row = out.setdefault(t.jd_id, {"jd_id": t.jd_id, "name": t.name, "tier": t.tier, "status": t.status, "hours": 0.0})
        row["hours"] += t.units * UNIT
    return list(out.values())
