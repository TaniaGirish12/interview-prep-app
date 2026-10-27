import { Fragment, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { AnalysisResult, StatusT } from "../schemas";
import { IdChip, Quote, StatusBadge, TierBadge } from "./ui";

type SortKey = "id" | "tier" | "status" | "confidence";
const STATUS_ORDER: Record<StatusT, number> = { gap: 0, partial: 1, strong: 2 };
const CATEGORY: Record<string, string> = { task: "Task", requirement: "Requirement", nice_to_have: "Nice-to-have" };

export function MatrixTable({ result, analysisId }: { result: AnalysisResult; analysisId: number }) {
  const [tier, setTier] = useState<number | "all">("all");
  const [status, setStatus] = useState<StatusT | "all">("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "tier", dir: 1 });
  const [open, setOpen] = useState<Set<string>>(new Set());
  const cv = useMemo(() => Object.fromEntries(result.cv_items.map((c) => [c.id, c])), [result.cv_items]);

  const rows = useMemo(() => {
    const list = result.jd_items
      .map((item) => ({ item, rank: result.rankings[item.id], match: result.matches[item.id] }))
      .filter((r) => (tier === "all" || r.rank.tier === tier) && (status === "all" || r.match.status === status));
    const val = (r: (typeof list)[number]) =>
      sort.key === "id" ? r.item.id
        : sort.key === "tier" ? r.rank.tier
          : sort.key === "status" ? STATUS_ORDER[r.match.status]
            : r.match.confidence;
    return list.sort((a, b) => {
      const x = val(a), y = val(b);
      const c = x < y ? -1 : x > y ? 1 : a.item.id.localeCompare(b.item.id);
      return c * sort.dir;
    });
  }, [result, tier, status, sort]);

  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const header = (key: SortKey, label: string) => {
    const active = sort.key === key;
    return (
      <th scope="col" className="px-3 py-2 text-left font-semibold"
        aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button className="inline-flex items-center gap-1"
          onClick={() => setSort({ key, dir: active ? (sort.dir === 1 ? -1 : 1) : 1 })}>
          {label}<span aria-hidden className="muted">{active ? (sort.dir === 1 ? "▲" : "▼") : "↕"}</span>
        </button>
      </th>
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 items-end no-print">
        <label className="text-sm">
          <span className="block muted mb-1">Tier</span>
          <select className="field" value={String(tier)} onChange={(e) => setTier(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">All tiers</option>
            {[1, 2, 3, 4].map((t) => <option key={t} value={t}>Tier {t}</option>)}
          </select>
        </label>
        <label className="text-sm">
          <span className="block muted mb-1">Status</span>
          <select className="field" value={status} onChange={(e) => setStatus(e.target.value as StatusT | "all")}>
            <option value="all">All statuses</option>
            <option value="strong">Strong match</option>
            <option value="partial">Partial</option>
            <option value="gap">Gap</option>
          </select>
        </label>
        <p className="text-sm muted ml-auto" aria-live="polite">{rows.length} of {result.jd_items.length} requirements</p>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead style={{ background: "var(--surface-2)" }}>
            <tr>
              <th scope="col" className="w-8"><span className="sr-only">Expand</span></th>
              {header("id", "ID")}
              <th scope="col" className="px-3 py-2 text-left font-semibold">Requirement</th>
              {header("tier", "Tier")}
              {header("status", "Status")}
              {header("confidence", "Confidence")}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ item, rank, match }) => {
              const isOpen = open.has(item.id);
              return (
                <Fragment key={item.id}>
                  <tr className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-2">
                      <button className="btn-ghost px-2 py-1" aria-expanded={isOpen} aria-controls={`row-${item.id}`}
                        onClick={() => toggle(item.id)} aria-label={`${isOpen ? "Collapse" : "Expand"} ${item.id}`}>
                        <span aria-hidden>{isOpen ? "−" : "+"}</span>
                      </button>
                    </td>
                    <td className="px-3 py-2"><IdChip id={item.id} /></td>
                    <td className="px-3 py-2 min-w-48">
                      <Link className="font-medium hover:underline" to={`/a/${analysisId}/topic/${item.id}`}>{item.name}</Link>
                      <span className="block text-xs muted">{CATEGORY[item.category]} · {rank.skill_area}</span>
                    </td>
                    <td className="px-3 py-2"><TierBadge tier={rank.tier} /></td>
                    <td className="px-3 py-2"><StatusBadge status={match.status} /></td>
                    <td className="px-3 py-2 tabular-nums">{Math.round(match.confidence * 100)}%</td>
                  </tr>
                  {isOpen && (
                    <tr id={`row-${item.id}`} style={{ background: "var(--surface-2)" }}>
                      <td />
                      <td colSpan={5} className="px-3 py-3 space-y-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide muted mb-1">Job posting</p>
                          <Quote source={item.section}>{item.quote}</Quote>
                          <p className="text-xs muted mt-1">Tier reason: {rank.reason}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide muted mb-1">Resume evidence</p>
                          {match.evidence.length ? (
                            <ul className="space-y-1">
                              {match.evidence.map((e, i) => (
                                <li key={i} className="flex gap-2 items-start">
                                  <IdChip id={e.cv_id} />
                                  <Quote source={cv[e.cv_id]?.title}>{e.quote}</Quote>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm muted">No evidence in the resume.</p>
                          )}
                          <p className="text-sm mt-2">{match.rationale}</p>
                          {match.downgraded && (
                            <p className="text-xs mt-1" style={{ color: "var(--partial)" }}>
                              Set to Gap: the model's evidence quotes could not be verified in the resume.
                            </p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && <p className="p-6 text-center muted">No requirements match these filters.</p>}
      </div>
    </div>
  );
}
