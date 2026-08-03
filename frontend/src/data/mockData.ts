import type { Candidate, SkillMatchNarrative } from './types'

// Identity/profile fields only — everything analysis-related (score,
// recommendation, fit summary) comes from the real ResumeAnalysisResult
// returned by the backend, not from mock data.
export const candidate: Candidate = {
  name: 'Nupur Sharma',
  initials: 'NS',
  title: 'Senior Product Manager',
  company: 'Adobe',
  yearsExperience: 13,
  rating: 4.5,
}

// The backend's SkillMatch only ever carries category/score/matched_skills/
// missing_skills — no narrative text. `aiSummary`/`recommendation` (shown in
// the Analysis Panel) and `recruiterSummary` (shown on each metric card) are
// kept mocked here, keyed by `category`, so they can be deleted the moment
// the backend starts returning this content itself, without touching any
// component that reads them.
export const skillMatchNarratives: Record<string, SkillMatchNarrative> = {
  'Technical Skills': {
    recruiterSummary: 'Strong backend & API expertise',
    aiSummary:
      'Demonstrates deep technical fluency across backend systems, API design, and cloud infrastructure, closely matching the core technical requirements of this role.',
    recommendation: 'Proceed — technical depth exceeds the bar for this role.',
  },
  Leadership: {
    recruiterSummary: 'Good team leadership; PM ownership weaker',
    aiSummary:
      'Shows solid cross-functional leadership and mentorship experience, though direct people-management scope is narrower than ideal for this level.',
    recommendation: 'Probe leadership scope further in the interview before finalizing.',
  },
  'Domain Expertise': {
    recruiterSummary: 'Deep industry & product-domain knowledge',
    aiSummary:
      'Strong alignment with enterprise SaaS and B2B product domains, backed by 13 years at a recognized industry leader.',
    recommendation: 'Domain background is a strong match for this role.',
  },
  Communication: {
    recruiterSummary: 'Clear, structured stakeholder communication',
    aiSummary:
      'Communication style is clear and structured, with strong evidence of effective stakeholder alignment across distributed teams.',
    recommendation: 'No concerns — communication skills support the role.',
  },
  Experience: {
    recruiterSummary: 'Extensive senior-level track record',
    aiSummary:
      'Extensive, senior-level experience with a consistent track record of enterprise-scale product delivery.',
    recommendation: 'Experience level exceeds requirements for this role.',
  },
}

// Used whenever a skill_match's category has no matching entry above —
// e.g. a category the backend adds later that this mock file doesn't know
// about yet. Keeps the dashboard from rendering blank/undefined text for
// any category count or name, per "don't assume exactly five categories."
export const defaultSkillMatchNarrative: SkillMatchNarrative = {
  recruiterSummary: 'Assessment based on resume evidence',
  aiSummary: 'A detailed narrative for this category is not yet available.',
  recommendation: 'Review the supporting evidence before making a decision.',
}
