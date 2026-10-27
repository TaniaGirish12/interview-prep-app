import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import { Markdown } from "../components/Markdown";
import { EmptyState, ErrorState, IdChip, LabelBadge, LoadingState } from "../components/ui";
import type { FlashcardDeckT, FlashcardT, GradeT } from "../schemas";
import { useAnalysisCtx } from "./AnalysisLayout";

const GRADES: { grade: GradeT; label: string; key: string; hint: string }[] = [
  { grade: "again", label: "Again", key: "1", hint: "Didn't know it; show again today" },
  { grade: "hard", label: "Hard", key: "2", hint: "Got it with effort" },
  { grade: "good", label: "Good", key: "3", hint: "Knew it" },
  { grade: "easy", label: "Easy", key: "4", hint: "Knew it instantly" },
];

const KIND: Record<FlashcardT["kind"], string> = {
  concept: "Concept", question: "Interview question", mistake: "Common mistake", code: "Code",
};

/** Due reviews first (oldest first), then new cards. */
export function buildQueue(cards: FlashcardT[], topic: string | null): FlashcardT[] {
  const pick = cards.filter((c) => c.is_due && (!topic || c.jd_id === topic));
  return [...pick.filter((c) => !c.is_new).sort((a, b) => (a.due ?? "").localeCompare(b.due ?? "")),
    ...pick.filter((c) => c.is_new)];
}

