import type {
  InterviewPreparation,
  JobPreparationDetail,
  JobPreparationListResult,
} from '../data/jobPreparationHistoryTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Calls the backend's GET /v1/job-preparations -- the History list.
// `search`/`limit`/`offset` are sent straight through as query params --
// both search and pagination are server-side (see the History
// server-side pagination/search decision; the backend already supported
// company/job_title/updated_after too, still unused here). Returns the
// full result object (items + total + limit + offset), not just the
// items array, since HistoryPage needs `total` to render pagination
// controls.
export async function listJobPreparations(options?: {
  search?: string
  limit?: number
  offset?: number
}): Promise<JobPreparationListResult> {
  const params = new URLSearchParams()
  if (options?.search !== undefined) params.set('search', options.search)
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
  if (options?.offset !== undefined) params.set('offset', String(options.offset))
  const query = params.toString()

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/job-preparations${query ? `?${query}` : ''}`)
  } catch {
    throw new ApiError('Could not reach the history service. Is the backend running?')
  }

  if (!response.ok) {
    throw new ApiError(`Loading history failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as JobPreparationListResult
}

// Calls the backend's GET /v1/job-preparations/{id} -- opening one
// preparation from History. Throws `ApiError` with `cause: 'not_found'`
// on a 404 (e.g. a stale link), matching this codebase's existing
// `getCareerConversation` convention for distinguishing "gone" from any
// other failure.
export async function getJobPreparation(jobPreparationId: string): Promise<JobPreparationDetail> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/job-preparations/${jobPreparationId}`)
  } catch {
    throw new ApiError('Could not reach the history service. Is the backend running?')
  }

  if (response.status === 404) {
    throw new ApiError('This job preparation no longer exists.', { cause: 'not_found' })
  }

  if (!response.ok) {
    throw new ApiError(`Loading this job preparation failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as JobPreparationDetail
}

// Calls the backend's POST /v1/job-preparations/{id}/interview-preparation
// -- generates (and persists server-side) the Interview Preparation guide
// for one job preparation. No request body: the backend derives
// everything it needs (resume, job description, Career Conversation) from
// the already-persisted JobPreparation itself (see the endpoint's
// docstring). `409` means the preparation is already completed and is
// read-only history, matching the same convention as any other
// completed-preparation write in this codebase.
export async function generateInterviewPreparation(
  jobPreparationId: string,
): Promise<InterviewPreparation> {
  let response: Response
  try {
    response = await fetch(
      `${API_BASE_URL}/v1/job-preparations/${jobPreparationId}/interview-preparation`,
      { method: 'POST' },
    )
  } catch {
    throw new ApiError('Could not reach the interview preparation service. Is the backend running?')
  }

  if (response.status === 404) {
    throw new ApiError('This job preparation no longer exists.', { cause: 'not_found' })
  }

  if (response.status === 409) {
    throw new ApiError('This job preparation is already completed and is read-only.', {
      cause: 'conflict',
    })
  }

  if (!response.ok) {
    throw new ApiError(`Generating interview preparation failed (HTTP ${response.status}).`)
  }

  return (await response.json()) as InterviewPreparation
}

// Calls the backend's DELETE /v1/job-preparations/{id} -- the user-facing
// "Delete" action in History. Soft-delete only (see that endpoint's own
// docstring): the preparation is no longer returned by
// `listJobPreparations`, but this call itself has no response body to
// return. `404` (`cause: 'not_found'`) means the preparation was never
// there to begin with -- HistoryPage treats that the same as a successful
// delete (the desired end state, "not in History," already holds), same
// convention as `getJobPreparation`'s `not_found` classification.
export async function deleteJobPreparation(jobPreparationId: string): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/job-preparations/${jobPreparationId}`, {
      method: 'DELETE',
    })
  } catch {
    throw new ApiError('Could not reach the history service. Is the backend running?')
  }

  if (response.status === 404) {
    throw new ApiError('This job preparation no longer exists.', { cause: 'not_found' })
  }

  if (!response.ok) {
    throw new ApiError(`Deleting this job preparation failed (HTTP ${response.status}).`)
  }
}
