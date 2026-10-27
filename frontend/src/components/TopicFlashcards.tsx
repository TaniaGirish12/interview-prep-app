import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { keys } from "../api/hooks";

/** Make flashcards for one topic. Nothing is generated until the user clicks. */
export function TopicFlashcards({ analysisId, jdId }: { analysisId: number; jdId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: keys.topicCards(analysisId, jdId),
    queryFn: () => api.getTopicCards(analysisId, jdId),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? 3000 : false),
  });
  const make = useMutation({
    mutationFn: () => api.makeTopicCards(analysisId, jdId),
    onSuccess: (data) => qc.setQueryData(keys.topicCards(analysisId, jdId), data),
  });
  const ready = q.data?.status === "ready";
  useEffect(() => {
    if (ready) qc.invalidateQueries({ queryKey: keys.deck(analysisId) });  // new cards appear in the deck
  }, [ready, analysisId, qc]);

  return (
    <section className="card p-5 flex flex-wrap items-center gap-3 no-print" aria-labelledby="cards-h">
      <div className="min-w-0 flex-1">
        <h3 id="cards-h" className="font-semibold">Flashcards</h3>
        <p className="text-sm muted" aria-live="polite">
          {q.isPending ? "Checking…"
            : ready ? `${q.data!.count} cards made from these notes.`
              : q.data?.status === "generating" ? "Making flashcards from these notes… (about half a minute)"
                : q.data?.status === "error" ? `Making flashcards failed: ${q.data.error ?? "unknown error"}`
                  : "Turn these notes into spaced-repetition cards. Uses one model call."}
        </p>
        {make.isError && <p className="text-sm" role="alert" style={{ color: "var(--gap)" }}>{make.error.message}</p>}
      </div>
      {ready ? (
        <Link className="btn" to={`../../cards?topic=${jdId}`} relative="path">Study these cards</Link>
      ) : q.data?.status === "generating" ? (
        <span className="size-4 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />
      ) : (
        <button className="btn" onClick={() => make.mutate()} disabled={make.isPending || q.isPending}>
          {q.data?.status === "error" ? "Try again" : "Make flashcards"}
        </button>
      )}
    </section>
  );
}
