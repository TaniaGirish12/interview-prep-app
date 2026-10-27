import type { z } from "zod";
import * as S from "../schemas";

export class ApiError extends Error {
  constructor(message: string, public status: number, public reason?: string) {
    super(message);
  }
}

async function request<T extends z.ZodType>(schema: T, path: string, init?: RequestInit): Promise<z.infer<T>> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Cannot reach the backend. Is it running on port 8000?", 0);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok && res.status !== 202) {
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${res.status}).`;
    throw new ApiError(detail, res.status, body?.reason);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    console.error("Response did not match schema", path, parsed.error);
    throw new ApiError("The server sent data in an unexpected format.", res.status);
  }
  return parsed.data;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  uploadResume(file: File) {
    const form = new FormData();
    form.append("file", file);
    return request(S.ResumeUpload, "/api/resume", { method: "POST", body: form });
  },
  saveResume(id: number, text: string) {
    return request(S.SavedResume, `/api/resume/${id}`, json("PUT", { text }));
  },
  addJob(input: { url?: string; text?: string }) {
    return request(S.JdResponse, "/api/jd", json("POST", input));
  },
  createAnalysis(body: {
    resume_id: number; jd_id: number; interview_date?: string | null; interview_time?: string | null;
    hours_per_day?: number | null;
  }) {
    return request(S.CreatedAnalysis, "/api/analyses", json("POST", body));
  },
  updateSchedule(id: number, body: { interview_date?: string | null; interview_time?: string | null; hours_per_day?: number | null }) {
    return request(S.ScheduleResponse, `/api/analyses/${id}`, json("PATCH", body));
  },
  listAnalyses() {
    return request(S.AnalysisListItem.array(), "/api/analyses");
  },
  getAnalysis(id: number) {
    return request(S.Analysis, `/api/analyses/${id}`);
  },
  retryAnalysis(id: number) {
    return fetch(`/api/analyses/${id}/retry`, { method: "POST" });
  },
  getTopic(id: number, jdId: string) {
    return request(S.TopicResponse, `/api/analyses/${id}/topics/${jdId}`);
  },
  openTopic(id: number, jdId: string) {
    return request(S.TopicResponse, `/api/analyses/${id}/topics/${jdId}/open`, { method: "POST" });
  },
  getGaps(id: number) {
    return request(S.GapsResponse, `/api/analyses/${id}/gaps`);
  },
  getPlan(id: number) {
    return request(S.StudyPlan, `/api/analyses/${id}/plan`);
  },
  markDone(id: number, body: { jd_id: string | null; kind: string; hours: number }) {
    return request(S.DoneResponse, `/api/analyses/${id}/plan/done`, json("POST", body));
  },
  undoDone(id: number, entryId: number) {
    return request(S.UndoResponse, `/api/analyses/${id}/plan/done/${entryId}`, { method: "DELETE" });
  },
  getTopicCards(id: number, jdId: string) {
    return request(S.TopicCards, `/api/analyses/${id}/topics/${jdId}/flashcards`);
  },
  makeTopicCards(id: number, jdId: string) {
    return request(S.TopicCards, `/api/analyses/${id}/topics/${jdId}/flashcards`, { method: "POST" });
  },
  getDeck(id: number) {
    return request(S.FlashcardDeck, `/api/analyses/${id}/flashcards`);
  },
  reviewCard(id: number, cardId: number, grade: string) {
    return request(S.Flashcard, `/api/analyses/${id}/flashcards/${cardId}/review`, json("POST", { grade }));
  },
  retryGaps(id: number) {
    return fetch(`/api/analyses/${id}/gaps/retry`, { method: "POST" });
  },
};
