// zod mirrors of the backend Pydantic schemas (backend/app/schemas) and API payloads.
// A contract test parses payloads written by pytest (shared/contract-fixtures).
import { z } from "zod";

export const JdId = z.string().regex(/^JD-[TRN]\d{2,3}$/);
export const CvId = z.string().regex(/^CV-\d{2,3}$/);
export const Label = z.enum(["fact", "prediction"]);
export const Status = z.enum(["strong", "partial", "gap"]);
export const Tier = z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]);

export const JDItem = z.object({
  id: JdId,
  category: z.enum(["task", "requirement", "nice_to_have"]),
  kind: z.enum(["responsibility", "skill", "language", "tool", "technology",
    "domain", "qualification", "soft_skill", "formal"]),
  name: z.string(),
  quote: z.string().min(3).max(400),
  section: z.string(),
}).strict();

export const RankedRequirement = z.object({
  jd_id: JdId, tier: Tier, reason: z.string(), skill_area: z.string(),
}).strict();

export const CVItem = z.object({
  id: CvId,
  category: z.enum(["role", "project", "skill", "achievement", "education", "certification"]),
  title: z.string(),
  context: z.string().nullable(),
  quote: z.string(),
}).strict();

export const Evidence = z.object({ cv_id: CvId, quote: z.string() }).strict();

export const Match = z.object({
  jd_id: JdId,
  status: Status,
  evidence: z.array(Evidence),
  rationale: z.string(),
  confidence: z.number().min(0).max(1),
  downgraded: z.boolean(),
}).strict();

export const Dropped = z.object({
  step: z.string(), reason: z.string(), item: z.record(z.string(), z.unknown()),
});

export const StudyNext = z.object({
  jd_id: JdId, name: z.string(), tier: Tier, status: Status,
  confidence: z.number(), priority: z.number(),
});

export const Scores = z.object({
  match_score: z.number().nullable(),
  radar: z.array(z.object({ area: z.string(), score: z.number(), count: z.number() })),
  tier_status: z.array(z.object({ tier: Tier, strong: z.number(), partial: z.number(), gap: z.number() })),
  study_next: z.array(StudyNext),
});

export const TopicStatus = z.enum(["ready", "queued", "generating", "error", "not_started"]);

export const Cost = z.object({
  calls: z.number(), usd: z.number(), input: z.number(), output: z.number(),
  cache_read: z.number(), cache_write: z.number(),
});

export const AnalysisResult = z.object({
  meta: z.object({
    role_title: z.string(), company_name: z.string().nullable(),
    location: z.string().nullable(), employment_type: z.string().nullable(),
  }),
  about_company: z.array(z.string()),
  jd_items: z.array(JDItem),
  skill_areas: z.array(z.string()),
  rankings: z.record(z.string(), RankedRequirement),
  cv_items: z.array(CVItem),
  matches: z.record(z.string(), Match),
  defaulted: z.object({ rank: z.array(JdId), match: z.array(JdId) }),
  dropped: z.array(Dropped),
  scores: Scores,
  topics: z.record(z.string(), TopicStatus),
});

export const Schedule = z.object({
  days_until: z.number(),
  hours_until: z.number().nullable(),
  past: z.boolean(),
  study_days: z.number(),
  review_hours: z.number(),
  total_hours: z.number().nullable(),
});

export const Analysis = z.object({
  id: z.number(),
  status: z.enum(["pending", "running", "done", "error"]),
  error: z.string().nullable(),
  interview_date: z.string().nullable(),
  interview_time: z.string().nullable(),
  hours_per_day: z.number().nullable(),
  schedule: Schedule.nullable(),
  created_at: z.string(),
  model: z.string(),
  jd: z.object({
    url: z.string().nullable(), title: z.string().nullable(),
    company: z.string().nullable(), source: z.string(),
  }),
  resume: z.object({ filename: z.string().nullable() }),
  cost: Cost,
  backend: z.enum(["api", "claude-code"]),
  gxx_available: z.boolean(),
  result: AnalysisResult.nullable(),
});

export const CodeCheck = z.object({
  status: z.enum(["verified", "not_verified"]), tool: z.string(), detail: z.string().nullable(),
}).strict();

export const CodeExample = z.object({
  language: z.enum(["cpp", "python"]),
  title: z.string(),
  code: z.string(),
  runnable: z.boolean(),
  explanation: z.string(),
  jd_ids: z.array(JdId).min(1),
  check: CodeCheck,
}).strict();

export const Bullet = z.object({ text: z.string(), label: Label, jd_ids: z.array(JdId).min(1) }).strict();

export const LikelyQuestion = z.object({
  question: z.string(),
  model_answer: z.string(),
  difficulty: z.enum(["warm-up", "core", "deep"]),
  label: z.literal("prediction"),
  jd_ids: z.array(JdId).min(1),
}).strict();

export const TopicContent = z.object({
  jd_id: JdId,
  title: z.string(),
  explanation: z.array(z.object({
    level: z.enum(["fundamentals", "intermediate", "interview"]),
    heading: z.string(),
    body_md: z.string(),
  }).strict()),
  diagram: z.object({
    kind: z.enum(["flowchart", "stateDiagram", "sequenceDiagram", "classDiagram"]),
    mermaid: z.string(),
    description: z.string(),
  }).strict().nullable(),
  code_examples: z.array(CodeExample),
  common_mistakes: z.array(Bullet),
  real_world_use: z.array(Bullet),
  likely_questions: z.array(LikelyQuestion),
}).strict();

export const TopicResponse = z.discriminatedUnion("status", [
  z.object({ status: z.literal("ready"), content: TopicContent }),
  z.object({ status: z.literal("queued"), position: z.number().nullable().optional() }),
  z.object({ status: z.literal("generating") }),
  z.object({ status: z.literal("not_started") }),
  z.object({ status: z.literal("error"), error: z.string().nullable().optional() }),
]);

