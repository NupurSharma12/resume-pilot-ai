import {
  RESUME_SESSION_VERSION,
  type PersistedResumeSession,
  type ResumeSessionStorage,
} from './resumeSessionTypes'

// Namespaced so it can't collide with anything else that might use
// sessionStorage on this origin, and so it's obvious in devtools what wrote it.
const STORAGE_KEY = 'resumepilot.resumeSession.v1'

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

// Deliberately permissive about the *content* of resume/jobDescription/
// resumeAnalysis (those are large, evolving shapes already typed elsewhere —
// re-validating every field here would just be a second, driftable copy of
// those types) but strict about the envelope: version, status enum, and the
// session id's type. Anything else is treated as corrupt/unsupported and
// discarded rather than risking a crash from acting on it.
function isSupportedPersistedSession(value: unknown): value is PersistedResumeSession {
  if (!isPlainObject(value)) return false
  if (value.version !== RESUME_SESSION_VERSION) return false
  if (!('resume' in value) || !('jobDescription' in value) || !('resumeAnalysis' in value)) {
    return false
  }
  if (value.status !== 'idle' && value.status !== 'success' && value.status !== 'error') {
    return false
  }
  if (
    value.activeCareerConversationSessionId !== null &&
    typeof value.activeCareerConversationSessionId !== 'string'
  ) {
    return false
  }
  return true
}

export const sessionStorageResumeSessionStorage: ResumeSessionStorage = {
  load() {
    let raw: string | null
    try {
      raw = window.sessionStorage.getItem(STORAGE_KEY)
    } catch {
      // sessionStorage can throw (e.g. disabled, private-browsing quota) --
      // treat exactly like "nothing stored" rather than crashing the app.
      return null
    }
    if (!raw) return null

    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      this.clear()
      return null
    }

    if (!isSupportedPersistedSession(parsed)) {
      this.clear()
      return null
    }

    return parsed
  },

  save(session) {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
    } catch {
      // Storage can be full or unavailable -- persistence is a nice-to-have,
      // not a requirement for the app to keep working this session.
    }
  },

  clear() {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // See save() -- nothing meaningful to do if storage is unavailable.
    }
  },
}
