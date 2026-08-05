// Mirrors the FastAPI backend's Tailoring Engine response shape
// field-for-field (src/app/api/v1/models/tailor_resume.py), snake_case
// included — same convention as ResumeAnalysisResult/ConversationSessionState
// in types.ts/careerConversationTypes.ts, so a real API response body
// needs no reshaping.

export type TailoringAction = 'rewrite' | 'expand' | 'reorder' | 'trim' | 'add_emphasis' | 'remove'

export interface PlannedChange {
  section: string
  action: TailoringAction
  reason: string
  evidence_ids: string[]
}

export interface TailoringPlan {
  changes: PlannedChange[]
}

export interface TailoredBullet {
  text: string
  supporting_evidence_ids: string[]
}

export interface TailoredSection {
  heading: string
  bullets: TailoredBullet[]
}

export interface TailoredResume {
  sections: TailoredSection[]
}

export interface RejectedBullet {
  section: string
  text: string
  reason: string
}

export interface ValidationReport {
  total_bullets: number
  accepted_count: number
  rejected_count: number
  rejected_bullets: RejectedBullet[]
  passed: boolean
}

export interface TailorResumeResult {
  tailored_resume: TailoredResume
  tailoring_plan: TailoringPlan
  validation_report: ValidationReport
}
