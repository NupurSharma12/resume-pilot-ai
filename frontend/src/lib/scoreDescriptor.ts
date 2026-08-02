// Pure, score-driven derivations. The backend's SkillMatch/OverallAssessment
// only ever give us a numeric score — no descriptor word, no match-quality
// label — so both are computed here from the number rather than mocked
// per category. This is what makes the dashboard work for any category the
// backend returns, not just ones a developer thought to hardcode text for.

export function getScoreDescriptor(score: number): string {
  if (score >= 90) return 'Exceptional'
  if (score >= 80) return 'Strong'
  if (score >= 70) return 'Good'
  if (score >= 60) return 'Fair'
  return 'Needs Improvement'
}

export function getMatchLabel(score: number): string {
  if (score >= 85) return 'Strong Match'
  if (score >= 70) return 'Moderate Match'
  return 'Weak Match'
}
