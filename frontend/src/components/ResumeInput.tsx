import { useEffect, useRef } from 'react'
import FileUploadField from './FileUploadField'
import { useExtractedFile } from '../hooks/useExtractedFile'

export interface ResumeInputValue {
  text: string
  fileName: string
}

interface ResumeInputProps {
  // The currently-resolved resume, owned by a parent (see DashboardLayout).
  // Treated as the source of truth for what's "current": a real `File`
  // object can't survive this component remounting (e.g. on route
  // navigation), but the filename/extracted text can and do — so this is
  // what re-populates the editor instead of showing it empty.
  value: ResumeInputValue | null
  onChange: (value: ResumeInputValue | null) => void
}

const ACCEPT = '.pdf,.docx,.txt,.md'
const ACCEPT_LABEL = 'PDF, DOCX, TXT, or MD'

export default function ResumeInput({ value, onChange }: ResumeInputProps) {
  const { file, text, status, error, selectFile, clear } = useExtractedFile()

  // This component can remount when navigating between routes (its
  // internal file/extraction state doesn't survive that, since a `File`
  // handle isn't meaningfully restorable). Only report a change once the
  // user has actually picked or removed a file *in this mount* — guarding
  // on "has selectFile/clear been called" rather than "is this the first
  // effect run" so it stays correct under StrictMode's dev-only double
  // effect invocation, which would otherwise still let a stale second
  // pass wipe an already-resolved value.
  const hasInteracted = useRef(false)

  function handleSelectFile(newFile: File) {
    hasInteracted.current = true
    void selectFile(newFile)
  }

  function handleRemove() {
    hasInteracted.current = true
    if (file) {
      clear()
    } else {
      onChange(null)
    }
  }

  useEffect(() => {
    if (!hasInteracted.current) return
    if (file && status === 'ready' && text) {
      onChange({ text, fileName: file.name })
    } else {
      onChange(null)
    }
  }, [file, status, text, onChange])

  // A file picked during this mount always wins; otherwise fall back to
  // showing whatever `value` already holds, so the editor never looks
  // empty just because the live `File` handle is gone.
  const restoredFileName = !file ? (value?.fileName ?? null) : null

  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-gray-900">Resume</p>
      <FileUploadField
        variant="dropzone"
        accept={ACCEPT}
        acceptLabel={ACCEPT_LABEL}
        file={file}
        restoredFileName={restoredFileName}
        status={file ? status : 'ready'}
        error={file ? error : null}
        onFileSelected={handleSelectFile}
        onRemove={handleRemove}
      />
    </div>
  )
}
