import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import { EmptyState, ErrorState, IdChip, LoadingState, StatusBadge, TierBadge } from "../components/ui";
import { useAnalysisCtx } from "./AnalysisLayout";

export function Gaps() {
  const { result, id } = useAnalysisCtx();
  const q = useQuery({
    queryKey: keys.gaps(id),
    queryFn: () => api.getGaps(id),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? 4000 : false),
  });
  const items = Object.fromEntries(result.jd_items.map((i) => [i.id, i]));

  if (q.isPending) return <LoadingState />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (d.status === "error") return <ErrorState message={d.error} onRetry={async () => { await api.retryGaps(id); q.refetch(); }} />;
  if (d.status !== "ready") return <LoadingState label="Building your learning plan for partial matches and gaps…" />;
  if (!d.plans.length) return <EmptyState title="No gaps to close">Every requirement is a strong match.</EmptyState>;

  const total = d.plans.reduce((s, p) => s + p.steps.reduce((t, x) => t + x.est_hours, 0), 0);
  return (
    <div className="space-y-4">
      <p className="text-sm muted">
        In priority order (highest tier and biggest gap first). Estimated total: <strong>{total.toFixed(1)} hours</strong>. Estimates are predictions.
      </p>
      <ol className="space-y-4">
        {d.plans.map((p) => {
          const item = items[p.jd_id];
          const hours = p.steps.reduce((t, x) => t + x.est_hours, 0);
          return (
            <li key={p.jd_id} className="card p-5">
              <div className="flex flex-wrap gap-2 items-center">
                <Link to={`../topic/${p.jd_id}`} relative="path" className="font-semibold hover:underline">{item?.name ?? p.jd_id}</Link>
                <IdChip id={p.jd_id} />
                <TierBadge tier={result.rankings[p.jd_id].tier} />
                <StatusBadge status={result.matches[p.jd_id].status} />
                <span className="ml-auto text-sm tabular-nums muted">{hours.toFixed(1)} h</span>
              </div>
              <ol className="mt-3 space-y-2">
                {[...p.steps].sort((a, b) => a.order - b.order).map((s) => (
                  <li key={s.order} className="flex gap-3 text-sm">
                    <span className="tabular-nums muted w-5 text-right">{s.order}.</span>
                    <span className="flex-1">
                      <span className="font-medium">{s.what}</span>
                      <span className="block muted">{s.why}</span>
                    </span>
                    <span className="tabular-nums muted whitespace-nowrap">{s.est_hours} h</span>
                  </li>
                ))}
              </ol>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
