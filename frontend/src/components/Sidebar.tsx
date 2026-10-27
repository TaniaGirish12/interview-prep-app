import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import { daysUntil, relativeDay } from "../lib/dates";
import type { AnalysisListItem } from "../schemas";
import { formatTime } from "./Widgets";

type Group = { title: string; items: AnalysisListItem[] };

/** Upcoming interviews soonest first, then ones without a date, then past ones (most recent first). */
export function groupInterviews(items: AnalysisListItem[], today: Date = new Date()): Group[] {
  const upcoming = items.filter((a) => a.interview_date && daysUntil(a.interview_date, today) >= 0)
    .sort((a, b) => `${a.interview_date} ${a.interview_time ?? ""}`.localeCompare(`${b.interview_date} ${b.interview_time ?? ""}`));
  const undated = items.filter((a) => !a.interview_date);
  const past = items.filter((a) => a.interview_date && daysUntil(a.interview_date, today) < 0)
    .sort((a, b) => b.interview_date!.localeCompare(a.interview_date!));
  return [
    { title: "Upcoming", items: upcoming },
    { title: "No date set", items: undated },
    { title: "Past", items: past },
  ].filter((g) => g.items.length);
}

function StatusLine({ a }: { a: AnalysisListItem }) {
  if (a.status === "running" || a.status === "pending") return <span>Analysing…</span>;
  if (a.status === "error") return <span style={{ color: "var(--gap)" }}>Analysis failed</span>;
  return a.match_score === null ? null : <span className="tabular-nums">{Math.round(a.match_score)}% match</span>;
}

function DateLine({ date, time }: { date: string | null; time: string | null }) {
  if (!date) return <span>No date</span>;
  const n = daysUntil(date);
  const soon = n >= 0 && n <= 7;
  return (
    <span className={soon ? "font-semibold" : ""} style={soon ? { color: "var(--partial)" } : undefined}>
      {relativeDay(date)}{time && ` · ${formatTime(time)}`}
    </span>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const q = useQuery({
    queryKey: keys.list,
    queryFn: api.listAnalyses,
    // Keep "Analysing…" entries fresh until they finish.
    refetchInterval: (query) =>
      query.state.data?.some((a) => a.status === "running" || a.status === "pending") ? 5000 : false,
  });

  return (
    <nav aria-label="Your interviews" className="flex flex-col gap-4 h-full">
      <NavLink to="/" end onClick={onNavigate} className="btn w-full">+ New interview</NavLink>

      {q.isPending ? (
        <p className="text-sm muted" role="status">Loading interviews…</p>
      ) : q.isError ? (
        <p className="text-sm" role="alert" style={{ color: "var(--gap)" }}>
          Could not load interviews. <button className="underline" onClick={() => q.refetch()}>Retry</button>
        </p>
      ) : q.data.length === 0 ? (
        <p className="text-sm muted">No interviews yet. Start one with your resume and a job posting.</p>
      ) : (
        groupInterviews(q.data).map((g) => (
          <section key={g.title} aria-label={g.title}>
            <h2 className="text-xs font-semibold uppercase tracking-wide muted mb-1 px-2">{g.title}</h2>
            <ul className="space-y-0.5">
              {g.items.map((a) => (
                <li key={a.id}>
                  <NavLink
                    to={`/a/${a.id}`}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `block rounded-lg px-2 py-2 text-sm ${isActive ? "" : "hover:bg-[var(--surface-2)]"}`}
                    style={({ isActive }) => (isActive ? { background: "var(--surface-2)" } : undefined)}
                  >
                    <span className="block font-medium leading-snug line-clamp-2">{a.title ?? `Interview ${a.id}`}</span>
                    {a.company && <span className="block text-xs muted truncate">{a.company}</span>}
                    <span className="mt-1 flex flex-wrap gap-x-2 text-xs muted">
                      <DateLine date={a.interview_date} time={a.interview_time} />
                      <StatusLine a={a} />
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </nav>
  );
}
