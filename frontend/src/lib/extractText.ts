// Client-side text extraction, dispatched by file extension — the browser
// equivalent of the backend's DocumentExtractorRegistry (src/app/ingestion/),
// needed here because the existing analyzeResume() API only ever accepts
// plain text, and extraction has to happen before that call, not on the
// server. PDF (pdfjs-dist) and DOCX (mammoth) parsers are dynamically
// imported, so neither is pulled into the main bundle unless a user
// actually uploads that format.

const SUPPORTED_EXTENSIONS = ['pdf', 'docx', 'txt', 'md'] as const
export type SupportedExtension = (typeof SUPPORTED_EXTENSIONS)[number]

export class TextExtractionError extends Error {}

export function getFileExtension(fileName: string): string {
  return fileName.split('.').pop()?.toLowerCase() ?? ''
}

export function isSupportedExtension(extension: string): extension is SupportedExtension {
  return (SUPPORTED_EXTENSIONS as readonly string[]).includes(extension)
}

async function extractPdfText(file: File): Promise<string> {
  const [{ getDocument, GlobalWorkerOptions }, workerUrl] = await Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url').then((mod) => mod.default),
  ])
  GlobalWorkerOptions.workerSrc = workerUrl

  const buffer = await file.arrayBuffer()
  const loadingTask = getDocument({ data: buffer })
  try {
    const pdf = await loadingTask.promise
    const pageTexts: string[] = []
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
      const page = await pdf.getPage(pageNumber)
      const content = await page.getTextContent()
      const pageText = content.items.map((item) => ('str' in item ? item.str : '')).join(' ')
      pageTexts.push(pageText)
    }
    return pageTexts.join('\n\n').trim()
  } finally {
    // `getDocument` opens a dedicated worker port per loading task that is
    // never released on its own -- without this, repeatedly extracting a
    // PDF in the same page session (e.g. re-uploading via "Change," or
    // trying a different file after a failed one) leaks one worker port
    // per attempt. Enough leaked ports can make a *later* `getDocument`
    // call fail for reasons entirely unrelated to that later file being
    // corrupted -- exactly the kind of failure the blanket catch below
    // used to relabel as "the file may be corrupted," which is why this
    // was hard to diagnose from the error message alone. `destroy()` lives
    // on the loading task (returned synchronously by `getDocument`), not
    // on the resolved `PDFDocumentProxy` -- calling it here also covers
    // the case where `loadingTask.promise` itself rejects.
    void loadingTask.destroy()
  }
}

async function extractDocxText(file: File): Promise<string> {
  const mammoth = await import('mammoth')
  const buffer = await file.arrayBuffer()
  const { value } = await mammoth.extractRawText({ arrayBuffer: buffer })
  return value.trim()
}

export async function extractTextFromFile(file: File): Promise<string> {
  const extension = getFileExtension(file.name)

  let text: string
  try {
    switch (extension) {
      case 'txt':
      case 'md':
        text = (await file.text()).trim()
        break
      case 'pdf':
        text = await extractPdfText(file)
        break
      case 'docx':
        text = await extractDocxText(file)
        break
      default:
        throw new TextExtractionError(
          `Unsupported file type ".${extension || '?'}". Please use PDF, DOCX, TXT, or MD.`,
        )
    }
  } catch (err) {
    if (err instanceof TextExtractionError) throw err
    // The underlying library error (a worker-loading failure, a genuinely
    // corrupt file, a leaked-resource failure, ...) is logged rather than
    // discarded -- the message shown to the user stays generic and
    // actionable ("may be corrupted"), but the real cause is still
    // available in the console instead of being a dead end. This was
    // previously a blanket re-throw with no trace of what actually failed.
    console.error(`Text extraction failed for "${file.name}":`, err)
    throw new TextExtractionError(`Could not read "${file.name}". The file may be corrupted.`)
  }

  if (!text) {
    throw new TextExtractionError(`"${file.name}" doesn't appear to contain any readable text.`)
  }

  return text
}
