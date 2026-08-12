import type { JobPreparationDetail, JobPreparationSummary } from '../data/jobPreparationHistoryTypes'
import { ApiError } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Calls the backend's GET /v1/job-preparations -- the History list. No
// filters are sent yet (see HistoryPage: no search/filter UI in this
// milestone), but the backend already supports company/job_title/
// updated_after/limit if a future UI adds them.
export async function listJobPreparations(): Promise<JobPreparationSummary[]> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/job-preparations`)
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
