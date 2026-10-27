import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { ScheduleCard } from "../components/ScheduleCard";
import { groupInterviews, Sidebar } from "../components/Sidebar";
import { relativeDay } from "../lib/dates";
import type { AnalysisListItem } from "../schemas";

const TODAY = new Date(2026, 9, 23); // 23 Oct 2026, local time

const item = (id: number, interview_date: string | null, extra: Partial<AnalysisListItem> = {}): AnalysisListItem => ({
  id, status: "done", created_at: "2026-10-01T00:00:00+00:00", interview_date, interview_time: null, hours_per_day: null,
  title: `Role ${id}`, company: "Co", filename: "cv.pdf", match_score: 50, ...extra,
});

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe("groupInterviews", () => {
  it("orders upcoming soonest first, then undated, then past most recent first", () => {
    const groups = groupInterviews(
      [item(1, "2026-11-20"), item(2, null), item(3, "2026-10-01"), item(4, "2026-10-23"), item(5, "2026-09-01")],
      TODAY,
    );
    expect(groups.map((g) => [g.title, g.items.map((i) => i.id)])).toEqual([
      ["Upcoming", [4, 1]],
      ["No date set", [2]],
      ["Past", [3, 5]],
    ]);
  });

  it("describes dates relative to today", () => {
    expect(relativeDay("2026-10-23", TODAY)).toBe("Today");
    expect(relativeDay("2026-10-24", TODAY)).toBe("Tomorrow");
    expect(relativeDay("2026-11-02", TODAY)).toBe("In 10 days");
    expect(relativeDay("2026-10-20", TODAY)).toBe("3 days ago");
    expect(relativeDay(null, TODAY)).toBe("No date set");
  });
});

describe("Sidebar", () => {
  it("lists interviews with links, match score and status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([
      item(1, null, { title: "C++ Intern", company: "MBition", match_score: 47.4 }),
      item(2, null, { title: "Backend Dev", status: "error", match_score: null }),
    ]))));
    wrap(<Sidebar />);
    const link = await screen.findByRole("link", { name: /C\+\+ Intern/ });
    expect(link).toHaveAttribute("href", "/a/1");
    expect(link).toHaveTextContent("47% match");
    expect(screen.getByRole("link", { name: /Backend Dev/ })).toHaveTextContent("Analysis failed");
    expect(screen.getByRole("link", { name: "+ New interview" })).toHaveAttribute("href", "/");
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]")));
    wrap(<Sidebar />);
    expect(await screen.findByText(/No interviews yet/)).toBeInTheDocument();
  });
});

describe("ScheduleCard", () => {
  it("shows the study time the backend computed", () => {
    wrap(<ScheduleCard analysisId={3} interviewDate="2099-01-10" interviewTime="15:00" hoursPerDay={3}
      schedule={{ days_until: 4, hours_until: 100, past: false, study_days: 4, review_hours: 2, total_hours: 14 }} />);
    expect(screen.getByText("14 h")).toBeInTheDocument();
    expect(screen.getByText(/4 study days × 3 h \+ 2 h review on the interview morning/)).toBeInTheDocument();
  });

  it("asks for the time and hours when they are missing", () => {
    wrap(<ScheduleCard analysisId={3} interviewDate="2099-01-10" interviewTime={null} hoursPerDay={null}
      schedule={{ days_until: 4, hours_until: null, past: false, study_days: 4, review_hours: 0, total_hours: null }} />);
    expect(screen.getByText(/Add your hours per day/)).toBeInTheDocument();
    expect(screen.getByText(/Add the interview time/)).toBeInTheDocument();
  });

  it("sets an interview date and sends only date and hours", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(
      { analysis_id: 3, interview_date: "2026-12-01", interview_time: "14:30", hours_per_day: 2, schedule: null })));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    wrap(<ScheduleCard analysisId={3} interviewDate={null} interviewTime={null} hoursPerDay={null} schedule={null} />);
    expect(screen.getByText("No interview date set yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Set date" }));
    await user.type(screen.getByLabelText("Interview date"), "2026-12-01");
    await user.type(screen.getByLabelText("Interview time"), "14:30");
    await user.type(screen.getByLabelText("Hours available per day"), "2");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/analyses/3");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ interview_date: "2026-12-01", interview_time: "14:30", hours_per_day: 2 });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument());
  });
});
