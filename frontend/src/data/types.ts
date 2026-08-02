import type { ColorTheme } from './theme'

// Candidate identity/profile fields — not part of the backend's resume
// analysis response, so kept separate from ResumeAnalysisResult.
export interface Candidate {
  name: string
  initials: string
  title: string
  company: string
  yearsExperience: number
  rating: number
}

// The types below mirror the FastAPI backend's response shape field-for-
// field (src/app/models/resume_analysis.py), snake_case included, so that
// `mockResumeAnalysis` in mockData.ts can be replaced by a real API
// response body with no reshaping.

export interface HiringRecommendation {
  decision: string
  reason: string
}

export interface OverallAssessment {
  overall_score: number
  hiring_recommendation: HiringRecommendation
  summary: string
}

export interface SkillMatch {
  category: string
  score: number
  matched_skills: string[]
  missing_skills: string[]
}

export interface MatchingProject {
  title: string
  relevance_score: number
  reason: string
}

export interface ResumeImprovement {
  section: string
  recommendation: string
  priority: number
}

export interface ResumeAnalysisResult {
  overall_assessment: OverallAssessment
  skill_matches: SkillMatch[]
  matching_projects: MatchingProject[]
  strengths: string[]
  weaknesses: string[]
  resume_improvements: ResumeImprovement[]
}

// Frontend-only: narrative text the backend's SkillMatch doesn't carry yet
// (only category/score/matched_skills/missing_skills). Kept as its own
// type — distinct from SkillMatch — so it's obvious at a glance which
// fields are real backend data and which are still mocked supplementary
// copy (see mockData.ts `skillMatchNarratives`).
export interface SkillMatchNarrative {
  recruiterSummary: string
  aiSummary: string
  recommendation: string
}

// Frontend-only: pairs a real SkillMatch with a display color assigned by
// position (the backend has no concept of "theme"), so components never
// need to hardcode which category gets which color.
export interface ThemedSkillMatch {
  skillMatch: SkillMatch
  theme: ColorTheme
}
