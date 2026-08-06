import { Download } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'
import type { ExportFormat, SourceFormat } from '../data/tailoringSuggestionsTypes'

const SOURCE_FORMAT_LABELS: Record<SourceFormat, string> = {
  pdf: 'PDF',
  docx: 'DOCX',
  markdown: 'Markdown',
  plain_text: 'plain text',
}

const FORMAT_LABELS: Record<ExportFormat, string> = {
  txt: 'Download TXT',
  markdown: 'Download Markdown',
  docx: 'Download DOCX',
  pdf: 'Download PDF',
}

// Fixed, honest per-format fidelity copy -- known statically from the
// export architecture itself (see app.export.service.ExportService),
// not something that needs a round trip to the backend to state
// correctly. TXT/Markdown are content-faithful re-renderings of the
// final resume (no visual styling to speak of, so "preserved" doesn't
// meaningfully apply); DOCX/PDF are always freshly generated documents,
// never a reproduction of any original file's layout -- see this
// feature's docs for why that's a hard architectural limit, not a
// missing feature.
const FORMAT_FIDELITY_COPY: Record<ExportFormat, string> = {
  txt: 'Plain text. Clean, content-faithful export of your final resume.',
  markdown: 'Markdown. Clean, content-faithful export of your final resume.',
  docx: 'Regenerated DOCX. A fresh document in a clean layout -- your original file\'s fonts and styling are not preserved.',
  pdf: 'Regenerated PDF. An ATS-friendly layout generated from scratch -- not a reproduction of any original file\'s design.',
}

interface TailoringDownloadPanelProps {
  availableFormats: ExportFormat[]
  defaultFormat: ExportFormat
  sourceFormat: SourceFormat | null
  exportingFormat: ExportFormat | null
  exportError: string | null
  onDownload: (format: ExportFormat) => void
}

// Stage 5's download controls. Only ever shows formats the backend
// actually reported as available for this plan (`availableFormats`) --
// never a hardcoded list -- and the default format is both labeled and
// visually distinguished, never silently assumed. An export failure
// shows inline, right here, without touching whether the final resume
// preview above it stays visible (see TailoredResumePage's export
// handler for why that's a hard requirement, not a UI nicety).
export default function TailoringDownloadPanel({
  availableFormats,
  defaultFormat,
  sourceFormat,
  exportingFormat,
  exportError,
  onDownload,
}: TailoringDownloadPanelProps) {
  const orderedFormats = [...availableFormats].sort((a, b) =>
    a === defaultFormat ? -1 : b === defaultFormat ? 1 : 0,
  )

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Download Tailored Resume</h3>
      <p className="mt-1 text-sm text-gray-500">
        {sourceFormat &&
          `Originally uploaded as ${SOURCE_FORMAT_LABELS[sourceFormat]}. `}
        Formatting is honestly labeled below -- DOCX and PDF are always freshly generated, never a
        reproduction of your original file's exact layout.
      </p>

      <ul className="mt-4 space-y-3">
        {orderedFormats.map((format) => (
          <li
            key={format}
            className="flex flex-col gap-2 rounded-xl border border-gray-100 p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-gray-900">
                  {FORMAT_LABELS[format]}
                </span>
                {format === defaultFormat && <Badge variant="green">Default</Badge>}
              </div>
              <p className="mt-1 text-xs text-gray-500">{FORMAT_FIDELITY_COPY[format]}</p>
            </div>
            <Button
              variant={format === defaultFormat ? 'solid' : 'outline'}
              icon={<Download size={16} />}
              disabled={exportingFormat !== null}
              onClick={() => onDownload(format)}
            >
              {exportingFormat === format ? 'Preparing…' : FORMAT_LABELS[format]}
            </Button>
          </li>
        ))}
      </ul>

      {exportError && (
        <div className="mt-4 rounded-xl border border-rose-100 bg-rose-50/60 p-4">
          <p className="text-sm text-rose-600">{exportError}</p>
        </div>
      )}
    </div>
  )
}
