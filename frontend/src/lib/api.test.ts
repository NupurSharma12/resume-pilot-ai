import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyzeResume, ApiError } from './api'
import { fixtureResumeAnalysis } from '../testFixtures'

describe('analyzeResume', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs to /v1/analyze and splits job_preparation_id out of the analysis result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ ...fixtureResumeAnalysis, job_preparation_id: 'job-prep-1' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await analyzeResume('resume text', 'jd text')

    expect(result.analysis).toEqual(fixtureResumeAnalysis)
    expect(result.jobPreparationId).toBe('job-prep-1')
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/v1/analyze')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.resume).toBe('resume text')
    expect(body.job_description).toBe('jd text')
  })

  it('returns a null jobPreparationId when the backend omits it', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureResumeAnalysis),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await analyzeResume('resume text', 'jd text')

    expect(result.jobPreparationId).toBeNull()
    expect(result.analysis).toEqual(fixtureResumeAnalysis)
  })

  it('throws ApiError when the network request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    await expect(analyzeResume('r', 'jd')).rejects.toThrow(ApiError)
  })

  it('throws ApiError on a non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))

    await expect(analyzeResume('r', 'jd')).rejects.toThrow(ApiError)
  })
})
