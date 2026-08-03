import { useEffect, useRef, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import FileUploadField from './FileUploadField'
import { useExtractedFile } from '../hooks/useExtractedFile'

export interface JobDescriptionInputValue {
  text: string
  fileName: string | null
}

interface JobDescriptionInputProps {
  // The currently-resolved JD, owned by a parent (see DashboardLayout) —
  // same "source of truth for what's current" role as ResumeInput's
  // `value` prop.
  value: JobDescriptionInputValue | null
  onChange: (value: JobDescriptionInputValue | null) => void
}

const ACCEPT = '.pdf,.docx,.txt,.md'
const ACCEPT_LABEL = 'PDF, DOCX, TXT, or MD'

// Two mutually-exclusive ways to provide a job description: paste into the
// textarea, or upload a file. Both the typed text and the file/extraction
// state are local to this component (same "only lift the resolved value"
// pattern as ResumeInput) — the parent only ever sees the final
// {text, fileName} via onChange.
export default function JobDescriptionInput({ value, onChange }: JobDescriptionInputProps) {
  // Seeds from `value` only for the pasted-text case (a file-derived
  // value renders through the FileUploadField restoration path below
  // instead) — so remounting with previously-pasted text still shows it.
  const [text, setText] = useState(value?.fileName == null ? (value?.text ?? '') : '')
  const { file, text: fileText, status, error, selectFile, clear } = useExtractedFile()

  // See ResumeInput for why this guards on actual user interaction rather
  // than "is this the first effect run": StrictMode's dev-only double
  // effect invocation would otherwise let a stale second pass wipe an
  // already-resolved value on every mount, not just navigation.
  const hasInteracted = useRef(false)

  function handleTextChange(newText: string) {
    hasInteracted.current = true
    setText(newText)
  }

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
    if (file && status === 'ready' && fileText) {
      onChange({ text: fileText, fileName: file.name })
    } else if (!file && text.trim()) {
      onChange({ text: text.trim(), fileName: null })
    } else {
      onChange(null)
    }
  }, [file, status, fileText, text, onChange])

  // A file picked during this mount always wins; otherwise fall back to
  // a file-derived `value` from a previous mount, so it still renders as
  // a resolved file row rather than an empty picker.
  const restoredFileName = !file ? (value?.fileName ?? null) : null
  const showFileRow = Boolean(file) || Boolean(restoredFileName)

  const characterCount = text.trim().length

  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-gray-900">Job Description</p>

      {showFileRow ? (
        <FileUploadField
          variant="button"
          accept={ACCEPT}
          acceptLabel={ACCEPT_LABEL}
          file={file}
          restoredFileName={restoredFileName}
          status={file ? status : 'ready'}
          error={file ? error : null}
          onFileSelected={handleSelectFile}
          onRemove={handleRemove}
        />
      ) : (
        <>
          <textarea
            value={text}
            onChange={(event) => handleTextChange(event.target.value)}
            placeholder="Paste the Job Description here..."
            rows={6}
            className="w-full resize-none rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700 placeholder:text-gray-400 focus:border-indigo-400 focus:outline-none"
          />

          {characterCount > 0 && (
            <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-emerald-600">
              <CheckCircle2 size={14} />
              {characterCount} characters detected
            </p>
          )}

          <div className="mt-3 flex items-center gap-3">
            <div className="h-px flex-1 bg-gray-200" />
            <span className="text-xs text-gray-400">or</span>
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          <div className="mt-3">
            <FileUploadField
              variant="button"
              buttonLabel="Upload JD File"
              accept={ACCEPT}
              acceptLabel={ACCEPT_LABEL}
              file={file}
              status={status}
              error={error}
              onFileSelected={handleSelectFile}
              onRemove={handleRemove}
            />
          </div>
        </>
      )}
    </div>
  )
}
