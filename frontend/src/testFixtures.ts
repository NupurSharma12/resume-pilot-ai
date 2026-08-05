import type { ResumeAnalysisResult } from './data/types'
import type { ResumeInputValue } from './components/ResumeInput'
import type { JobDescriptionInputValue } from './components/JobDescriptionInput'
import type { ConversationSessionState } from './data/careerConversationTypes'
import type { TailorResumeResult } from './data/tailoringTypes'
import { RESUME_SESSION_VERSION, type PersistedResumeSession } from './session/resumeSessionTypes'

export const fixtureResume: ResumeInputValue = {
  text: 'Experienced engineer...',
  fileName: 'resume.txt',
}

export const fixtureJobDescription: JobDescriptionInputValue = {
  text: 'We are looking for...',
  fileName: null,
}

export const fixtureResumeAnalysis: ResumeAnalysisResult = {
  overall_assessment: {
    overall_score: 82,
    hiring_recommendation: { decision: 'Strong Match', reason: 'Solid overlap.' },
    summary: 'A strong candidate overall.',
  },
  skill_matches: [
    { category: 'Frontend', score: 90, matched_skills: ['React'], missing_skills: [] },
  ],
  matching_projects: [],
  strengths: ['Communication'],
  weaknesses: ['Limited backend experience'],
  resume_improvements: [],
}

export const fixtureSession: ConversationSessionState = {
  session_id: 'session-123',
  status: 'in_progress',
  history: [],
  current_question: {
    topic: 'Leadership',
    question: 'Tell me about a time you led a project.',
    evidence_goal: 'Assess leadership evidence.',
    estimated_impact: 'high',
    assistant_response: null,
  },
  stop_reason: null,
}

export const fixtureCompletedSession: ConversationSessionState = {
  session_id: 'session-123',
  status: 'complete',
  history: [
    {
      topic: 'Leadership',
      question: 'Tell me about a time you led a project.',
      answer: 'I led the migration of our dashboard from Angular to React.',
      assistant_response: null,
    },
  ],
  current_question: null,
  stop_reason: 'Enough evidence recovered.',
}

export const fixtureTailorResult: TailorResumeResult = {
  tailoring_plan: {
    changes: [
      {
        section: 'Summary',
        action: 'rewrite',
        reason: 'Recent backend engineering work is missing.',
        evidence_ids: ['conversation-turn-1'],
      },
    ],
  },
  tailored_resume: {
    sections: [
      {
        heading: 'Summary',
        bullets: [
          {
            text: 'Led the migration of the dashboard from Angular to React.',
            supporting_evidence_ids: ['conversation-turn-1'],
          },
        ],
      },
    ],
  },
  validation_report: {
    total_bullets: 2,
    accepted_count: 1,
    rejected_count: 1,
    rejected_bullets: [
      {
        section: 'Summary',
        text: 'Reduced infrastructure costs by 40% using Kubernetes.',
        reason: 'Contains term(s) not present in cited evidence: Kubernetes.',
      },
    ],
    passed: false,
  },
}

export function fixturePersistedSession(
  overrides: Partial<PersistedResumeSession> = {},
): PersistedResumeSession {
  return {
    version: RESUME_SESSION_VERSION,
    resume: fixtureResume,
    jobDescription: fixtureJobDescription,
    resumeAnalysis: fixtureResumeAnalysis,
    status: 'success',
    activeCareerConversationSessionId: null,
    careerConversationStatus: null,
    tailoredResumeResult: null,
    ...overrides,
  }
}
