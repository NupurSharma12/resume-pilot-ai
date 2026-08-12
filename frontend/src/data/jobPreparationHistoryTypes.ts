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

export interface JobPreparationDetail {
  id: string
  job_title: string
  company: string | null
  job_description: string
  resume_name: string
  status: string
  created_at: string
  updated_at: string
  checkpoints: CheckpointStatus
  analysis_result: Record<string, unknown> | null
  career_conversation: Record<string, unknown> | null
  tailoring_plan: Record<string, unknown> | null
  applied_resume_text: string | null
  post_apply_analysis: Record<string, unknown> | null
}