export const GapsResponse = z.discriminatedUnion("status", [
  z.object({
    status: z.literal("ready"),
    plans: z.array(z.object({
      jd_id: JdId,
      steps: z.array(z.object({
        order: z.number(), what: z.string(), why: z.string(), est_hours: z.number(), jd_ids: z.array(JdId),
      }).strict()),
    }).strict()),
  }),
  z.object({ status: z.literal("generating") }),
  z.object({ status: z.literal("not_started") }),
  z.object({ status: z.literal("error"), error: z.string() }),
]);

export const ResumeUpload = z.object({
  resume_id: z.number(), text: z.string(), extractor: z.string(),
  page_count: z.number(), filename: z.string().nullable(),
});

export const SavedResume = z.object({ resume_id: z.number(), text: z.string() });

export const CreatedAnalysis = z.object({ analysis_id: z.number(), reused: z.boolean() });

export const JdResponse = z.object({
  jd_id: z.number(), text: z.string(), source: z.enum(["json-ld", "main-content", "pasted"]),
  title: z.string().nullable(), company: z.string().nullable(), url: z.string().nullable(),
});

export const AnalysisListItem = z.object({
  id: z.number(),
  status: z.enum(["pending", "running", "done", "error"]),
  created_at: z.string(),
  interview_date: z.string().nullable(),
  interview_time: z.string().nullable(),
  hours_per_day: z.number().nullable(),
  title: z.string().nullable(),
  company: z.string().nullable(),
  filename: z.string().nullable(),
  match_score: z.number().nullable(),
});

export const ScheduleResponse = z.object({
  analysis_id: z.number(), interview_date: z.string().nullable(), interview_time: z.string().nullable(),
  hours_per_day: z.number().nullable(), schedule: Schedule.nullable(),
});

const PlanKind = z.enum(["learn", "practise", "review", "final"]);

export const PlanBlock = z.object({
  id: z.string(),
  jd_id: JdId.nullable(),
  name: z.string(),
  tier: Tier.nullable(),
  status: Status.nullable(),
  kind: PlanKind,
  hours: z.number(),
  label: z.string(),
});

export const DoneResponse = z.object({ id: z.number() });
export const UndoResponse = z.object({ deleted: z.number() });

export const StudyPlan = z.object({
  missing: z.array(z.enum(["interview_date", "hours_per_day"])),
  past: z.boolean(),
  needed_hours: z.number(),
  available_hours: z.number(),
  scheduled_hours: z.number(),
  days: z.array(z.object({
    date: z.string(), interview_day: z.boolean(), capacity_hours: z.number(), used_hours: z.number(),
    blocks: z.array(PlanBlock),
  })),
  unscheduled: z.array(z.object({ jd_id: JdId, name: z.string(), tier: Tier, status: Status, hours: z.number() })),
  today: z.string(),
  budget: Schedule.nullable(),
  uses_gap_plan: z.boolean(),
  done_today: z.array(z.object({
    id: z.number(), jd_id: JdId.nullable(), kind: PlanKind, hours: z.number(), name: z.string(),
  }).passthrough()),
  done_hours_total: z.number(),
  cards_due: z.record(z.string(), z.number()),
});

export const Grade = z.enum(["again", "hard", "good", "easy"]);

export const Flashcard = z.object({
  id: z.number(),
  jd_id: JdId,
  kind: z.enum(["concept", "question", "mistake", "code"]),
  front: z.string(),
  back: z.string(),
  label: Label,
  jd_ids: z.array(JdId),
  reps: z.number(),
  lapses: z.number(),
  interval_days: z.number(),
  due: z.string().nullable(),
  last_grade: Grade.nullable(),
  is_new: z.boolean(),
  is_due: z.boolean(),
});

export const FlashcardDeck = z.object({
  today: z.string(),
  cards: z.array(Flashcard),
  topics: z.array(z.object({
    jd_id: JdId, name: z.string(), tier: Tier.nullable(), total: z.number(), due: z.number(), new: z.number(),
  })),
  stats: z.object({
    total: z.number(), new: z.number(), due: z.number(), learned: z.number(), next_due: z.string().nullable(),
  }),
});

export const TopicCards = z.object({
  status: z.enum(["none", "generating", "ready", "error"]),
  count: z.number(),
  error: z.string().optional(),
});

export type JDItem = z.infer<typeof JDItem>;
export type StudyPlanT = z.infer<typeof StudyPlan>;
export type FlashcardT = z.infer<typeof Flashcard>;
export type GradeT = z.infer<typeof Grade>;
export type FlashcardDeckT = z.infer<typeof FlashcardDeck>;
export type PlanBlockT = z.infer<typeof PlanBlock>;
export type CVItem = z.infer<typeof CVItem>;
export type Match = z.infer<typeof Match>;
export type RankedRequirement = z.infer<typeof RankedRequirement>;
export type Analysis = z.infer<typeof Analysis>;
export type AnalysisResult = z.infer<typeof AnalysisResult>;
export type TopicContent = z.infer<typeof TopicContent>;
export type TopicResponse = z.infer<typeof TopicResponse>;
export type GapsResponse = z.infer<typeof GapsResponse>;
export type CodeExample = z.infer<typeof CodeExample>;
export type StatusT = z.infer<typeof Status>;
export type TopicStatusT = z.infer<typeof TopicStatus>;
export type Cost = z.infer<typeof Cost>;
export type AnalysisListItem = z.infer<typeof AnalysisListItem>;
export type ScheduleT = z.infer<typeof Schedule>;
