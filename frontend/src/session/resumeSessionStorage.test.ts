import { describe, expect, it, beforeEach } from 'vitest'
import { sessionStorageResumeSessionStorage } from './resumeSessionStorage'
import { fixturePersistedSession } from '../testFixtures'

const STORAGE_KEY = 'resumepilot.resumeSession.v1'

describe('sessionStorageResumeSessionStorage', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('returns null when nothing is stored', () => {
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('round-trips a saved session', () => {
    const session = fixturePersistedSession({ activeCareerConversationSessionId: 'abc' })
    sessionStorageResumeSessionStorage.save(session)
    expect(sessionStorageResumeSessionStorage.load()).toEqual(session)
  })

  it('clears the stored key', () => {
    sessionStorageResumeSessionStorage.save(fixturePersistedSession())
    sessionStorageResumeSessionStorage.clear()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards malformed (non-JSON) storage instead of throwing', () => {
    window.sessionStorage.setItem(STORAGE_KEY, 'not json{{{')
    expect(() => sessionStorageResumeSessionStorage.load()).not.toThrow()
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('discards an unsupported/future version instead of crashing', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), version: 999 }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('discards a payload with an invalid status enum', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), status: 'loading' }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload that is not an object', () => {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(['not', 'an', 'object']))
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('round-trips tailoring plan, selections, custom instructions, and final resume', () => {
    const session = fixturePersistedSession({
      tailoringPlan: {
        plan_id: 'plan-1',
        suggestions: [],
      },
      tailoringSelections: ['suggestion-0'],
      tailoringCustomInstructions: 'Keep it under two pages.',
      tailoringEditedTexts: { 'suggestion-0': 'Edited text.' },
      finalTailoredResume: { finalResumeText: 'Final text.', appliedSuggestionIds: ['suggestion-0'] },
      tailoringValidationReport: { is_valid: true, messages: [] },
      tailoringAvailableExportFormats: ['txt', 'pdf'],
      tailoringSourceFormat: 'pdf',
    })
    sessionStorageResumeSessionStorage.save(session)
    expect(sessionStorageResumeSessionStorage.load()).toEqual(session)
  })

  it('discards a payload from a version predating the Interactive Tailoring fields', () => {
    // A session persisted by a prior build of this app: no tailoringPlan/
    // tailoringSelections/etc. keys at all, and version 1 instead of 2.
    const legacySession = {
      version: 1,
      resume: null,
      jobDescription: null,
      resumeAnalysis: null,
      status: 'idle',
      activeCareerConversationSessionId: null,
      careerConversationStatus: null,
      tailoredResumeResult: null,
    }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(legacySession))
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('discards a payload with an invalid tailoringPlanStatus enum', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), tailoringPlanStatus: 'generating' }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload where tailoringSelections is not an array', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), tailoringSelections: 'suggestion-0' }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload where tailoringCustomInstructions is not a string', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), tailoringCustomInstructions: 42 }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload where tailoringEditedTexts is not an object', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), tailoringEditedTexts: ['not', 'a', 'record'] }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload with an invalid tailoringSourceFormat', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), tailoringSourceFormat: 'jpeg' }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('discards a payload from a version predating the Post-Apply Analysis Loop fields', () => {
    // A session persisted by the prior build (version 3): no
    // postApplyAnalysis/postApplyComparison/postApplyAnalysisStatus keys
    // at all -- must be discarded, not partially rehydrated.
    const preLoopSession = { ...fixturePersistedSession(), version: 3 } as Record<string, unknown>
    delete preLoopSession.postApplyAnalysis
    delete preLoopSession.postApplyComparison
    delete preLoopSession.postApplyAnalysisStatus
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(preLoopSession))

    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('discards a payload with an invalid postApplyAnalysisStatus enum', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...fixturePersistedSession(), postApplyAnalysisStatus: 'reanalyzing' }),
    )
    expect(sessionStorageResumeSessionStorage.load()).toBeNull()
  })

  it('round-trips a session carrying a post-apply comparison', () => {
    const session = fixturePersistedSession({
      postApplyAnalysis: null,
      postApplyComparison: {
        score_before: 70,
        score_after: 80,
        score_delta: 10,
        status: 'improved',
        category_comparisons: [],
        strengths_gained: ['Demonstrated frontend work.'],
        strengths_lost: [],
        weaknesses_resolved: [],
        weaknesses_remaining: [],
        new_weaknesses: [],
      },
      postApplyAnalysisStatus: 'idle',
    })
    sessionStorageResumeSessionStorage.save(session)
    expect(sessionStorageResumeSessionStorage.load()).toEqual(session)
  })
})
