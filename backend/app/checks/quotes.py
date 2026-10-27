"""Quote verification: every quoted line must actually appear in its source."""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, TypeVar

from ..schemas import Evidence, Match, MatchLLM
from .normalize import contains, normalize

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class Dropped:
    step: str
    reason: str
    item: dict[str, Any]


@dataclass
class CheckResult:
    kept: list = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)


def verify_quotes(
    items: Sequence[T], source: str, step: str, get_quote: Callable[[T], str] = lambda i: i.quote
) -> CheckResult:
    src = normalize(source)
    result = CheckResult()
    for item in items:
        if contains(src, get_quote(item)):
            result.kept.append(item)
        else:
            d = Dropped(step, "quote not found in source", _dump(item))
            log.warning("Dropped %s item: %s", step, d.item)
            result.dropped.append(d)
    return result


def verify_match_evidence(
    matches: Sequence[MatchLLM], resume_text: str, cv_quotes: dict[str, str]
) -> tuple[list[Match], list[Dropped]]:
    """Each evidence quote must be in the resume AND inside the quote of the CV item it cites.
    A strong/partial match that loses all of its evidence is downgraded to gap."""
    src = normalize(resume_text)
    out: list[Match] = []
    dropped: list[Dropped] = []
    for m in matches:
        good: list[Evidence] = []
        for ev in m.evidence:
            cv_quote = cv_quotes.get(ev.cv_id)
            if cv_quote is None:
                reason = f"unknown CV id {ev.cv_id}"
            elif not contains(src, ev.quote):
                reason = "evidence quote not found in resume"
            elif not (contains(normalize(cv_quote), ev.quote) or contains(normalize(ev.quote), cv_quote)):
                reason = f"evidence quote is not part of {ev.cv_id}"
            else:
                good.append(ev)
                continue
            d = Dropped("matching", reason, {"jd_id": m.jd_id, **ev.model_dump()})
            log.warning("Dropped evidence: %s", d.item)
            dropped.append(d)
        downgraded = m.status != "gap" and not good
        out.append(Match(
            jd_id=m.jd_id,
            status="gap" if downgraded else m.status,
            evidence=good,
            rationale=m.rationale,
            confidence=m.confidence,
            downgraded=downgraded,
        ))
    return out, dropped


def _dump(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return item
    return {"value": item}
