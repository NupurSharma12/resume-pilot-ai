// Pure, deterministic derivations from ResumeAnalysisResult — no invented
// content. Two different granularities are pulled from the same backend
// fields on purpose, so the Executive Summary and the "Why this Score?"
// card don't just repeat each other:
//   - buildExecutiveSummary: sentence-level, from `strengths`/`weaknesses`
//     (already full recruiter-style sentences from the backend).
//   - deriveTopStrengths/deriveTopRisks: skill-token-level, from each
//     skill_match's own `matched_skills`/`missing_skills`.

import type { ResumeAnalysisResult } from '../data/types'

const SUMMARY_BULLET_COUNT = 5
const MAX_STRENGTH_SENTENCES = 3
const MAX_WEAKNESS_SENTENCES = 2
const MAX_TOP_ITEMS = 3
const WEAK_SCORE_THRESHOLD = 70

export function buildExecutiveSummary(result: ResumeAnalysisResult): string[] {
  const bullets = [
    ...result.strengths.slice(0, MAX_STRENGTH_SENTENCES),
    ...result.weaknesses.slice(0, MAX_WEAKNESS_SENTENCES),
  ]

  // If the backend's own strengths/weaknesses sentences don't add up to
  // five, fill the remainder with one real sentence per skill_match
  // (highest-scoring first) — still only real category names and scores,
  // never fabricated skills or claims.
  if (bullets.length < SUMMARY_BULLET_COUNT) {
    const byScoreDesc = [...result.skill_matches].sort((a, b) => b.score - a.score)
    for (const skillMatch of byScoreDesc) {
      if (bullets.length >= SUMMARY_BULLET_COUNT) break
      const descriptor =
        skillMatch.score >= 80
          ? 'Strong alignment'
          : skillMatch.score >= WEAK_SCORE_THRESHOLD
            ? 'Moderate alignment'
            : 'Limited alignment'
      bullets.push(`${descriptor} in ${skillMatch.category} (${skillMatch.score}/100).`)
    }
  }

  return bullets.slice(0, SUMMARY_BULLET_COUNT)
}

export function deriveTopStrengths(result: ResumeAnalysisResult): string[] {
  const items: string[] = []
  const byScoreDesc = [...result.skill_matches].sort((a, b) => b.score - a.score)

  // One representative matched skill from each of the highest-scoring
  // categories — gives breadth across dimensions rather than three skills
  // from a single category.
  for (const skillMatch of byScoreDesc) {
    if (items.length >= MAX_TOP_ITEMS) break
    const [topMatch] = skillMatch.matched_skills
    if (topMatch) items.push(`Strong ${topMatch}`)
  }

  // Fall back to the backend's own strengths sentences if skill_matches
  // didn't yield enough (e.g. a category with no matched_skills listed).
  for (const strength of result.strengths) {
    if (items.length >= MAX_TOP_ITEMS) break
    if (!items.includes(strength)) items.push(strength)
  }

  return items.slice(0, MAX_TOP_ITEMS)
}

export function deriveTopRisks(result: ResumeAnalysisResult): string[] {
  const items: string[] = []
  const byScoreAsc = [...result.skill_matches].sort((a, b) => a.score - b.score)

  for (const skillMatch of byScoreAsc) {
    if (items.length >= MAX_TOP_ITEMS) break
    const [topMissing] = skillMatch.missing_skills
    if (topMissing) {
      items.push(`Missing ${topMissing}`)
    } else if (skillMatch.score < WEAK_SCORE_THRESHOLD) {
      items.push(`${skillMatch.category} evidence is weak`)
    }
  }

  for (const weakness of result.weaknesses) {
    if (items.length >= MAX_TOP_ITEMS) break
    if (!items.includes(weakness)) items.push(weakness)
  }

  return items.slice(0, MAX_TOP_ITEMS)
}
