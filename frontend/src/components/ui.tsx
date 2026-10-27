import { useEffect, useState, type ReactNode } from "react";
import type { StatusT } from "../schemas";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-3 py-10 justify-center muted">
      <span className="size-4 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card p-8 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="muted mt-2 text-sm">{children}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="card p-5 border-[var(--gap)]" style={{ background: "var(--gap-bg)" }}>
      <p className="font-semibold" style={{ color: "var(--gap)" }}>Something went wrong</p>
      <p className="mt-1 text-sm whitespace-pre-wrap">{message}</p>
      {onRetry && <button className="btn mt-3" onClick={onRetry}>Retry</button>}
    </div>
  );
}

const STATUS_TEXT: Record<StatusT, string> = { strong: "Strong match", partial: "Partial", gap: "Gap" };

export function StatusBadge({ status }: { status: StatusT }) {
  return (
    <span
      className="inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ color: `var(--${status})`, background: `var(--${status}-bg)` }}
    >
      {STATUS_TEXT[status]}
    </span>
  );
}

export function TierBadge({ tier }: { tier: number }) {
  return (
    <span
      className="inline-block whitespace-nowrap rounded-md border px-1.5 py-0.5 text-xs font-semibold tabular-nums"
      style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}
      title={`Tier ${tier}: ${["", "central to the role", "explicit requirement", "nice-to-have or supporting", "peripheral"][tier]}`}
    >
      Tier {tier}
    </span>
  );
}

export function LabelBadge({ label }: { label: "fact" | "prediction" }) {
  const fact = label === "fact";
  return (
    <span
      className="inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium border"
      style={{ borderColor: "var(--border)", color: "var(--muted)" }}
    >
      {fact ? "Fact (from JD/resume)" : "Prediction (not confirmed)"}
    </span>
  );
}

export function IdChip({ id }: { id: string }) {
  return (
    <code className="whitespace-nowrap rounded px-1 py-0.5 text-[11px]" style={{ background: "var(--surface-2)", color: "var(--muted)" }}>
      {id}
    </code>
  );
}

export function Quote({ children, source }: { children: ReactNode; source?: string }) {
  return (
    <blockquote className="border-l-4 pl-3 py-1 text-sm italic" style={{ borderColor: "var(--accent)" }}>
      “{children}”{source && <span className="not-italic muted"> · {source}</span>}
    </blockquote>
  );
}

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable: keep in memory only */
    }
  }, [key, value]);
  return [value, setValue];
}
