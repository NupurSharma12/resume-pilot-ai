import { describe, it, expect, vi, beforeEach } from 'vitest'
import { reanalyzeAfterApply } from './postApplyApi'
import { ApiError } from './api'
import { fixtureResumeAnalysis } from '../testFixtures'
import type { ReanalyzeResponse } from '../data/postApplyTypes'

const fixtureReanalyzeResponse: ReanalyzeResponse = {
  after_analysis: fixtureResumeAnalysis,
  comparison: {
    score_before: 70,
    score_after: 80,
    score_delta: 10,
    status: 'improved',
    category_comparisons: [],
    strengths_gained: [],
    strengths_lost: [],
    weaknesses_resolved: [],
    weaknesses_remaining: [],
    new_weaknesses: [],
  },
}

describe('reanalyzeAfterApply', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs to the reanalyze endpoint with no job_description field and returns the parsed result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureReanalyzeResponse),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await reanalyzeAfterApply('plan-123', fixtureResumeAnalysis, ['suggestion-0'], {
      'suggestion-0': 'edited text',
    })

    expect(result).toEqual(fixtureReanalyzeResponse)
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/v1/tailoring-suggestions/plan-123/reanalyze')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.previous_analysis).toEqual(fixtureResumeAnalysis)
    expect(body.selected_suggestion_ids).toEqual(['suggestion-0'])
    expect(body.edited_texts).toEqual({ 'suggestion-0': 'edited text' })
    expect(body.job_description).toBeUndefined()
  })

  it('throws ApiError when the network request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    await expect(reanalyzeAfterApply('plan-123', fixtureResumeAnalysis, [], {})).rejects.toThrow(
      ApiError,
    )
  })

  it('surfaces the backend-provided error detail and classifies a 404 as not_found', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Tailoring suggestion plan not found.' }),
      }),
    )

    await expect(
      reanalyzeAfterApply('plan-123', fixtureResumeAnalysis, [], {}),
    ).rejects.toMatchObject({
      message: 'Tailoring suggestion plan not found.',
      cause: 'not_found',
    })
  })

  it('falls back to a generic message when the error response has no JSON body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('not json')),
      }),
    )

    await expect(
      reanalyzeAfterApply('plan-123', fixtureResumeAnalysis, [], {}),
    ).rejects.toMatchObject({
      message: 'Re-analysis failed (HTTP 500).',
    })
  })
})
