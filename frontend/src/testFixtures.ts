import type { ResumeAnalysisResult } from './data/types'
import type { ResumeInputValue } from './components/ResumeInput'
import type { JobDescriptionInputValue } from './components/JobDescriptionInput'
import type { ConversationSessionState } from './data/careerConversationTypes'
import type {
  ApplySuggestionsResponse,
  GenerateSuggestionsResponse,
  TailoringSuggestion,
} from './data/tailoringSuggestionsTypes'
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

export const fixtureSuggestionAppend: TailoringSuggestion = {
  suggestion_id: 'suggestion-0',
  target_section_id: 'section-1',
  target_item_id: 'section-1-item-0',
  operation: 'append',
  current_text: 'Python',
  suggested_text: 'Python, TypeScript',
  reason: 'TypeScript experience is missing from Skills.',
  evidence_ids: ['conversation-turn-1'],
  evidence_sources: ['Conversation Turn 1'],
  confidence: 90,
  selected_by_default: true,
  validation_status: 'supported_by_conversation',
  validation_issues: [],
  conflicts_with: [],
}

export const fixtureSuggestionInsert: TailoringSuggestion = {
  suggestion_id: 'suggestion-1',
  target_section_id: 'section-2',
  target_item_id: 'section-2-item-0',
  operation: 'insert_after',
  current_text: null,
  suggested_text: 'Led the migration of the dashboard from Angular to React.',
  reason: 'Recent frontend work is missing from Experience.',
  evidence_ids: ['conversation-turn-1'],
  evidence_sources: ['Conversation Turn 1'],
  confidence: 85,
  selected_by_default: true,
  validation_status: 'supported_by_conversation',
  validation_issues: [],
  conflicts_with: [],
}

export const fixtureGenerateSuggestionsResponse: GenerateSuggestionsResponse = {
  plan_id: 'plan-123',
  suggestions: [fixtureSuggestionAppend, fixtureSuggestionInsert],
  available_export_formats: ['txt', 'markdown', 'docx', 'pdf'],
  default_export_format: 'txt',
}

export const fixtureApplySuggestionsResponse: ApplySuggestionsResponse = {
  applied_suggestion_ids: ['suggestion-0'],
  final_resume_text: 'SUMMARY\nExperienced engineer...\n\nSKILLS\nPython, TypeScript\n',
  final_validation: { is_valid: true, messages: [] },
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
    tailoringPlan: null,
    tailoringPlanStatus: 'idle',
    tailoringSelections: [],
    tailoringCustomInstructions: '',
    tailoringEditedTexts: {},
    finalTailoredResume: null,
    tailoringValidationReport: null,
    tailoringAvailableExportFormats: [],
    tailoringSourceFormat: null,
    postApplyAnalysis: null,
    postApplyComparison: null,
    postApplyAnalysisStatus: 'idle',
    jobPreparationId: null,
    ...overrides,
  }
}
