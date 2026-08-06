import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  extractTextFromFile,
  getFileExtension,
  isSupportedExtension,
  TextExtractionError,
} from './extractText'

const mockGetPage = vi.fn()
const mockDestroy = vi.fn().mockResolvedValue(undefined)
let mockDocumentPromise: Promise<{ numPages: number; getPage: typeof mockGetPage }>

vi.mock('pdfjs-dist', () => ({
  getDocument: vi.fn(() => ({
    promise: mockDocumentPromise,
    destroy: mockDestroy,
  })),
  GlobalWorkerOptions: {},
}))
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'blob:fake-worker-url' }))

const mockExtractRawText = vi.fn()
vi.mock('mammoth', () => ({ extractRawText: mockExtractRawText }))

function fakePage(text: string) {
  return {
    getTextContent: vi.fn().mockResolvedValue({ items: [{ str: text }] }),
  }
}

describe('getFileExtension / isSupportedExtension', () => {
  it('extracts a lowercased extension', () => {
    expect(getFileExtension('Resume.PDF')).toBe('pdf')
    expect(getFileExtension('no-extension')).toBe('no-extension')
  })

  it('recognizes exactly the four supported extensions', () => {
    expect(isSupportedExtension('pdf')).toBe(true)
    expect(isSupportedExtension('docx')).toBe(true)
    expect(isSupportedExtension('txt')).toBe(true)
    expect(isSupportedExtension('md')).toBe(true)
    expect(isSupportedExtension('jpeg')).toBe(false)
  })
})

describe('extractTextFromFile: plain text', () => {
  it('reads and trims TXT content', async () => {
    const file = new File(['  hello world  \n'], 'resume.txt', { type: 'text/plain' })
    await expect(extractTextFromFile(file)).resolves.toBe('hello world')
  })

  it('rejects an unsupported extension with an actionable message', async () => {
    const file = new File(['data'], 'resume.jpeg', { type: 'image/jpeg' })
    await expect(extractTextFromFile(file)).rejects.toThrow(/unsupported file type/i)
  })

  it('rejects a file with no readable text', async () => {
    const file = new File([''], 'resume.txt', { type: 'text/plain' })
    await expect(extractTextFromFile(file)).rejects.toThrow(/doesn't appear to contain/i)
  })
})

describe('extractTextFromFile: PDF', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPage.mockImplementation((n: number) => Promise.resolve(fakePage(`page ${n}`)))
  })

  it('extracts text across all pages and releases the loading task', async () => {
    mockDocumentPromise = Promise.resolve({ numPages: 2, getPage: mockGetPage })
    const file = new File(['%PDF-1.4 fake'], 'resume.pdf', { type: 'application/pdf' })

    const text = await extractTextFromFile(file)

    expect(text).toBe('page 1\n\npage 2')
    expect(mockGetPage).toHaveBeenCalledTimes(2)
    // The loading task's worker port must always be released, whether
    // extraction succeeds or fails -- see extractText.ts's `finally`.
    expect(mockDestroy).toHaveBeenCalledTimes(1)
  })

  it('releases the loading task even when the document promise rejects', async () => {
    mockDocumentPromise = Promise.reject(new Error('worker crashed'))
    const file = new File(['not actually a pdf'], 'resume.pdf', { type: 'application/pdf' })

    await expect(extractTextFromFile(file)).rejects.toThrow(TextExtractionError)
    expect(mockDestroy).toHaveBeenCalledTimes(1)
  })

  it('logs the real underlying error instead of only the generic message', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const realError = new Error('The API version does not match the Worker version')
    mockDocumentPromise = Promise.reject(realError)
    const file = new File(['data'], 'resume.pdf', { type: 'application/pdf' })

    await expect(extractTextFromFile(file)).rejects.toThrow(/may be corrupted/i)
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('resume.pdf'), realError)

    consoleSpy.mockRestore()
  })

  it('still throws a corrupted-file error for a genuinely empty PDF', async () => {
    mockDocumentPromise = Promise.resolve({ numPages: 1, getPage: mockGetPage })
    mockGetPage.mockResolvedValue({ getTextContent: vi.fn().mockResolvedValue({ items: [] }) })
    const file = new File(['data'], 'resume.pdf', { type: 'application/pdf' })

    await expect(extractTextFromFile(file)).rejects.toThrow(/doesn't appear to contain/i)
  })
})

describe('extractTextFromFile: DOCX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('extracts and trims DOCX text via mammoth', async () => {
    mockExtractRawText.mockResolvedValue({ value: '  Experienced engineer.  ' })
    const file = new File(['fake docx bytes'], 'resume.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })

    await expect(extractTextFromFile(file)).resolves.toBe('Experienced engineer.')
  })

  it('wraps a mammoth failure as a generic, actionable TextExtractionError', async () => {
    mockExtractRawText.mockRejectedValue(new Error('not a valid zip file'))
    const file = new File(['garbage'], 'resume.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })

    await expect(extractTextFromFile(file)).rejects.toThrow(/may be corrupted/i)
  })
})
