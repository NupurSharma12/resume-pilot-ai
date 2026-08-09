// Mirrors the FastAPI backend's Post-Apply Analysis Loop response shapes
// field-for-field (src/app/api/v1/models/tailoring_suggestions.py's
// Reanalyze*/ResumeAnalysisComparisonResponse/SkillCategoryComparisonResponse,
// backed by src/app/models/analysis_comparison.py) -- same convention as
// tailoringSuggestionsTypes.ts, so a real API response body needs no
// reshaping. See docs/features/postapply-analysis-loop.md.

import type { ResumeAnalysisResult } from './types'

// Computed purely from after_score vs. before_score on the backend
// (app.analysis.comparison.compute_resume_analysis_comparison) -- never
// an LLM's opinion. 'unchanged' and 'decreased' are first-class outcomes
// the UI must present honestly, never folded into a success message.
export type ComparisonStatus = 'improved' | 'unchanged' | 'decreased'

export interface SkillCategoryComparison {
  category: string
  score_before: number
  score_after: number
  score_delta: number
  status: ComparisonStatus
  newly_matched_skills: string[]
  newly_missing_skills: string[]
}

export interface ResumeAnalysisComparison {
  score_before: number
  score_after: number
  score_delta: number
  status: ComparisonStatus
  category_comparisons: SkillCategoryComparison[]
  strengths_gained: string[]
  strengths_lost: string[]
  weaknesses_resolved: string[]
  weaknesses_remaining: string[]
  new_weaknesses: string[]
}

export interface ReanalyzeResponse {
  after_analysis: ResumeAnalysisResult
  comparison: ResumeAnalysisComparison
}
