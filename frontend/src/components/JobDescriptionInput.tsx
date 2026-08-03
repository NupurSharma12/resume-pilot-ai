import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import FileUploadField from './FileUploadField'
import { useExtractedFile } from '../hooks/useExtractedFile'

export interface JobDescriptionInputValue {
  text: string
  fileName: string | null
}

interface JobDescriptionInputProps {
  onChange: (value: JobDescriptionInputValue | null) => void
}

const ACCEPT = '.pdf,.docx,.txt,.md'
const ACCEPT_LABEL = 'PDF, DOCX, TXT, or MD'

// Two mutually-exclusive ways to provide a job description: paste into the
// textarea, or upload a file. Both the typed text and the file/extraction
// state are local to this component (same "only lift the resolved value"
// pattern as ResumeInput) — the parent only ever sees the final
// {text, fileName} via onChange.
export default function JobDescriptionInput({ onChange }: JobDescriptionInputProps) {
  const [text, setText] = useState('')
  const { file, text: fileText, status, error, selectFile, clear } = useExtractedFile()

  useEffect(() => {
    if (file && status === 'ready' && fileText) {
      onChange({ text: fileText, fileName: file.name })
    } else if (!file && text.trim()) {
      onChange({ text: text.trim(), fileName: null })
    } else {
      onChange(null)
    }
  }, [file, status, fileText, text, onChange])

  const characterCount = text.trim().length

  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-gray-900">Job Description</p>

      {file ? (
        <FileUploadField
          variant="button"
          accept={ACCEPT}
          acceptLabel={ACCEPT_LABEL}
          file={file}
          status={status}
          error={error}
          onFileSelected={selectFile}
          onRemove={clear}
        />
      ) : (
        <>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
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
              onFileSelected={selectFile}
              onRemove={clear}
            />
          </div>
        </>
      )}
    </div>
  )
}
