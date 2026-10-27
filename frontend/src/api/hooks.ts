import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./client";

export const keys = {
  analysis: (id: number) => ["analysis", id] as const,
  topic: (id: number, jdId: string) => ["topic", id, jdId] as const,
  gaps: (id: number) => ["gaps", id] as const,
  plan: (id: number) => ["plan", id] as const,
  deck: (id: number) => ["deck", id] as const,
  topicCards: (id: number, jdId: string) => ["topicCards", id, jdId] as const,
  list: ["analyses"] as const,
};

export function useAnalysis(id: number) {
  return useQuery({ queryKey: keys.analysis(id), queryFn: () => api.getAnalysis(id) });
}

export type StepState = { step: string; label: string; state: "running" | "done"; cached?: boolean; dropped?: number };

export type LiveState = {
  steps: StepState[];
  dropped: number;
  error: string | null;
  connected: boolean;
};

const STEP_ORDER = ["jd", "rank", "resume", "match"];

/** Subscribes to the analysis event stream and keeps react-query caches fresh. */
export function useAnalysisEvents(id: number): LiveState {
  const qc = useQueryClient();
  const [state, setState] = useState<LiveState>({ steps: [], dropped: 0, error: null, connected: false });

  useEffect(() => {
    const es = new EventSource(`/api/analyses/${id}/events`);
    const on = (name: string, fn: (data: Record<string, unknown>) => void) =>
      es.addEventListener(name, (e) => fn(JSON.parse((e as MessageEvent).data)));

    es.onopen = () => setState((s) => ({ ...s, connected: true }));
    es.onerror = () => setState((s) => ({ ...s, connected: false }));
    on("analysis_started", () => setState({ steps: [], dropped: 0, error: null, connected: true }));
    on("step_started", (d) =>
      setState((s) => ({
        ...s,
        steps: [...s.steps.filter((x) => x.step !== d.step),
          { step: String(d.step), label: String(d.label), state: "running" as const }]
          .sort((a, b) => STEP_ORDER.indexOf(a.step) - STEP_ORDER.indexOf(b.step)),
      })),
    );
    on("step_done", (d) =>
      setState((s) => ({
        ...s,
        steps: s.steps.map((x) =>
          x.step === d.step ? { ...x, state: "done", cached: Boolean(d.cached), dropped: Number(d.dropped) } : x),
      })),
    );
    on("item_dropped", () => setState((s) => ({ ...s, dropped: s.dropped + 1 })));
    on("usage", (d) =>
      qc.setQueryData(keys.analysis(id), (old: unknown) =>
        old && typeof old === "object" ? { ...(old as object), cost: d } : old),
    );
    on("pipeline_error", (d) => {
      setState((s) => ({ ...s, error: String(d.message) }));
      qc.invalidateQueries({ queryKey: keys.analysis(id) });
      qc.invalidateQueries({ queryKey: keys.list });
    });
    on("analysis_done", () => {
      qc.invalidateQueries({ queryKey: keys.analysis(id) });
      qc.invalidateQueries({ queryKey: keys.list });
    });
    on("topic_status", (d) => {
      qc.invalidateQueries({ queryKey: keys.topic(id, String(d.jd_id)) });
      if (d.status === "ready" || d.status === "error") qc.invalidateQueries({ queryKey: keys.analysis(id) });
    });
    on("gaps_ready", () => {
      qc.invalidateQueries({ queryKey: keys.gaps(id) });
      qc.invalidateQueries({ queryKey: keys.plan(id) });  // the plan uses the gap estimates
    });
    return () => es.close();
  }, [id, qc]);

  return state;
}
