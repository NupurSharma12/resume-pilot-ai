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
})
