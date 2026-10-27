"""Match score, radar and study-next ranking. Computed here, never by the LLM."""

from dataclasses import asdict, dataclass

from ..schemas import JDItem, Match, RankedRequirement

TIER_WEIGHT = {1: 4, 2: 3, 3: 2, 4: 1}
STATUS_VALUE = {"strong": 1.0, "partial": 0.5, "gap": 0.0}
LOW_CONFIDENCE_BOOST = 0.5


@dataclass
class StudyNext:
    jd_id: str
    name: str
    tier: int
    status: str
    confidence: float
    priority: float


def weighted_score(pairs: list[tuple[int, str]]) -> float | None:
    """Weighted average of status values, as a 0–100 percentage."""
    total = sum(TIER_WEIGHT[t] for t, _ in pairs)
    if not total:
        return None
    return round(100 * sum(TIER_WEIGHT[t] * STATUS_VALUE[s] for t, s in pairs) / total, 1)


def priority(tier: int, status: str, confidence: float, boost: float = 1.0) -> float:
    base = TIER_WEIGHT[tier] * (1 - STATUS_VALUE[status])
    return round(base * (1 + LOW_CONFIDENCE_BOOST * (1 - confidence)) * boost, 3)


def compute_scores(
    jd_items: list[JDItem],
    rankings: dict[str, RankedRequirement],
    matches: dict[str, Match],
    skill_areas: list[str],
    boosts: dict[str, float] | None = None,
) -> dict:
    boosts = boosts or {}
    pairs = [(rankings[i.id].tier, matches[i.id].status) for i in jd_items]
    by_area: dict[str, list[tuple[int, str]]] = {a: [] for a in skill_areas}
    for i in jd_items:
        by_area.setdefault(rankings[i.id].skill_area, []).append((rankings[i.id].tier, matches[i.id].status))

    tier_status = {t: {"strong": 0, "partial": 0, "gap": 0} for t in (1, 2, 3, 4)}
    for t, s in pairs:
        tier_status[t][s] += 1

    study = [
        StudyNext(
            jd_id=i.id, name=i.name, tier=rankings[i.id].tier, status=matches[i.id].status,
            confidence=matches[i.id].confidence,
            priority=priority(rankings[i.id].tier, matches[i.id].status, matches[i.id].confidence,
                              boosts.get(i.id, 1.0)),
        )
        for i in jd_items
    ]
    # Strong matches with full confidence score 0; still listed last so the order is total.
    study.sort(key=lambda s: (-s.priority, s.tier, s.jd_id))

    return {
        "match_score": weighted_score(pairs),
        "radar": [{"area": a, "score": weighted_score(p) or 0.0, "count": len(p)} for a, p in by_area.items() if p],
        "tier_status": [{"tier": t, **c} for t, c in tier_status.items()],
        "study_next": [asdict(s) for s in study],
    }
