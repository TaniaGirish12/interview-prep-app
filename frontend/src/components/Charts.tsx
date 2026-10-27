import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AnalysisResult } from "../schemas";

const axisTick = { fill: "var(--muted)", fontSize: 12 };
const shortLabel = (label: string) => (label.length > 12 ? `${label.slice(0, 11).trimEnd()}…` : label);
const tooltipStyle = {
  contentStyle: { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)" },
  itemStyle: { color: "var(--text)" },
  labelStyle: { color: "var(--text)", fontWeight: 600 },
};

export function MatchRadar({ radar }: { radar: AnalysisResult["scores"]["radar"] }) {
  const data = radar.map((r) => ({ ...r, label: r.area }));
  return (
    <figure aria-labelledby="radar-title">
      <figcaption id="radar-title" className="font-semibold">Match by skill area (%)</figcaption>
      <div className="h-72 overflow-hidden" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="40%" margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
            <PolarGrid stroke="var(--grid)" />
            <PolarAngleAxis dataKey="label" tick={{ ...axisTick, fontSize: 11 }} tickFormatter={shortLabel} />
            <PolarRadiusAxis domain={[0, 100]} tick={false} tickCount={5} axisLine={false} />
            <Radar dataKey="score" name="Match %" stroke="var(--accent)" strokeWidth={2}
              fill="var(--accent)" fillOpacity={0.18} dot={{ r: 4, fill: "var(--accent)", stroke: "var(--surface)", strokeWidth: 2 }} />
            <Tooltip {...tooltipStyle} formatter={(v) => [`${v}%`, "Match"]} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="sr-only"><table>
        <caption>Match percentage per skill area</caption>
        <thead><tr><th>Skill area</th><th>Match %</th><th>Requirements</th></tr></thead>
        <tbody>{radar.map((r) => <tr key={r.area}><td>{r.area}</td><td>{r.score}</td><td>{r.count}</td></tr>)}</tbody>
      </table></div>
    </figure>
  );
}

const SERIES = [
  { key: "strong", name: "Strong match", color: "var(--c-strong)" },
  { key: "partial", name: "Partial", color: "var(--c-partial)" },
  { key: "gap", name: "Gap", color: "var(--c-gap)" },
] as const;

export function TierStatusBars({ rows }: { rows: AnalysisResult["scores"]["tier_status"] }) {
  const data = rows.map((r) => ({ ...r, label: `Tier ${r.tier}` }));
  return (
    <figure aria-labelledby="tier-title">
      <figcaption id="tier-title" className="font-semibold">Requirements by tier and status</figcaption>
      <div className="h-72" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 12, right: 8, left: -16, bottom: 0 }} barCategoryGap="28%">
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="label" tick={axisTick} axisLine={{ stroke: "var(--border)" }} tickLine={false} />
            <YAxis allowDecimals={false} tick={axisTick} axisLine={false} tickLine={false} />
            <Tooltip {...tooltipStyle} cursor={{ fill: "var(--surface-2)" }} />
            <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} formatter={(v) => <span style={{ color: "var(--muted)" }}>{v}</span>} />
            {SERIES.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} stackId="s" fill={s.color}
                stroke="var(--surface)" strokeWidth={2}
                radius={i === SERIES.length - 1 ? [4, 4, 0, 0] : 0} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="sr-only"><table>
        <caption>Number of requirements per tier, by match status</caption>
        <thead><tr><th>Tier</th><th>Strong</th><th>Partial</th><th>Gap</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.tier}><td>{r.tier}</td><td>{r.strong}</td><td>{r.partial}</td><td>{r.gap}</td></tr>)}</tbody>
      </table></div>
    </figure>
  );
}
