// Converts the backend's extracted `candidate_profile` into the
// `Candidate` view-model the identity UI renders.
//
// The null return is the important part of this contract: analyses
// persisted before `candidate_profile` existed have no identity data, and
// no amount of client-side work can recover it. Callers render a neutral
// "not available" state for null rather than falling back to a stand-in
// person -- a hardcoded name is indistinguishable from a correctly
// extracted one on screen, which is exactly how the previous mock went
// unnoticed while showing the same name for every uploaded resume.
import type { Candidate, ResumeAnalysisResult } from './types'

// Two initials at most, taken from the first and last whitespace-separated
// parts of the name, so "Ada Lovelace" -> "AL" and a single-word name like
// "Prince" -> "P". Uses the array's first/last entries rather than the
// first two, so a middle name doesn't displace the surname ("Ada Byron
// Lovelace" -> "AL", not "AB"). Falls back to an empty string only if the
// name is blank, which the backend's required `name` field should prevent.
export function initialsFromName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return ''
  const first = parts[0]
  const last = parts[parts.length - 1]
  const letters = parts.length === 1 ? [first[0]] : [first[0], last[0]]
  return letters.join('').toUpperCase()
}

export function toCandidate(analysis: ResumeAnalysisResult | null): Candidate | null {
  const profile = analysis?.candidate_profile
  if (!profile) return null

  return {
    name: profile.name,
    initials: initialsFromName(profile.name),
    // Passed through as-is, including null: `Candidate` is nullable in
    // exactly these three fields so the components can decide how to
    // present "not stated" per layout, rather than this helper baking in
    // a placeholder string that would then be indistinguishable from real
    // extracted text.
    title: profile.title,
    company: profile.current_company,
    yearsExperience: profile.years_experience,
  }
}
