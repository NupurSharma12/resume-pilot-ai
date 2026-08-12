// Deterministic session fixtures for the specs that don't need to be
// backed by a real LLM (comparator, selection/phased-apply, part of
// refresh/recovery). Seeded directly into `sessionStorage` under the
// exact key/shape `resumeSessionStorage.ts` itself reads and validates
// (`resumepilot.resumeSession.v1`, `RESUME_SESSION_VERSION`) -- this is
// exactly what a real prior browser session would have left behind, not
// a bypass of any product code: ResumeSessionProvider's own hydration
// effect is what reads it back out, unmodified.
import type { Page } from '@playwright/test'
import type { ResumeAnalysisResult } from '../../src/data/types'
import type {
  GenerateSuggestionsResponse,
  TailoringSuggestion,
} from '../../src/data/tailoringSuggestionsTypes'
import type { PersistedResumeSession } from '../../src/session/resumeSessionTypes'

const STORAGE_KEY = 'resumepilot.resumeSession.v1'
// Must match resumeSessionTypes.ts's RESUME_SESSION_VERSION exactly -- a
// mismatch here doesn't fail loudly, it just makes
// isSupportedPersistedSession discard this seeded session as an
// unsupported version, the same as a stale session from a prior build.
const RESUME_SESSION_VERSION = 5 as const

export const SAMPLE_RESUME_TEXT = [
  'SUMMARY',
  'Backend engineer with 5 years of experience.',
  '',
  'SKILLS',
  'Python',
  'Django',
  '',
  'EXPERIENCE',
  'Built internal tools using Python and Django.',
  'Irrelevant certification from 2005.',
].join('\n')

export const SAMPLE_JOB_DESCRIPTION_TEXT =
  'We are looking for a full-stack engineer with strong TypeScript and leadership experience.'

export const fixtureResumeAnalysis: ResumeAnalysisResult = {
  overall_assessment: {
    overall_score: 78,
    hiring_recommendation: { decision: 'Proceed', reason: 'Solid backend foundation.' },
    summary: 'A strong backend candidate with room to grow into full-stack work.',
  },
  skill_matches: [
    { category: 'Backend', score: 85, matched_skills: ['Python', 'Django'], missing_skills: [] },
    { category: 'Frontend', score: 40, matched_skills: [], missing_skills: ['TypeScript', 'React'] },
  ],
  matching_projects: [],
  strengths: ['Strong backend ownership.'],
  weaknesses: ['Frontend experience is unclear.', 'No people-management evidence.'],
  resume_improvements: [],
}

function suggestion(overrides: Partial<TailoringSuggestion> = {}): TailoringSuggestion {
  return {
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
    ...overrides,
  }
}

// Three independent, atomic suggestions across two sections -- Skills
// (two composable appends) and Experience (one insertion) -- deliberately
// shaped like the real Tailoring Engine's output (see
// docs/features/interactive-tailored-resume.md's atomic-suggestions
// design) so the E2E specs exercise the same section-grouping and
// conflict-free-composition behavior a live plan would.
export const fixtureSuggestions: TailoringSuggestion[] = [
  suggestion({
    suggestion_id: 'suggestion-0',
    target_section_id: 'section-1',
    target_item_id: 'section-1-item-0',
    operation: 'append',
    current_text: 'Python',
    suggested_text: 'Python, TypeScript',
    reason: 'TypeScript experience is missing from Skills.',
    // 'Resume: {heading}' is the exact shape EvidenceStoreBuilder sends
    // for resume-item evidence (see suggestionPresentation.ts's
    // `buildSectionNameMap`) -- present here so this fixture resolves a
    // real "Skills" section name, the same way a live plan's suggestions
    // (which cite their own target section's resume evidence whenever
    // applicable) would, rather than falling back to "Resume Section N".
    evidence_sources: ['Resume: SKILLS'],
  }),
  suggestion({
    suggestion_id: 'suggestion-1',
    target_section_id: 'section-1',
    target_item_id: 'section-1-item-1',
    operation: 'append',
    current_text: 'Django',
    suggested_text: 'Django, Flask',
    reason: 'Flask experience is missing from Skills.',
    selected_by_default: false,
    evidence_sources: ['Resume: SKILLS'],
  }),
  suggestion({
    suggestion_id: 'suggestion-2',
    target_section_id: 'section-2',
    target_item_id: 'section-2-item-0',
    operation: 'insert_after',
    current_text: null,
    suggested_text: 'Led a cross-team migration involving 4 engineers.',
    reason: 'People-management evidence is missing from Experience.',
    evidence_sources: ['Conversation Turn 1', 'Resume: EXPERIENCE'],
  }),
]

export const fixtureTailoringPlan: GenerateSuggestionsResponse = {
  plan_id: 'e2e-fixture-plan-1',
  suggestions: fixtureSuggestions,
  available_export_formats: ['txt', 'markdown', 'docx', 'pdf'],
  default_export_format: 'txt',
}

function basePersistedSession(): PersistedResumeSession {
  return {
    version: RESUME_SESSION_VERSION,
    resume: { text: SAMPLE_RESUME_TEXT, fileName: 'resume.txt' },
    jobDescription: { text: SAMPLE_JOB_DESCRIPTION_TEXT, fileName: null },
    resumeAnalysis: fixtureResumeAnalysis,
    status: 'success',
    activeCareerConversationSessionId: 'e2e-fixture-session-1',
    careerConversationStatus: 'complete',
    tailoringPlan: fixtureTailoringPlan,
    tailoringPlanStatus: 'idle',
    tailoringSelections: fixtureSuggestions
      .filter((s) => s.selected_by_default)
      .map((s) => s.suggestion_id),
    tailoringCustomInstructions: '',
    tailoringEditedTexts: {},
    finalTailoredResume: null,
    tailoringValidationReport: null,
    tailoringAvailableExportFormats: fixtureTailoringPlan.available_export_formats,
    tailoringSourceFormat: 'plain_text',
    postApplyAnalysis: null,
    postApplyComparison: null,
    postApplyAnalysisStatus: 'idle',
    jobPreparationId: null,
  }
}

// Seeds `sessionStorage` *before* any app script runs (via
// `addInitScript`, evaluated on every document the page loads in this
// context) -- so by the time ResumeSessionProvider's hydration effect
// runs on first paint, the session is already there, the same as a real
// reload would see it. Must be called before `page.goto`.
export async function seedResumeSession(
  page: Page,
  overrides: Partial<PersistedResumeSession> = {},
): Promise<PersistedResumeSession> {
  const session: PersistedResumeSession = { ...basePersistedSession(), ...overrides }
  await page.addInitScript(
    ([key, value]) => {
      window.sessionStorage.setItem(key, value)
    },
    [STORAGE_KEY, JSON.stringify(session)] as [string, string],
  )
  return session
}

export async function clearSeededSession(page: Page): Promise<void> {
  await page.addInitScript(
    (key) => {
      window.sessionStorage.removeItem(key)
    },
    STORAGE_KEY,
  )
}
