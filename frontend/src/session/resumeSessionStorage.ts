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
// resumeAnalysis/tailoringPlan/finalTailoredResume (those are large,
// evolving shapes already typed elsewhere — re-validating every field
// here would just be a second, driftable copy of those types) but strict
// about the envelope: version, status enums, and id/array/record types.
// Anything else is treated as corrupt/unsupported and discarded rather
// than risking a crash from acting on it. A payload saved before a given
// field existed is "unsupported" by the same rule (missing required
// keys) — cleared and re-initialized empty, the same graceful path
// already used for any other stale/malformed session, not a special
// case. Bumping RESUME_SESSION_VERSION (done for the Interactive
// Tailoring fields below) is what makes any session persisted by a prior
// build of this app -- which never had these fields at all -- fail this
// check and get discarded the same way, rather than partially rehydrating
// into a shape this version doesn't expect.
function isSupportedPersistedSession(value: unknown): value is PersistedResumeSession {
  if (!isPlainObject(value)) return false
  if (value.version !== RESUME_SESSION_VERSION) return false
  if (
    !('resume' in value) ||
    !('jobDescription' in value) ||
    !('resumeAnalysis' in value) ||
    !('tailoringPlan' in value) ||
    !('finalTailoredResume' in value)
  ) {
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
  if (
    value.careerConversationStatus !== null &&
    value.careerConversationStatus !== 'in_progress' &&
    value.careerConversationStatus !== 'complete'
  ) {
    return false
  }
  if (value.tailoringPlanStatus !== 'idle' && value.tailoringPlanStatus !== 'error') {
    return false
  }
  if (!Array.isArray(value.tailoringSelections)) return false
  if (typeof value.tailoringCustomInstructions !== 'string') return false
  if (!isPlainObject(value.tailoringEditedTexts)) return false
  if (!Array.isArray(value.tailoringAvailableExportFormats)) return false
  if (
    value.tailoringSourceFormat !== null &&
    value.tailoringSourceFormat !== 'pdf' &&
    value.tailoringSourceFormat !== 'docx' &&
    value.tailoringSourceFormat !== 'markdown' &&
    value.tailoringSourceFormat !== 'plain_text'
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
