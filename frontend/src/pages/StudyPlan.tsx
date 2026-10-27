import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import { ScheduleCard } from "../components/ScheduleCard";
import { ErrorState, IdChip, LoadingState, StatusBadge, TierBadge } from "../components/ui";
import type { PlanBlockT, StudyPlanT } from "../schemas";
import { useAnalysisCtx } from "./AnalysisLayout";

const KIND_LABEL: Record<PlanBlockT["kind"], string> = {
  learn: "Learn", practise: "Practise", review: "Review", final: "Final review",
};

const hours = (h: number) => `${Number.isInteger(h) ? h : h.toFixed(1)} h`;

function dayTitle(iso: string, today: string, interviewDay: boolean) {
  const [y, m, d] = iso.split("-").map(Number);
  const label = new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  if (interviewDay) return `Interview day · ${label}`;
  return iso === today ? `Today · ${label}` : label;
}

function useDone(analysisId: number) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.plan(analysisId) });
  };
  const mark = useMutation({
    mutationFn: (b: PlanBlockT) => api.markDone(analysisId, { jd_id: b.jd_id, kind: b.kind, hours: b.hours }),
    onSuccess: refresh,
  });
  const undo = useMutation({ mutationFn: (entryId: number) => api.undoDone(analysisId, entryId), onSuccess: refresh });
  return { mark, undo };
}

function Summary({ plan }: { plan: StudyPlanT }) {
  const short = plan.needed_hours - plan.scheduled_hours;
  const spare = plan.available_hours - plan.scheduled_hours;
  const studyDays = plan.days.filter((d) => !d.interview_day).length;
  const stats = [
    ["Study days", String(studyDays)],
    ["Time left", hours(plan.available_hours)],
    ["Still to study", hours(plan.needed_hours)],
    ["Done so far", hours(plan.done_hours_total)],
  ];
  return (
    <section className="card p-5 space-y-3" aria-label="Plan summary">
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {stats.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs muted">{k}</dt>
            <dd className="text-2xl font-bold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      {short > 0 ? (
        <p className="text-sm rounded-lg p-3" style={{ background: "var(--partial-bg)" }}>
          <strong>Not everything fits.</strong> {hours(short)} of lower-priority study is listed under "Not
          scheduled". Add more hours per day to fit more in.
        </p>
      ) : spare > 0 ? (
        <p className="text-sm muted">
          Everything fits, with {hours(spare)} to spare. Use free time for extra practice on tier 1 topics.
        </p>
      ) : null}
      <p className="text-xs muted">
        Built from your tiers, gaps and match confidence, highest priority first.{" "}
        {plan.uses_gap_plan
          ? "Learning steps and hours come from your Knowledge gaps plan."
          : <>Hours are estimates; open <Link className="underline" to="../gaps" relative="path">Knowledge gaps</Link> for step-by-step estimates and the plan will use them.</>}
      </p>
    </section>
  );
}

function BlockRow({ block, onDone, busy }: { block: PlanBlockT; onDone: () => void; busy: boolean }) {
  return (
    <li className="flex gap-3 items-start rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide">{KIND_LABEL[block.kind]}</span>
          {block.jd_id ? (
            <Link className="font-medium hover:underline" to={`../topic/${block.jd_id}`} relative="path">{block.name}</Link>
          ) : (
            <span className="font-medium">{block.name}</span>
          )}
          {block.jd_id && <IdChip id={block.jd_id} />}
          {block.tier && <TierBadge tier={block.tier} />}
          {block.status && <StatusBadge status={block.status} />}
        </div>
        <p className="text-sm muted">{block.label}</p>
      </div>
      <span className="text-sm tabular-nums whitespace-nowrap">{hours(block.hours)}</span>
      <button className="btn-ghost text-xs no-print" onClick={onDone} disabled={busy}
        aria-label={`Mark done: ${KIND_LABEL[block.kind]} ${block.name}, ${hours(block.hours)}`}>
        ✓ Done
      </button>
    </li>
  );
}

