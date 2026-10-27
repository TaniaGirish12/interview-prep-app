import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { StudyPlan } from "../pages/StudyPlan";
import { Analysis, StudyPlan as PlanSchema } from "../schemas";

const fixtures = resolve(__dirname, "../../../shared/contract-fixtures");
const load = (name: string) => JSON.parse(readFileSync(resolve(fixtures, name), "utf8"));
const analysis = Analysis.parse(load("analysis.json"));
const planJson = load("plan.json");

function renderPlan(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ctx = { analysis, result: analysis.result!, id: 1 };
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/a/1/plan"]}>
        <Routes>
          <Route path="/a/:id" element={<Outlet context={ctx} />}>
            <Route path="plan" element={<StudyPlan />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

it("plan payload from the backend parses", () => {
  const plan = PlanSchema.parse(planJson);
  expect(plan.days.length).toBeGreaterThan(0);
  expect(plan.days.at(-1)?.interview_day).toBe(true);
});

it("renders the timeline and marks a block done", async () => {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
    Promise.resolve(new Response(JSON.stringify(init?.method === "POST" ? { id: 9 } : planJson))));
  const user = userEvent.setup();
  renderPlan(fetchMock);

  const timeline = await screen.findByRole("list", { name: "Day by day" });
  expect(within(timeline).getByRole("region", { name: /^Interview day/ })).toBeInTheDocument();
  expect(screen.getByText("Time left")).toBeInTheDocument();

  const first = planJson.days[0].blocks[0];
  const done = within(timeline).getAllByRole("button", { name: /^Mark done:/ })[0];
  await user.click(done);
  await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(true));
  const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
  expect(url).toBe("/api/analyses/1/plan/done");
  expect(JSON.parse(init!.body as string)).toEqual({ jd_id: first.jd_id, kind: first.kind, hours: first.hours });
});

it("asks for the date and hours when they are missing", async () => {
  const missing = { ...planJson, missing: ["interview_date", "hours_per_day"], days: [] };
  renderPlan(vi.fn().mockResolvedValue(new Response(JSON.stringify(missing))));
  expect(await screen.findByText(/add your interview date and hours per day/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Countdown" })).toBeInTheDocument();
});
