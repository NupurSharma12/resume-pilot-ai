import type { ColorTheme } from './theme'

// The view-model the candidate identity UI renders. Built from the
// backend's `candidate_profile` by `toCandidate` (data/candidate.ts) --
// `initials` is derived there rather than sent by the backend, which is
// why this is a separate type from `CandidateProfile` below and not just
// an alias for it.
//
// `title`/`company`/`yearsExperience` are nullable because the underlying
// resume genuinely may not state them; components render a neutral
// fallback rather than inventing a value. There is deliberately no
// `rating` field: nothing in this application evaluates a candidate on a
// star scale, and the previous hardcoded 4.5 was a placeholder that
// rendered identically for every resume.
export interface Candidate {
  name: string
  initials: string
  title: string | null
  company: string | null
  yearsExperience: number | null
}

// The types below mirror the FastAPI backend's response shape field-for-
// field (src/app/models/resume_analysis.py), snake_case included, so that
// `mockResumeAnalysis` in mockData.ts can be replaced by a real API
// response body with no reshaping.

export interface CandidateProfile {
  name: string
  current_company: string | null
  title: string | null
  years_experience: number | null
}

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
  // Optional, and null for every analysis persisted before this field
  // existed -- the backend's matching field defaults to None precisely so
  // those historical records keep parsing (see resume_analysis.py).
  candidate_profile?: CandidateProfile | null
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
