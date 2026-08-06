import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  applyTailoringSuggestions,
  downloadExportedFile,
  exportTailoredResume,
  generateTailoringSuggestions,
} from './tailoringSuggestionsApi'
import { ApiError } from './api'
import {
  fixtureApplySuggestionsResponse,
  fixtureCompletedSession,
  fixtureGenerateSuggestionsResponse,
  fixtureResumeAnalysis,
} from '../testFixtures'

function fakeHeaders(values: Record<string, string>) {
  return { get: (name: string) => values[name.toLowerCase()] ?? values[name] ?? null }
}

describe('generateTailoringSuggestions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs to /v1/tailoring-suggestions with the expected body and returns the parsed result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureGenerateSuggestionsResponse),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await generateTailoringSuggestions(
      'resume text',
      'jd text',
      fixtureResumeAnalysis,
      fixtureCompletedSession,
      '  Keep it under two pages.  ',
      'resume.pdf',
    )

    expect(result).toEqual(fixtureGenerateSuggestionsResponse)
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/v1/tailoring-suggestions')
    expect(options.method).toBe('POST')
    const body = JSON.parse(options.body)
    expect(body.resume).toBe('resume text')
    expect(body.job_description).toBe('jd text')
    expect(body.resume_analysis).toEqual(fixtureResumeAnalysis)
    expect(body.career_conversation).toEqual(fixtureCompletedSession)
    expect(body.custom_instructions).toBe('Keep it under two pages.')
    expect(body.resume_filename).toBe('resume.pdf')
  })

  it('sends null custom_instructions when blank', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureGenerateSuggestionsResponse),
    })
    vi.stubGlobal('fetch', fetchMock)

    await generateTailoringSuggestions(
      'resume text',
      'jd text',
      fixtureResumeAnalysis,
      fixtureCompletedSession,
      '   ',
      null,
    )

    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.custom_instructions).toBeNull()
    expect(body.resume_filename).toBeNull()
  })

  it('throws ApiError when the network request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))

    await expect(
      generateTailoringSuggestions('r', 'jd', fixtureResumeAnalysis, fixtureCompletedSession, '', null),
    ).rejects.toThrow(ApiError)
  })

  it('surfaces the backend-provided error detail on a 502 (invalid plan)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: () => Promise.resolve({ detail: 'Planned edit cites no evidence.' }),
      }),
    )

    await expect(
      generateTailoringSuggestions('r', 'jd', fixtureResumeAnalysis, fixtureCompletedSession, '', null),
    ).rejects.toThrow('Planned edit cites no evidence.')
  })
})

describe('applyTailoringSuggestions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('POSTs selected ids and edited texts, and returns the parsed result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixtureApplySuggestionsResponse),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await applyTailoringSuggestions('plan-1', ['suggestion-0'], {
      'suggestion-0': 'Edited text.',
    })

    expect(result).toEqual(fixtureApplySuggestionsResponse)
    const [url, options] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/v1/tailoring-suggestions/plan-1/apply')
    const body = JSON.parse(options.body)
    expect(body.selected_suggestion_ids).toEqual(['suggestion-0'])
    expect(body.edited_texts).toEqual({ 'suggestion-0': 'Edited text.' })
  })

  it.each([
    [400, 'unknown_suggestion'],
    [404, 'not_found'],
    [409, 'conflict'],
    [422, 'revalidation_failed'],
    [500, 'unknown'],
  ])('classifies a %i response as cause=%s', async (status, cause) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status,
        json: () => Promise.resolve({ detail: 'Something went wrong.' }),
      }),
    )

    await expect(applyTailoringSuggestions('plan-1', [], {})).rejects.toMatchObject({ cause })
  })

  it('falls back to a generic message when the error body has no detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: () => Promise.reject(new Error('not json')),
      }),
    )

    await expect(applyTailoringSuggestions('plan-1', [], {})).rejects.toThrow(/HTTP 409/)
  })
})

describe('exportTailoredResume', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('returns the blob, parsed filename, content type, and fidelity on success', async () => {
    const blob = new Blob(['file content'])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(blob),
        headers: fakeHeaders({
          'content-disposition': 'attachment; filename="Tailored_Resume.pdf"',
          'x-export-fidelity': 'regenerated_template',
          'content-type': 'application/pdf',
        }),
      }),
    )

    const result = await exportTailoredResume('plan-1', ['suggestion-0'], {}, 'pdf', 'My Resume')

    expect(result.blob).toBe(blob)
    expect(result.filename).toBe('Tailored_Resume.pdf')
    expect(result.fidelity).toBe('regenerated_template')
    expect(result.contentType).toBe('application/pdf')
  })

  it('falls back to a default filename when Content-Disposition is missing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        blob: () => Promise.resolve(new Blob(['x'])),
        headers: fakeHeaders({}),
      }),
    )

    const result = await exportTailoredResume('plan-1', [], {}, 'txt', null)

    expect(result.filename).toBe('Tailored_Resume')
    expect(result.fidelity).toBeNull()
  })

  it('never treats an error response body as a downloadable file', async () => {
    const blobSpy = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Tailoring suggestion plan not found.' }),
        blob: blobSpy,
      }),
    )

    await expect(exportTailoredResume('does-not-exist', [], {}, 'txt', null)).rejects.toMatchObject(
      { cause: 'not_found' },
    )
    expect(blobSpy).not.toHaveBeenCalled()
  })
})

describe('downloadExportedFile', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('creates and revokes an object URL, and triggers a click via a temporary anchor', () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:fake-url')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

    const clickSpy = vi.fn()
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = originalCreateElement(tag)
      if (tag === 'a') element.click = clickSpy
      return element
    })

    downloadExportedFile({
      blob: new Blob(['content']),
      filename: 'Tailored_Resume.txt',
      contentType: 'text/plain',
      fidelity: 'approximate_style',
    })

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url')
  })

  it('revokes the object URL even if the download click throws', () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:fake-url')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })

    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const element = originalCreateElement(tag)
      if (tag === 'a') {
        element.click = () => {
          throw new Error('boom')
        }
      }
      return element
    })

    expect(() =>
      downloadExportedFile({
        blob: new Blob(['content']),
        filename: 'x.txt',
        contentType: 'text/plain',
        fidelity: null,
      }),
    ).toThrow('boom')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url')
  })
})
