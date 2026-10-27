import { LabelBadge, Quote } from "../components/ui";
import { useAnalysisCtx } from "./AnalysisLayout";

export function Company() {
  const { analysis, result } = useAnalysisCtx();
  const { meta } = result;
  const facts = [
    ["Role", meta.role_title],
    ["Company", meta.company_name],
    ["Location", meta.location],
    ["Employment type", meta.employment_type],
  ].filter(([, v]) => v);
  const sections = [...new Set(result.jd_items.map((i) => i.section))];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section className="card p-5 space-y-3" aria-labelledby="role-h">
        <h2 id="role-h" className="font-semibold">The role <LabelBadge label="fact" /></h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {facts.map(([k, v]) => (
            <div key={k} className="contents"><dt className="muted">{k}</dt><dd>{v}</dd></div>
          ))}
        </dl>
        {analysis.jd.url && (
          <p className="text-sm">
            <a className="underline break-all" href={analysis.jd.url} target="_blank" rel="noreferrer noopener">Original posting</a>
          </p>
        )}
        <p className="text-sm muted">Sections in the posting: {sections.join(" · ")}</p>
      </section>

      <section className="card p-5 space-y-3" aria-labelledby="about-h">
        <h2 id="about-h" className="font-semibold">About the company <LabelBadge label="fact" /></h2>
        <p className="text-xs muted">Quoted only from the fetched posting.</p>
        {result.about_company.length ? (
          <div className="space-y-2">{result.about_company.map((q, i) => <Quote key={i}>{q}</Quote>)}</div>
        ) : (
          <p className="text-sm muted">The posting does not describe the company.</p>
        )}
      </section>

      <section className="card p-5 md:col-span-2" role="note" style={{ background: "var(--partial-bg)" }}>
        <h2 className="font-semibold" style={{ color: "var(--partial)" }}>Interview process: not verified</h2>
        <p className="text-sm mt-1">
          Nothing here describes this company's interview process. The posting does not state it, and this app does not
          guess it. Check with your recruiter or the company's careers pages.
        </p>
      </section>
    </div>
  );
}