function Timeline({ plan, analysisId }: { plan: StudyPlanT; analysisId: number }) {
  const { mark } = useDone(analysisId);
  return (
    <ol className="relative space-y-4 border-l-2 ml-2 pl-5" style={{ borderColor: "var(--border)" }} aria-label="Day by day">
      {plan.days.map((day) => {
        const isToday = day.date === plan.today;
        const free = day.capacity_hours - day.used_hours;
        return (
          <li key={day.date} className="relative">
            <span aria-hidden className="absolute -left-[27px] top-5 size-3 rounded-full border-2"
              style={{ background: isToday || day.interview_day ? "var(--accent)" : "var(--surface)", borderColor: "var(--accent)" }} />
            <section className="card p-4 space-y-3" aria-label={dayTitle(day.date, plan.today, day.interview_day)}
              style={isToday ? { borderColor: "var(--accent)" } : undefined}>
              <div className="flex flex-wrap items-baseline gap-2">
                <h3 className="font-semibold">{dayTitle(day.date, plan.today, day.interview_day)}</h3>
                <span className="ml-auto text-xs muted tabular-nums">{hours(day.used_hours)} of {hours(day.capacity_hours)}</span>
              </div>
              <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-2)" }} aria-hidden>
                <div className="h-full rounded-full" style={{
                  width: `${day.capacity_hours ? Math.min(100, (day.used_hours / day.capacity_hours) * 100) : 0}%`,
                  background: "var(--accent)",
                }} />
              </div>
              {day.blocks.length ? (
                <ul className="space-y-2">
                  {day.blocks.map((b) => (
                    <BlockRow key={b.id} block={b} busy={mark.isPending} onDone={() => mark.mutate(b)} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm muted">{day.capacity_hours ? "Nothing planned." : "Today's hours are already done."}</p>
              )}
              {(plan.cards_due[day.date] ?? 0) > 0 && !day.interview_day && (
                <p className="text-sm">
                  <Link className="underline" to="../cards" relative="path">
                    {plan.cards_due[day.date]} {plan.cards_due[day.date] === 1 ? "flashcard" : "flashcards"} due
                  </Link>
                  <span className="muted"> · about {Math.max(5, Math.round(plan.cards_due[day.date] * 0.5))} min</span>
                </p>
              )}
              {free > 0 && day.blocks.length > 0 && (
                <p className="text-xs muted">{hours(free)} free: buffer, or extra practice on tier 1 topics.</p>
              )}
            </section>
          </li>
        );
      })}
    </ol>
  );
}

export function StudyPlan() {
  const { analysis, id } = useAnalysisCtx();
  const q = useQuery({ queryKey: keys.plan(id), queryFn: () => api.getPlan(id) });
  const { undo } = useDone(id);

  if (q.isPending) return <LoadingState label="Building your study plan…" />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const plan = q.data;

  const schedule = (
    <ScheduleCard analysisId={id} interviewDate={analysis.interview_date} interviewTime={analysis.interview_time}
      hoursPerDay={analysis.hours_per_day} schedule={analysis.schedule} />
  );

  if (plan.missing.length) {
    const what = plan.missing.length === 2 ? "your interview date and hours per day"
      : plan.missing[0] === "interview_date" ? "your interview date" : "how many hours per day you can study";
    return (
      <div className="space-y-4 max-w-xl">
        <p>To build a day-by-day plan, add {what}. About <strong>{hours(plan.needed_hours)}</strong> of study is needed in total.</p>
        {schedule}
      </div>
    );
  }
  if (plan.past) {
    return <div className="space-y-4 max-w-xl"><p>This interview date has passed. Set a new date to plan again.</p>{schedule}</div>;
  }

  return (
    <div className="space-y-6">
      <Summary plan={plan} />

      {plan.done_today.length > 0 && (
        <section className="card p-5" aria-labelledby="done-h">
          <h2 id="done-h" className="font-semibold mb-2">Done today</h2>
          <ul className="space-y-1">
            {plan.done_today.map((e) => (
              <li key={e.id} className="flex items-center gap-2 text-sm">
                <span aria-hidden style={{ color: "var(--strong)" }}>✓</span>
                <span>{KIND_LABEL[e.kind]}: {e.name}</span>
                <span className="muted tabular-nums">{hours(e.hours)}</span>
                <button className="ml-auto text-xs underline muted no-print" disabled={undo.isPending}
                  onClick={() => undo.mutate(e.id)}>Undo</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_18rem]">
        <section aria-labelledby="timeline-h" className="min-w-0">
          <h2 id="timeline-h" className="text-lg font-semibold mb-3">Day by day</h2>
          <Timeline plan={plan} analysisId={id} />
        </section>
        <aside className="space-y-4">
          {schedule}
          {plan.unscheduled.length > 0 && (
            <section className="card p-5" aria-labelledby="unsched-h">
              <h2 id="unsched-h" className="font-semibold">Not scheduled</h2>
              <p className="text-xs muted mb-2">Didn't fit before the interview, in priority order.</p>
              <ul className="space-y-2 text-sm">
                {plan.unscheduled.map((u) => (
                  <li key={u.jd_id} className="flex gap-2 items-baseline">
                    <Link className="hover:underline flex-1 min-w-0" to={`../topic/${u.jd_id}`} relative="path">{u.name}</Link>
                    <span className="muted tabular-nums whitespace-nowrap">{hours(u.hours)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
