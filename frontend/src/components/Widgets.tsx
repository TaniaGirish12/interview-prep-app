import { useEffect, useState } from "react";
import type { StepState } from "../api/hooks";
import { daysUntil, relativeDay } from "../lib/dates";
import { useTheme } from "../lib/theme";
import type { Cost } from "../schemas";

export function ThemeToggle() {
  const { dark, toggle } = useTheme();
  return (
    <button className="btn-ghost" onClick={toggle} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
      <span aria-hidden>{dark ? "☀" : "☾"}</span>
      <span className="hidden sm:inline">{dark ? "Light" : "Dark"}</span>
    </button>
  );
}

export function CostMeter({ cost, backend }: { cost: Cost; backend: "api" | "claude-code" }) {
  const tokens = cost.input + cost.output + cost.cache_read + cost.cache_write;
  if (backend === "claude-code") {
    return (
      <div className="text-xs muted tabular-nums" title={`${cost.calls} calls via the claude CLI on your subscription`}
        aria-label={`Claude subscription, ${tokens} tokens across ${cost.calls} model calls`}>
        Claude subscription · {(tokens / 1000).toFixed(1)}k tokens
      </div>
    );
  }
  return (
    <div
      className="text-xs muted tabular-nums"
      title={`${cost.calls} calls · input ${cost.input} · output ${cost.output} · cache read ${cost.cache_read} · cache write ${cost.cache_write} tokens`}
      aria-label={`Estimated cost ${cost.usd.toFixed(2)} US dollars across ${cost.calls} model calls`}
    >
      ≈ ${cost.usd.toFixed(cost.usd < 1 ? 3 : 2)} · {(tokens / 1000).toFixed(1)}k tokens
    </div>
  );
}

export function Countdown({ date, time }: { date: string | null; time?: string | null }) {
  // Re-render every minute so the hours count down and the day rolls over at midnight.
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, []);
  if (!date) {
    return <p className="muted text-sm">No interview date set yet.</p>;
  }
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = (time ?? "00:00").split(":").map(Number);
  const at = new Date(y, m - 1, d, hh, mm);
  const msLeft = at.getTime() - Date.now();
  const days = daysUntil(date);
  const when = `${at.toLocaleDateString(undefined, { dateStyle: "full" })}${time ? ` at ${formatTime(time)}` : ""}`;

  if (days < 0 || (time && msLeft <= 0)) {
    return <p className="font-semibold">This interview was {days < 0 ? relativeDay(date).toLowerCase() : "earlier today"}.</p>;
  }
  if (days === 0) {
    return (
      <p>
        <span className="text-lg font-semibold">Interview day is today. Good luck!</span>
        {time && <span className="block text-sm muted mt-1">At {formatTime(time)}, in {formatDuration(msLeft)}</span>}
      </p>
    );
  }
  return (
    <p className="tabular-nums" aria-live="off">
      <span className="text-4xl font-bold">{days}</span> <span className="muted">{days === 1 ? "day" : "days"} to go</span>
      <span className="block text-sm muted mt-1">Interview on {when}</span>
      {time && <span className="block text-sm muted">That is {formatDuration(msLeft)} from now</span>}
    </p>
  );
}

export function formatTime(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function formatDuration(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60_000));
  const d = Math.floor(totalMin / 1440);
  const h = Math.floor((totalMin % 1440) / 60);
  const min = totalMin % 60;
  if (d > 0) return `${d} ${d === 1 ? "day" : "days"} ${h} h`;
  if (h > 0) return `${h} h ${min} min`;
  return `${min} min`;
}

export function PipelineProgress({ steps, error, dropped }: { steps: StepState[]; error: string | null; dropped: number }) {
  const all = [
    { step: "jd", label: "Extracting job requirements" },
    { step: "rank", label: "Ranking requirements" },
    { step: "resume", label: "Extracting resume" },
    { step: "match", label: "Matching resume to requirements" },
  ];
  return (
    <ol className="space-y-2" aria-label="Analysis progress">
      {all.map(({ step, label }) => {
        const s = steps.find((x) => x.step === step);
        const state = s?.state ?? "pending";
        return (
          <li key={step} className="card flex items-center gap-3 px-4 py-3">
            <span aria-hidden className="w-5 text-center">
              {state === "done" ? "✓" : state === "running" ? (
                <span className="inline-block size-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
              ) : "·"}
            </span>
            <span className={state === "pending" ? "muted" : ""}>{label}</span>
            <span className="ml-auto text-xs muted">
              {state === "done" && (s?.cached ? "from cache" : "done")}
              {state === "done" && s?.dropped ? ` · ${s.dropped} unverifiable item(s) dropped` : ""}
              {state === "running" && "working…"}
              <span className="sr-only">{state}</span>
            </span>
          </li>
        );
      })}
      {dropped > 0 && !error && (
        <li className="text-xs muted">Items whose quotes could not be found in the source were dropped and logged.</li>
      )}
    </ol>
  );
}
