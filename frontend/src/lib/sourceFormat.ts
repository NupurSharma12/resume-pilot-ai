import type { SourceFormat } from '../data/tailoringSuggestionsTypes'

// Mirrors the backend's `detect_source_format`
// (app.export.service.detect_source_format) exactly, for the same
// reason: only the *filename*'s extension is ever inspected, never file
// content -- no original file bytes are retained anywhere after upload
// (see docs/features/interactive-tailored-resume.md). Used here purely
// for display (labeling "originally uploaded as X" in the review UI) --
// the backend independently recomputes the same thing server-side to
// decide `default_export_format`, so this never needs to be trusted as
// authoritative, only as a UI hint.
const EXTENSION_TO_SOURCE_FORMAT: Record<string, SourceFormat> = {
  '.pdf': 'pdf',
  '.docx': 'docx',
  '.md': 'markdown',
  '.markdown': 'markdown',
  '.txt': 'plain_text',
}

export function detectSourceFormatFromFilename(filename: string | null): SourceFormat | null {
  if (!filename) return null
  const match = /\.[^./\\]+$/.exec(filename.toLowerCase())
  if (!match) return null
  return EXTENSION_TO_SOURCE_FORMAT[match[0]] ?? null
}

// Turns a filename like "Nupur_Sharma_Resume.pdf" into a candidate
// filename *stem* ("Nupur_Sharma_Resume") for `filename_base` in an
// export request. The backend sanitizes this again server-side (see
// `app.export.service.sanitize_filename_base`) regardless of what's sent
// here -- this is only a best-effort starting point, not a security
// boundary.
export function candidateFilenameBase(filename: string | null): string | null {
  if (!filename) return null
  const withoutExtension = filename.replace(/\.[^./\\]+$/, '')
  return withoutExtension.length > 0 ? withoutExtension : null
}