function Session({ analysisId, initial, names, onDone }: {
  analysisId: number; initial: FlashcardT[]; names: Record<string, string>; onDone: () => void;
}) {
  const qc = useQueryClient();
  const [queue, setQueue] = useState(initial);
  const [flipped, setFlipped] = useState(false);
  const [reviewed, setReviewed] = useState(0);
  const card = queue[0];

  const grade = useMutation({
    mutationFn: (g: GradeT) => api.reviewCard(analysisId, card.id, g),
    onSuccess: (updated) => {
      setReviewed((n) => n + 1);
      setFlipped(false);
      // "Again" keeps the card due today: it comes back at the end of this session.
      setQueue((q) => (updated.is_due ? [...q.slice(1), updated] : q.slice(1)));
      qc.invalidateQueries({ queryKey: keys.analysis(analysisId) });
      qc.invalidateQueries({ queryKey: keys.plan(analysisId) });
    },
  });

  const onKey = useCallback((e: KeyboardEvent) => {
    if (!card || grade.isPending || e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
    if (!flipped && (e.key === " " || e.key === "Enter")) {
      e.preventDefault();
      setFlipped(true);
    } else if (flipped) {
      const g = GRADES.find((x) => x.key === e.key);
      if (g) grade.mutate(g.grade);
    }
  }, [card, flipped, grade]);

  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  if (!card) {
    return (
      <div className="card p-8 text-center space-y-3">
        <p className="text-lg font-semibold">Session done: {reviewed} {reviewed === 1 ? "review" : "reviews"}.</p>
        <button className="btn" onClick={onDone}>Back to the deck</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <span className="muted" aria-live="polite">{queue.length} left · {reviewed} reviewed</span>
        <button className="btn-ghost ml-auto" onClick={onDone}>End session</button>
      </div>
      <article className="card p-6 sm:p-8 space-y-4 min-h-64" aria-live="polite" aria-label="Flashcard">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold uppercase tracking-wide muted">{KIND[card.kind]}</span>
          <Link className="hover:underline" to={`../topic/${card.jd_id}`} relative="path">{names[card.jd_id] ?? card.jd_id}</Link>
          {card.jd_ids.map((j) => <IdChip key={j} id={j} />)}
          <LabelBadge label={card.label} />
          {card.is_new && <span className="muted">New</span>}
        </div>
        <p className="text-xl font-semibold leading-snug">{card.front}</p>
        {flipped ? (
          <div className="border-t pt-4" style={{ borderColor: "var(--border)" }}><Markdown text={card.back} /></div>
        ) : (
          <button className="btn" onClick={() => setFlipped(true)} autoFocus>Show answer <span className="muted text-xs">(Space)</span></button>
        )}
      </article>
      {flipped && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" role="group" aria-label="How well did you know it?">
          {GRADES.map((g) => (
            <button key={g.grade} className="btn-ghost justify-center flex-col py-3" disabled={grade.isPending}
              onClick={() => grade.mutate(g.grade)} title={g.hint} aria-keyshortcuts={g.key}>
              <span className="font-semibold">{g.label}</span>
              <span className="text-xs muted">{g.key}</span>
            </button>
          ))}
        </div>
      )}
      {grade.isError && <ErrorState message={grade.error.message} />}
      <p className="text-xs muted">Keyboard: Space shows the answer, then 1 Again · 2 Hard · 3 Good · 4 Easy.</p>
    </div>
  );
}

function Overview({ deck, topic, setTopic, onStart }: {
  deck: FlashcardDeckT; topic: string | null; setTopic: (t: string | null) => void; onStart: () => void;
}) {
  const queue = buildQueue(deck.cards, topic);
  const s = deck.stats;
  return (
    <div className="space-y-6">
      <section className="card p-5 space-y-4">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[["Due", s.due], ["New", s.new], ["Learned", s.learned], ["Total", s.total]].map(([k, v]) => (
            <div key={k}><dt className="text-xs muted">{k}</dt><dd className="text-2xl font-bold tabular-nums">{v}</dd></div>
          ))}
        </dl>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block muted mb-1">Topic</span>
            <select className="field" value={topic ?? ""} onChange={(e) => setTopic(e.target.value || null)}>
              <option value="">All topics</option>
              {deck.topics.map((t) => <option key={t.jd_id} value={t.jd_id}>{t.name}</option>)}
            </select>
          </label>
          <button className="btn" disabled={!queue.length} onClick={onStart}>
            {queue.length ? `Start review (${queue.length})` : "Nothing due"}
          </button>
          {!queue.length && s.next_due && <p className="text-sm muted">Next cards are due on {s.next_due}.</p>}
        </div>
      </section>
      <section aria-labelledby="topics-h">
        <h2 id="topics-h" className="font-semibold mb-2">By topic</h2>
        <ul className="card divide-y" style={{ borderColor: "var(--border)" }}>
          {deck.topics.map((t) => (
            <li key={t.jd_id} className="px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" style={{ borderColor: "var(--border)" }}>
              <Link className="font-medium hover:underline min-w-0 flex-1" to={`../topic/${t.jd_id}`} relative="path">{t.name}</Link>
              <span className="muted tabular-nums">{t.due} due · {t.new} new · {t.total} total</span>
              <button className="btn-ghost text-xs" onClick={() => setTopic(t.jd_id)}>Study this topic</button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function Flashcards() {
  const { result, id } = useAnalysisCtx();
  const [params, setParams] = useSearchParams();
  const topic = params.get("topic");
  const [session, setSession] = useState<FlashcardT[] | null>(null);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: keys.deck(id), queryFn: () => api.getDeck(id) });
  const names = Object.fromEntries(result.jd_items.map((i) => [i.id, i.name]));
  const setTopic = (t: string | null) => setParams(t ? { topic: t } : {}, { replace: true });

  if (q.isPending) return <LoadingState label="Loading flashcards…" />;
  if (q.isError) return <ErrorState message={q.error.message} onRetry={() => q.refetch()} />;
  if (!q.data.cards.length) {
    return (
      <EmptyState title="No flashcards yet">
        Open a topic and click <strong>Make flashcards</strong> under its notes. Start with the{" "}
        <Link className="underline" to=".." relative="path">Study next</Link> list.
      </EmptyState>
    );
  }
  if (session) {
    return (
      <Session analysisId={id} initial={session} names={names}
        onDone={() => { setSession(null); qc.invalidateQueries({ queryKey: keys.deck(id) }); }} />
    );
  }
  return <Overview deck={q.data} topic={topic} setTopic={setTopic} onStart={() => setSession(buildQueue(q.data.cards, topic))} />;
}
