// Mirrors the FastAPI backend's History response shapes field-for-field
// (src/app/api/v1/models/job_preparation_history.py) -- same convention
// as tailoringSuggestionsTypes.ts/postApplyTypes.ts, so a real API
// response body needs no reshaping.

// A checkpoint is complete iff its own field here is non-null -- never
// inferred from any other field's shape. Five, not four: "Tailored
// Resume" and "Re-analysis" are tracked separately since Apply and
// Reanalyze are independent requests that can succeed or fail
// independently of each other (see the backend's own docstring).
export interface CheckpointStatus {
  initial_analysis_completed_at: string | null
  career_conversation_completed_at: string | null
  tailoring_plan_completed_at: string | null
  applied_at: string | null
  post_apply_analysis_completed_at: string | null
}

export interface JobPreparationSummary {
  id: string
  job_title: string
  company: string | null
  resume_name: string
  created_at: string
  updated_at: string
  checkpoints: CheckpointStatus
}

// Mirrors POST /v1/job-preparations/{id}/interview-preparation's response
// field-for-field (src/app/api/v1/models/interview_preparation.py) -- and,
// since `record_interview_preparation` persists that exact same shape
// (see the orchestration module), also what `JobPreparationDetail.
// interview_preparation` holds once generated. Typed here (unlike the
// other JSONB fields below, kept as `Record<string, unknown>`) because
// this is a brand-new payload with no pre-existing domain model to avoid
// duplicating -- see this feature's own scope decision.
export interface SystemDesignQuestion {
  question: string
  rationale: string
}

export interface CodingQuestion {
  title: string
  topic: string
  difficulty: string
  relevance: string
}

export interface BehavioralQuestion {
  question: string
  source: 'career_conversation' | 'suggested'
  context: string | null
}

// The three-stage Interview Preparation lifecycle (see
// InterviewPreparationStage on the backend): 'initial' (resume + job
// description alone), 'career_conversation_enriched' (behavioral
// questions folded in from the completed Career Conversation),
// 'tailoring_aligned' (system-design/coding questions regenerated
// against the actually applied resume). Drives the maturity label shown
// on both History's card and the active Interview Preparation page --
// see interviewPreparationStageLabel.ts.
export type InterviewPreparationStage =
  | 'initial'
  | 'career_conversation_enriched'
  | 'tailoring_aligned'

export interface InterviewPreparation {
  system_design_questions: SystemDesignQuestion[]
  coding_questions: CodingQuestion[]
  behavioral_questions: BehavioralQuestion[]
  generated_at: string
  stage: InterviewPreparationStage
}

export interface JobPreparationDetail {
  id: string
  job_title: string
  company: string | null
  job_description: string
  resume_name: string
  resume_text: string
  status: string
  created_at: string
  updated_at: string
  checkpoints: CheckpointStatus
  analysis_result: Record<string, unknown> | null
  career_conversation: Record<string, unknown> | null
  tailoring_plan: Record<string, unknown> | null
  applied_resume_text: string | null
  post_apply_analysis: Record<string, unknown> | null
  interview_preparation: InterviewPreparation | null
}
