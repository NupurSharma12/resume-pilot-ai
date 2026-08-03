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
  const pdf = await getDocument({ data: buffer }).promise
  const pageTexts: string[] = []
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
    const page = await pdf.getPage(pageNumber)
    const content = await page.getTextContent()
    const pageText = content.items.map((item) => ('str' in item ? item.str : '')).join(' ')
    pageTexts.push(pageText)
  }
  return pageTexts.join('\n\n').trim()
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
    throw new TextExtractionError(`Could not read "${file.name}". The file may be corrupted.`)
  }

  if (!text) {
    throw new TextExtractionError(`"${file.name}" doesn't appear to contain any readable text.`)
  }

  return text
}
