import { NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAnalysis, useAnalysisEvents } from "../api/hooks";
import { CostMeter, PipelineProgress } from "../components/Widgets";
import { ErrorState, LoadingState } from "../components/ui";
import type { Analysis, AnalysisResult } from "../schemas";

export type AnalysisCtx = { analysis: Analysis; result: AnalysisResult; id: number };

export function useAnalysisCtx() {
  return useOutletContext<AnalysisCtx>();
}

const TABS = [
  { to: "", label: "Overview", end: true },
  { to: "matrix", label: "JD vs resume" },
  { to: "plan", label: "Study plan" },
  { to: "cards", label: "Flashcards" },
  { to: "gaps", label: "Knowledge gaps" },
  { to: "company", label: "Company & role" },
];

export function AnalysisLayout() {
  const id = Number(useParams().id);
  const q = useAnalysis(id);
  const live = useAnalysisEvents(id);

  if (q.isPending) return <LoadingState label="Loading analysis…" />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;

  const a = q.data;
  const title = a.result?.meta.role_title ?? a.jd.title ?? `Analysis ${id}`;
  const company = a.result?.meta.company_name ?? a.jd.company;

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl sm:text-2xl font-bold break-words">{title}</h1>
            {company && <p className="muted">{company}</p>}
          </div>
          <CostMeter cost={a.cost} backend={a.backend} />
        </div>
        {a.status === "done" && a.result && (
          <nav aria-label="Analysis sections" className="flex gap-1 overflow-x-auto no-print -mx-1 px-1">
            {TABS.map((t) => (
              <NavLink key={t.label} to={t.to} end={t.end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "" : "muted hover:bg-[var(--surface-2)]"}`}
                style={({ isActive }) => (isActive ? { background: "var(--surface-2)", color: "var(--text)" } : undefined)}>
                {t.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      {a.status === "done" && a.result ? (
        <Outlet context={{ analysis: a, result: a.result, id } satisfies AnalysisCtx} />
      ) : a.status === "error" ? (
        <div className="space-y-4">
          <PipelineProgress steps={live.steps} error={a.error} dropped={live.dropped} />
          <ErrorState message={a.error ?? "The analysis failed."}
            onRetry={async () => { await api.retryAnalysis(id); q.refetch(); }} />
        </div>
      ) : (
        <div className="space-y-4" aria-live="polite">
          <p className="muted">Analysing. Each step's output is checked against your resume and the posting.</p>
          <PipelineProgress steps={live.steps} error={live.error} dropped={live.dropped} />
          {!live.connected && <p className="text-xs muted">Connecting to the progress stream…</p>}
        </div>
      )}
    </div>
  );
}
