import type { ExportFormat, SourceFormat } from '../data/tailoringSuggestionsTypes'

// Mirrors the backend's `detect_source_format`
// (app.export.service.detect_source_format) exactly, for the same
// reason: only the *filename*'s extension is ever inspected, never file
// content -- no original file bytes are retained anywhere after upload
// (see docs/features/interactive-tailored-resume.md).
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

// Mirrors the backend's `_ALL_EXPORT_FORMATS = list(ExportFormat)`
// (app.api.v1.endpoints.tailoring_suggestions) exactly: every export
// format this application supports, always, regardless of plan or
// resume -- a constant, not plan-specific data. The backend computes
// this fresh on every `/tailoring-suggestions` response and never
// persists it (see that endpoint's own docstring), so a rehydrated
// session has nothing to read it back from either -- this constant is
// the one place both a live generation and a History rehydration derive
// it from, identically, rather than one of them silently ending up with
// an empty list.
export const ALL_EXPORT_FORMATS: ExportFormat[] = ['txt', 'markdown', 'docx', 'pdf']

// Mirrors the backend's `ORIGINAL_FORMAT_EXPORT` (app.export.service)
// exactly, including its one deliberate gap: PDF has no entry there
// (regenerating an exact PDF isn't offered as a *default* -- a candidate
// can still choose "Download PDF" explicitly from the full format list
// above), so a PDF-sourced resume's default falls back to `txt`, same as
// an unrecognized/missing filename. Like `detectSourceFormatFromFilename`,
// this is now the authoritative source for `default_export_format` on
// both the live-generation and rehydrated-from-History paths -- neither
// reads a `default_export_format` off a stored/persisted plan (see
// `rehydrateFromJobPreparation.ts`'s docstring for why that's never
// reliably present).
const DEFAULT_EXPORT_FORMAT_FOR_SOURCE: Partial<Record<SourceFormat, ExportFormat>> = {
  plain_text: 'txt',
  markdown: 'markdown',
  docx: 'docx',
}

export function defaultExportFormatForSourceFormat(
  sourceFormat: SourceFormat | null,
): ExportFormat {
  if (sourceFormat === null) return 'txt'
  return DEFAULT_EXPORT_FORMAT_FOR_SOURCE[sourceFormat] ?? 'txt'
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
