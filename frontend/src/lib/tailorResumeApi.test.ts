import { describe, it, expect, vi, beforeEach } from 'vitest'
import { tailorResume } from './tailorResumeApi'
import { ApiError } from './api'
import { fixtureResumeAnalysis, fixtureCompletedSession, fixtureTailorResult } from '../testFixtures'

describe('tailorResume', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs to /v1/tailor-resume with the expected body and returns the parsed result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureTailorResult),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await tailorResume(
      'resume text',
      'jd text',
      fixtureResumeAnalysis,
      fixtureCompletedSession,
    )

    expect(result).toEqual(fixtureTailorResult)
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/v1/tailor-resume')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.resume).toBe('resume text')
    expect(body.job_description).toBe('jd text')
    expect(body.resume_analysis).toEqual(fixtureResumeAnalysis)
    expect(body.career_conversation).toEqual(fixtureCompletedSession)
  })

  it('throws ApiError when the network request itself fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('network down')),
    )

    await expect(
      tailorResume('resume', 'jd', fixtureResumeAnalysis, fixtureCompletedSession),
    ).rejects.toThrow(ApiError)
  })

  it('throws ApiError on a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500 }),
    )

    await expect(
      tailorResume('resume', 'jd', fixtureResumeAnalysis, fixtureCompletedSession),
    ).rejects.toThrow(/HTTP 500/)
  })
})
