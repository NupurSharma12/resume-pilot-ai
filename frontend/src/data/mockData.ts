import type { Candidate, ResumeAnalysisResult, SkillMatchNarrative } from './types'

// Identity/profile fields only — everything analysis-related (score,
// recommendation, fit summary) lives in `mockResumeAnalysis` below, since
// that's what the backend actually owns.
export const candidate: Candidate = {
  name: 'Nupur Sharma',
  initials: 'NS',
  title: 'Senior Product Manager',
  company: 'Adobe',
  yearsExperience: 13,
  rating: 4.5,
}

// Single source of truth, shaped to match the backend's ResumeAnalysisResult
// response exactly (see src/app/models/resume_analysis.py: overall_assessment,
// skill_matches, matching_projects, strengths, weaknesses, resume_improvements).
// The dashboard derives everything analysis-related from this one object, so
// wiring up the real API later is a matter of replacing this constant with
// the response body — not restructuring any component.
export const mockResumeAnalysis: ResumeAnalysisResult = {
  overall_assessment: {
    overall_score: 86,
    hiring_recommendation: {
      decision: 'Proceed to Interview',
      reason:
        'Exceptional product leader with enterprise-grade credentials and cross-functional depth.',
    },
    summary:
      'Exceptional product leader with enterprise-grade credentials and cross-functional depth. Strong technical fluency paired with proven leadership across globally distributed teams makes this candidate a top-tier fit for this role.',
  },
  skill_matches: [
    {
      category: 'Technical Skills',
      score: 91,
      matched_skills: ['API Design', 'System Architecture', 'Data Analytics', 'Cloud Platforms (AWS)'],
      missing_skills: ['Machine Learning Ops'],
    },
    {
      category: 'Leadership',
      score: 78,
      matched_skills: ['Cross-functional Team Leadership', 'Stakeholder Management', 'Mentorship'],
      missing_skills: ['Direct P&L Ownership', 'Formal People Management at Scale'],
    },
    {
      category: 'Domain Expertise',
      score: 88,
      matched_skills: ['Enterprise SaaS', 'Product-Led Growth', 'B2B Platforms'],
      missing_skills: ['Vertical-specific Compliance Knowledge'],
    },
    {
      category: 'Communication',
      score: 82,
      matched_skills: ['Executive Presentations', 'Written Documentation', 'Cross-team Alignment'],
      missing_skills: ['Public Speaking at Scale'],
    },
    {
      category: 'Experience',
      score: 93,
      matched_skills: ['13+ Years Product Management', 'Enterprise-scale Delivery', 'Team Scaling'],
      missing_skills: [],
    },
  ],
  matching_projects: [
    {
      title: 'Enterprise Platform Migration',
      relevance_score: 92,
      reason: 'Directly demonstrates large-scale product ownership relevant to this role.',
    },
  ],
  strengths: [
    'Deep technical fluency across backend systems and cloud infrastructure',
    'Proven cross-functional leadership across globally distributed teams',
  ],
  weaknesses: [
    'Limited direct P&L ownership',
    'No hands-on machine learning operations experience',
  ],
  resume_improvements: [
    {
      section: 'Leadership',
      recommendation: 'Quantify team size and P&L scope managed in prior roles.',
      priority: 1,
    },
  ],
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
