// Payloads written by the backend test suite (backend/tests/test_pipeline_mocked.py)
// must parse with the zod schemas, so the two sides cannot drift apart silently.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { Analysis, TopicResponse } from "../schemas";

const dir = resolve(__dirname, "../../../shared/contract-fixtures");
const load = (name: string) => JSON.parse(readFileSync(resolve(dir, name), "utf8"));

describe("backend ↔ frontend contract", () => {
  it("analysis payload parses", () => {
    const parsed = Analysis.parse(load("analysis.json"));
    expect(parsed.result?.jd_items.length).toBeGreaterThan(0);
    expect(parsed.result?.scores.study_next[0].jd_id).toMatch(/^JD-/);
  });

  it("topic payload parses", () => {
    const parsed = TopicResponse.parse(load("topic.json"));
    expect(parsed.status).toBe("ready");
  });

  it("rejects payloads with unknown fields", () => {
    const topic = load("topic.json");
    topic.content.unexpected = 1;
    expect(TopicResponse.safeParse(topic).success).toBe(false);
  });
});
