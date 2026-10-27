import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import { CodeBlock } from "../components/CodeBlock";
import { Markdown } from "../components/Markdown";
import { MermaidDiagram } from "../components/MermaidDiagram";
import { TopicFlashcards } from "../components/TopicFlashcards";
import { RevealAnswer } from "../components/RevealAnswer";
import { ErrorState, IdChip, LabelBadge, LoadingState, Quote, StatusBadge, TierBadge } from "../components/ui";
import type { TopicContent } from "../schemas";
import { useAnalysisCtx } from "./AnalysisLayout";

const LEVEL: Record<string, string> = { fundamentals: "Fundamentals", intermediate: "Going deeper", interview: "Interview level" };

export function Topic() {
  const { result, id } = useAnalysisCtx();
  const jdId = useParams().jdId!;
  const qc = useQueryClient();
  const item = result.jd_items.find((i) => i.id === jdId);

  // Opening a topic moves it to the front of the generation queue.
  useEffect(() => {
    if (item) api.openTopic(id, jdId).then((r) => qc.setQueryData(keys.topic(id, jdId), r)).catch(() => {});
  }, [id, jdId, item, qc]);

  const q = useQuery({
    queryKey: keys.topic(id, jdId),
    queryFn: () => api.getTopic(id, jdId),
    enabled: Boolean(item),
    refetchInterval: (query) => (query.state.data?.status === "ready" || query.state.data?.status === "error" ? false : 5000),
  });

  if (!item) return <ErrorState message={`Unknown requirement ${jdId}.`} />;
  const rank = result.rankings[jdId];
  const match = result.matches[jdId];
  const cv = Object.fromEntries(result.cv_items.map((c) => [c.id, c]));

  return (
    <article className="space-y-6" aria-labelledby="topic-h">
      <header className="space-y-3">
        <Link to={`/a/${id}`} className="text-sm underline muted no-print">← Overview</Link>
        <h2 id="topic-h" className="text-2xl font-bold">{q.data?.status === "ready" ? q.data.content.title : item.name}</h2>
        <div className="flex flex-wrap gap-2 items-center">
          <IdChip id={jdId} /><TierBadge tier={rank.tier} /><StatusBadge status={match.status} />
          <span className="text-xs muted">{rank.skill_area}</span>
        </div>
        <div className="card p-4 space-y-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide muted mb-1">From the job posting · <LabelBadge label="fact" /></p>
            <Quote source={item.section}>{item.quote}</Quote>
          </div>
          {match.evidence.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide muted mb-1">From your resume · <LabelBadge label="fact" /></p>
              {match.evidence.map((e, i) => <Quote key={i} source={`${e.cv_id} · ${cv[e.cv_id]?.title ?? ""}`}>{e.quote}</Quote>)}
            </div>
          )}
          <p className="text-sm">{match.rationale}</p>
        </div>
      </header>

      {q.isPending ? (
        <LoadingState label="Checking for notes…" />
      ) : q.isError ? (
        <ErrorState message={q.error.message} onRetry={() => q.refetch()} />
      ) : q.data.status === "ready" ? (
        <>
          <TopicBody content={q.data.content} />
          <TopicFlashcards analysisId={id} jdId={jdId} />
        </>
      ) : q.data.status === "error" ? (
        <ErrorState message={q.data.error ?? "Generating these notes failed."}
          onRetry={() => api.openTopic(id, jdId).then((r) => qc.setQueryData(keys.topic(id, jdId), r))} />
      ) : (
        <LoadingState label={
          q.data.status === "generating" ? "Writing notes and compiling the code examples… (usually under a minute)"
            : q.data.status === "queued" ? `Queued${"position" in q.data && q.data.position ? ` (position ${q.data.position})` : ""}…`
              : "Starting…"} />
      )}
    </article>
  );
}

function Bullets({ items, title }: { items: TopicContent["common_mistakes"]; title: string }) {
  if (!items.length) return null;
  return (
    <section className="card p-5" aria-label={title}>
      <h3 className="font-semibold mb-2">{title}</h3>
      <ul className="space-y-2">
        {items.map((b, i) => (
          <li key={i} className="text-sm">
            <span>{b.text}</span>{" "}
            <span className="inline-flex flex-wrap gap-1 align-middle"><LabelBadge label={b.label} />{b.jd_ids.map((j) => <IdChip key={j} id={j} />)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TopicBody({ content }: { content: TopicContent }) {
  return (
    <div className="space-y-6">
      <section className="space-y-4" aria-label="Explanation">
        {content.explanation.map((s, i) => (
          <div key={i} className="card p-5">
            <p className="text-xs font-semibold uppercase tracking-wide muted">{LEVEL[s.level]}</p>
            <h3 className="text-lg font-semibold mt-1">{s.heading}</h3>
            <Markdown text={s.body_md} />
          </div>
        ))}
      </section>

      {content.diagram && (
        <MermaidDiagram code={content.diagram.mermaid} description={content.diagram.description} title={content.title} />
      )}

      {content.code_examples.length > 0 && (
        <section className="space-y-4" aria-label="Code examples">
          <h3 className="text-lg font-semibold">Code examples</h3>
          {content.code_examples.map((ex, i) => <CodeBlock key={i} example={ex} />)}
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Bullets title="Common mistakes" items={content.common_mistakes} />
        <Bullets title="Real-world use" items={content.real_world_use} />
      </div>

      <section className="space-y-3" aria-labelledby="q-h">
        <h3 id="q-h" className="text-lg font-semibold">Likely interview questions</h3>
        <p className="text-xs muted">These are predictions based on the posting, not confirmed questions. Replace any [PLACEHOLDER] with your own details.</p>
        {content.likely_questions.map((q, i) => (
          <div key={i} className="card p-5 space-y-3">
            <div className="flex flex-wrap gap-2 items-center">
              <span className="text-xs font-semibold uppercase muted">{q.difficulty}</span>
              <LabelBadge label="prediction" />
              {q.jd_ids.map((j) => <IdChip key={j} id={j} />)}
            </div>
            <p className="font-medium">{q.question}</p>
            <RevealAnswer><Markdown text={q.model_answer} /></RevealAnswer>
          </div>
        ))}
      </section>
    </div>
  );
}
