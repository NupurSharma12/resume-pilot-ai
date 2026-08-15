import type {
  InterviewPreparation,
  JobPreparationDetail,
  JobPreparationSummary,
} from '../data/jobPreparationHistoryTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Calls the backend's GET /v1/job-preparations -- the History list.
// `limit` is the only filter sent (History shows only its 10 most
// recent); search is client-side over the returned page (see
// HistoryPage), not a server-side filter -- the backend already supports
// company/job_title/updated_after too, unused here.
export async function listJobPreparations(options?: {
  limit?: number
}): Promise<JobPreparationSummary[]> {
  const params = new URLSearchParams()
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
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

  const body = (await response.json()) as { items: JobPreparationSummary[] }
  return body.items
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
