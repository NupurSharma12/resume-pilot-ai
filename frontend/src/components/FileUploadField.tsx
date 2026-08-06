import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, UploadCloud } from 'lucide-react'
import Button from './Button'
import type { ExtractionStatus } from '../hooks/useExtractedFile'

interface FileUploadFieldProps {
  accept: string
  acceptLabel: string
  variant?: 'dropzone' | 'button'
  buttonLabel?: string
  file: File | null
  // Name of a file that was resolved in a previous mount (its real `File`
  // object can't be restored) — shown in the same "selected" row as
  // `file` so a restored value never renders as an empty picker.
  restoredFileName?: string | null
  status: ExtractionStatus
  error: string | null
  onFileSelected: (file: File) => void
  onRemove: () => void
}

function isAcceptedFile(fileName: string, accept: string): boolean {
  const extension = `.${fileName.split('.').pop()?.toLowerCase() ?? ''}`
  return accept
    .split(',')
    .map((ext) => ext.trim().toLowerCase())
    .includes(extension)
}

// Generic drag & drop / browse file field, reused for both the resume
// (dropzone variant) and the job description's file-upload alternative
// (button variant). Only the empty-state affordance differs between the
// two — the moment a file is selected, both render the exact same compact
// "✓ filename / Change / Remove" row, so a file looks identical regardless
// of which context it was uploaded from.
export default function FileUploadField({
  accept,
  acceptLabel,
  variant = 'dropzone',
  buttonLabel = 'Browse Files',
  file,
  restoredFileName = null,
  status,
  error,
  onFileSelected,
  onRemove,
}: FileUploadFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragActive, setIsDragActive] = useState(false)
  const [rejectionError, setRejectionError] = useState<string | null>(null)
  // "Change," for the dropzone variant, should bring back the full
  // drag-and-drop affordance -- not jump straight to the native file
  // picker (that regressed to feeling like every other plain file input,
  // and threw away the drag & drop entry point entirely once a file
  // already existed, which is true almost immediately after a restored
  // session repopulates `restoredFileName`). This flag toggles the
  // *same* dropzone markup used for the empty state back into view
  // instead of duplicating it — see `dropzoneContent` below.
  const [isReplacing, setIsReplacing] = useState(false)

  function openPicker() {
    inputRef.current?.click()
  }

  function handleFile(candidate: File) {
    if (!isAcceptedFile(candidate.name, accept)) {
      setRejectionError(`Unsupported file type. Please use ${acceptLabel}.`)
      return
    }
    setRejectionError(null)
    setIsReplacing(false)
    onFileSelected(candidate)
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0]
    if (selected) handleFile(selected)
    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setIsDragActive(false)
    const dropped = event.dataTransfer.files[0]
    if (dropped) handleFile(dropped)
  }

  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      accept={accept}
      className="hidden"
      onChange={handleInputChange}
    />
  )

  const displayName = file?.name ?? restoredFileName

  if (displayName && !isReplacing) {
    return (
      <div>
        <div className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
          <span className="flex min-w-0 items-center gap-2 text-sm text-gray-700">
            {status === 'extracting' && (
              <Loader2 size={16} className="shrink-0 animate-spin text-gray-400" />
            )}
            {status === 'ready' && (
              <CheckCircle2 size={16} className="shrink-0 text-emerald-500" />
            )}
            {status === 'error' && <AlertTriangle size={16} className="shrink-0 text-rose-500" />}
            <span className="truncate">{displayName}</span>
          </span>
          <span className="flex shrink-0 items-center gap-3 text-xs font-medium">
            <button
              type="button"
              onClick={() => (variant === 'dropzone' ? setIsReplacing(true) : openPicker())}
              className="text-indigo-600 hover:underline"
            >
              Change
            </button>
            <button
              type="button"
              onClick={onRemove}
              className="text-gray-400 hover:text-gray-600 hover:underline"
            >
              Remove
            </button>
          </span>
        </div>
        {status === 'error' && error && <p className="mt-1.5 text-xs text-rose-500">{error}</p>}
        {hiddenInput}
      </div>
    )
  }

  if (variant === 'button') {
    return (
      <div>
        <Button variant="outline" icon={<UploadCloud size={16} />} onClick={openPicker}>
          {buttonLabel}
        </Button>
        {rejectionError && <p className="mt-1.5 text-xs text-rose-500">{rejectionError}</p>}
        {hiddenInput}
      </div>
    )
  }

  // The dropzone itself: rendered both for the true empty state (no file
  // yet) and for "Change" on an already-selected/restored file
  // (`isReplacing`) -- one block, not a second copy of the same markup.
  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setIsDragActive(true)
        }}
        onDragLeave={() => setIsDragActive(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          isDragActive ? 'border-indigo-400 bg-indigo-50/50' : 'border-gray-300 bg-gray-50/50'
        }`}
      >
        <UploadCloud size={22} className="text-gray-400" />
        <p className="text-sm text-gray-600">
          Drag & drop your file here, or{' '}
          <button
            type="button"
            onClick={openPicker}
            className="font-medium text-indigo-600 hover:underline"
          >
            Browse Files
          </button>
        </p>
        <p className="text-xs text-gray-400">{acceptLabel}</p>
      </div>
      {isReplacing && displayName && (
        <button
          type="button"
          onClick={() => setIsReplacing(false)}
          className="mt-1.5 text-xs font-medium text-gray-400 hover:text-gray-600 hover:underline"
        >
          Cancel
        </button>
      )}
      {rejectionError && <p className="mt-1.5 text-xs text-rose-500">{rejectionError}</p>}
      {hiddenInput}
    </div>
  )
}
