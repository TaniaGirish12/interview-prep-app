import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { TopicFlashcards } from "../components/TopicFlashcards";
import { buildQueue, Flashcards } from "../pages/Flashcards";
import { Analysis, FlashcardDeck, type FlashcardT } from "../schemas";

const fixtures = resolve(__dirname, "../../../shared/contract-fixtures");
const load = (name: string) => JSON.parse(readFileSync(resolve(fixtures, name), "utf8"));
const analysis = Analysis.parse(load("analysis.json"));

const card = (id: number, extra: Partial<FlashcardT> = {}): FlashcardT => ({
  id, jd_id: "JD-T02", kind: "concept", front: `Front ${id}`, back: `Back ${id}`, label: "prediction",
  jd_ids: ["JD-T02"], reps: 0, lapses: 0, interval_days: 0, due: null, last_grade: null, is_new: true, is_due: true,
  ...extra,
});

function wrap(ui: React.ReactNode, path = "/a/1/cards") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ctx = { analysis, result: analysis.result!, id: 1 };
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/a/:id" element={<Outlet context={ctx} />}>
            <Route path="cards" element={ui} />
            <Route path="topic/:jdId" element={ui} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("deck payload from the backend parses", () => {
  expect(FlashcardDeck.parse(load("flashcards.json")).cards.length).toBeGreaterThan(0);
});

it("queues due reviews before new cards, and filters by topic", () => {
  const cards = [card(1), card(2, { is_new: false, due: "2026-10-20" }), card(3, { is_due: false, is_new: false }),
    card(4, { jd_id: "JD-R01", jd_ids: ["JD-R01"] })];
  expect(buildQueue(cards, null).map((c) => c.id)).toEqual([2, 1, 4]);
  expect(buildQueue(cards, "JD-R01").map((c) => c.id)).toEqual([4]);
});

it("reviews with the keyboard; Again brings the card back", async () => {
  const deck = { today: "2026-10-23", cards: [card(1), card(2)], topics: [
    { jd_id: "JD-T02", name: "Threads", tier: 1, total: 2, due: 0, new: 2 }],
    stats: { total: 2, new: 2, due: 0, learned: 0, next_due: null } };
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const id = Number(url.split("/").at(-2));
      const grade = JSON.parse(init.body as string).grade;
      return Promise.resolve(new Response(JSON.stringify(
        card(id, { is_new: false, is_due: grade === "again", reps: grade === "again" ? 0 : 1 }))));
    }
    return Promise.resolve(new Response(JSON.stringify(deck)));
  });
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  wrap(<Flashcards />);

  await user.click(await screen.findByRole("button", { name: "Start review (2)" }));
  expect(screen.getByText("Front 1")).toBeInTheDocument();
  expect(screen.queryByText("Back 1")).not.toBeInTheDocument();
  await user.keyboard(" ");
  expect(screen.getByText("Back 1")).toBeInTheDocument();
  await user.keyboard("1"); // Again
  await waitFor(() => expect(screen.getByText("Front 2")).toBeInTheDocument());
  await user.keyboard(" ");
  await user.keyboard("3"); // Good
  await waitFor(() => expect(screen.getByText("Front 1")).toBeInTheDocument()); // came back
  await user.keyboard(" ");
  await user.keyboard("4"); // Easy
  await waitFor(() => expect(screen.getByText(/Session done: 3 reviews/)).toBeInTheDocument());
  const grades = fetchMock.mock.calls.filter(([, i]) => i?.method === "POST").map(([u, i]) => [u, JSON.parse(i!.body as string).grade]);
  expect(grades).toEqual([
    ["/api/analyses/1/flashcards/1/review", "again"],
    ["/api/analyses/1/flashcards/2/review", "good"],
    ["/api/analyses/1/flashcards/1/review", "easy"],
  ]);
});

it("makes cards for a topic only when clicked", async () => {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => Promise.resolve(new Response(JSON.stringify(
    init?.method === "POST" ? { status: "generating", count: 0 } : { status: "none", count: 0 }))));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  wrap(<TopicFlashcards analysisId={1} jdId="JD-T02" />, "/a/1/topic/JD-T02");
  const button = await screen.findByRole("button", { name: "Make flashcards" });
  expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);
  await user.click(button);
  await waitFor(() => expect(screen.getByText(/Making flashcards from these notes/)).toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledWith("/api/analyses/1/topics/JD-T02/flashcards", { method: "POST" });
});
