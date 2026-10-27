import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { keys } from "../api/hooks";
import type { ScheduleT } from "../schemas";
import { Countdown, formatTime } from "./Widgets";

type Props = {
  analysisId: number;
  interviewDate: string | null;
  interviewTime: string | null;
  hoursPerDay: number | null;
  schedule: ScheduleT | null;
};

/** How much study time is left, from the numbers the backend computes. */
function StudyBudget({ schedule, hoursPerDay, interviewTime }: Omit<Props, "analysisId" | "interviewDate">) {
  if (!schedule || schedule.past) return null;
  const days = `${schedule.study_days} study ${schedule.study_days === 1 ? "day" : "days"}`;
  return (
    <div className="mt-3 pt-3 border-t text-sm space-y-1" style={{ borderColor: "var(--border)" }}>
      {schedule.total_hours !== null && hoursPerDay ? (
        <p>
          <span className="font-semibold tabular-nums">{schedule.total_hours} h</span> of study time:{" "}
          <span className="muted">
            {days} × {hoursPerDay} h
            {schedule.review_hours > 0 && ` + ${schedule.review_hours} h review on the interview morning`}
          </span>
        </p>
      ) : (
        <p className="muted">{days}. Add your hours per day to see your total study time.</p>
      )}
      {!interviewTime && <p className="muted">Add the interview time for an exact countdown and to plan the interview day.</p>}
      {interviewTime && schedule.review_hours === 0 && schedule.study_days > 0 && (
        <p className="muted">The interview is at {formatTime(interviewTime)}, so the interview day isn't counted as study time.</p>
      )}
    </div>
  );
}

/** Countdown to the interview, with an inline editor for date, time and daily hours. */
export function ScheduleCard({ analysisId, interviewDate, interviewTime, hoursPerDay, schedule }: Props) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [date, setDate] = useState(interviewDate ?? "");
  const [time, setTime] = useState(interviewTime ?? "");
  const [hours, setHours] = useState(hoursPerDay?.toString() ?? "");

  const save = useMutation({
    mutationFn: (body: { interview_date: string | null; interview_time: string | null; hours_per_day: number | null }) =>
      api.updateSchedule(analysisId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.analysis(analysisId) });
      qc.invalidateQueries({ queryKey: keys.list });
      qc.invalidateQueries({ queryKey: keys.plan(analysisId) });
      setEditing(false);
    },
  });

  const startEditing = () => {
    setDate(interviewDate ?? "");
    setTime(interviewTime ?? "");
    setHours(hoursPerDay?.toString() ?? "");
    save.reset();
    setEditing(true);
  };
  const hoursValue = hours ? Number(hours) : null;

  return (
    <section className="card p-5" aria-labelledby="count-h">
      <div className="flex items-center gap-2 mb-2">
        <h2 id="count-h" className="font-semibold">Countdown</h2>
        {!editing && (
          <button className="btn-ghost ml-auto text-xs no-print" onClick={startEditing}>
            {interviewDate ? "Edit" : "Set date"}
          </button>
        )}
      </div>

      {editing ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ interview_date: date || null, interview_time: date && time ? time : null, hours_per_day: hoursValue });
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="block mb-1">Interview date</span>
              <input className="field" type="date" value={date} onChange={(e) => setDate(e.target.value)} autoFocus />
            </label>
            <label className="block text-sm">
              <span className="block mb-1">Interview time</span>
              <input className="field" type="time" value={time} disabled={!date} onChange={(e) => setTime(e.target.value)} />
            </label>
          </div>
          <label className="block text-sm">
            <span className="block mb-1">Hours available per day</span>
            <input className="field" type="number" min={0.5} max={16} step={0.5} value={hours}
              onChange={(e) => setHours(e.target.value)} />
          </label>
          {save.isError && <p className="text-sm" role="alert" style={{ color: "var(--gap)" }}>{save.error.message}</p>}
          <div className="flex flex-wrap gap-2">
            <button className="btn" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</button>
            <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            {interviewDate && (
              <button type="button" className="btn-ghost ml-auto" disabled={save.isPending}
                onClick={() => save.mutate({ interview_date: null, interview_time: null, hours_per_day: hoursValue })}>
                Clear date
              </button>
            )}
          </div>
        </form>
      ) : (
        <>
          <Countdown date={interviewDate} time={interviewTime} />
          <StudyBudget schedule={schedule} hoursPerDay={hoursPerDay} interviewTime={interviewTime} />
        </>
      )}
    </section>
  );
}
