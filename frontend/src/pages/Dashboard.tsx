import { Link } from "react-router-dom";
import { MatchRadar, TierStatusBars } from "../components/Charts";
import { ScheduleCard } from "../components/ScheduleCard";
import { IdChip, StatusBadge, TierBadge } from "../components/ui";
import type { TopicStatusT } from "../schemas";
import { useAnalysisCtx } from "./AnalysisLayout";

const TOPIC_LABEL: Record<TopicStatusT, string> = {
  ready: "Notes ready", queued: "Queued", generating: "Writing notes…", error: "Failed", not_started: "",
};

export function Dashboard() {
  const { analysis, result, id } = useAnalysisCtx();
  const { scores } = result;
  const studyNext = scores.study_next.filter((s) => s.priority > 0).slice(0, 8);
  const counts = scores.tier_status.reduce(
    (acc, r) => ({ strong: acc.strong + r.strong, partial: acc.partial + r.partial, gap: acc.gap + r.gap }),
    { strong: 0, partial: 0, gap: 0 },
  );

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="card p-5" aria-labelledby="score-h">
        <h2 id="score-h" className="font-semibold">Match score</h2>
        <p className="text-5xl font-bold tabular-nums mt-2">
          {scores.match_score === null ? "–" : `${Math.round(scores.match_score)}%`}
        </p>
        <p className="text-sm muted mt-2">
          Weighted by tier: {counts.strong} strong, {counts.partial} partial, {counts.gap} gaps across {result.jd_items.length} requirements.
        </p>
      </section>

      <ScheduleCard analysisId={id} interviewDate={analysis.interview_date} interviewTime={analysis.interview_time}
        hoursPerDay={analysis.hours_per_day} schedule={analysis.schedule} />

      <section className="card p-5 lg:row-span-2" aria-labelledby="next-h">
        <h2 id="next-h" className="font-semibold">Study next</h2>
        <p className="text-xs muted mb-3">Ranked by tier weight × how far you are from a strong match, boosted when confidence is low.</p>
        {studyNext.length ? (
          <ol className="space-y-2">
            {studyNext.map((s, i) => (
              <li key={s.jd_id}>
                <Link to={`topic/${s.jd_id}`}
                  className="flex gap-3 items-start rounded-lg p-2 hover:bg-[var(--surface-2)]">
                  <span className="tabular-nums muted w-5 text-right">{i + 1}.</span>
                  <span className="min-w-0 flex-1">
                    <span className="font-medium block">{s.name}</span>
                    <span className="flex flex-wrap gap-1.5 mt-1 items-center">
                      <IdChip id={s.jd_id} /><TierBadge tier={s.tier} /><StatusBadge status={s.status} />
                      {result.topics[s.jd_id] && result.topics[s.jd_id] !== "not_started" && (
                        <span className="text-xs muted">{TOPIC_LABEL[result.topics[s.jd_id]]}</span>
                      )}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm muted">Every requirement is a strong match. Review the topic notes for interview depth.</p>
        )}
        <Link to="matrix" className="text-sm underline mt-3 inline-block">All requirements →</Link>
      </section>

      <section className="card p-5 lg:col-span-1">
        <MatchRadar radar={scores.radar} />
      </section>
      <section className="card p-5 lg:col-span-1">
        <TierStatusBars rows={scores.tier_status} />
      </section>

      {(result.dropped.length > 0 || result.defaulted.rank.length > 0 || result.defaulted.match.length > 0) && (
        <section className="card p-5 lg:col-span-3" aria-labelledby="checks-h">
          <details>
            <summary id="checks-h" className="cursor-pointer font-semibold">
              Deterministic checks: {result.dropped.length} item(s) dropped
              {result.defaulted.match.length > 0 && `, ${result.defaulted.match.length} defaulted`}
            </summary>
            <p className="text-sm muted mt-2">
              Items are dropped when their quote cannot be found in the source text, or when they reference an ID that does not exist.
            </p>
            <ul className="mt-3 space-y-1 text-sm">
              {result.dropped.map((d, i) => (
                <li key={i} className="flex flex-wrap gap-2">
                  <span className="font-mono text-xs muted">{d.step}</span>
                  <span>{d.reason}:</span>
                  <span className="muted break-all">{String(d.item.quote ?? d.item.value ?? d.item.jd_id ?? JSON.stringify(d.item))}</span>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}
      <p className="text-xs muted lg:col-span-3">Analysis {id} · model {analysis.model}</p>
    </div>
  );
}
