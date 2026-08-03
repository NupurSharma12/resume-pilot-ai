import { useEffect } from 'react'
import FileUploadField from './FileUploadField'
import { useExtractedFile } from '../hooks/useExtractedFile'

export interface ResumeInputValue {
  text: string
  fileName: string
}

interface ResumeInputProps {
  onChange: (value: ResumeInputValue | null) => void
}

const ACCEPT = '.pdf,.docx,.txt,.md'
const ACCEPT_LABEL = 'PDF, DOCX, TXT, or MD'

// Owns its own file/extraction-state (via useExtractedFile) — the parent
// only ever sees the resolved {text, fileName} once extraction succeeds,
// or null while empty/extracting/failed, per "keep state local unless
// lifting is necessary."
export default function ResumeInput({ onChange }: ResumeInputProps) {
  const { file, text, status, error, selectFile, clear } = useExtractedFile()

  useEffect(() => {
    if (file && status === 'ready' && text) {
      onChange({ text, fileName: file.name })
    } else {
      onChange(null)
    }
  }, [file, status, text, onChange])

  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-gray-900">Resume</p>
      <FileUploadField
        variant="dropzone"
        accept={ACCEPT}
        acceptLabel={ACCEPT_LABEL}
        file={file}
        status={status}
        error={error}
        onFileSelected={selectFile}
        onRemove={clear}
      />
    </div>
  )
}
