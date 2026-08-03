import { useState } from 'react'
import { extractTextFromFile, TextExtractionError } from '../lib/extractText'

export type ExtractionStatus = 'idle' | 'extracting' | 'ready' | 'error'

// Shared by ResumeInput and JobDescriptionInput's file-upload path, so
// "pick a file, extract its text, track status/errors" is written once —
// each caller just needs the file object and its resolved text.
export function useExtractedFile() {
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState<string | null>(null)
  const [status, setStatus] = useState<ExtractionStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  async function selectFile(newFile: File): Promise<void> {
    setFile(newFile)
    setText(null)
    setStatus('extracting')
    setError(null)
    try {
      const extracted = await extractTextFromFile(newFile)
      setText(extracted)
      setStatus('ready')
    } catch (err) {
      setError(err instanceof TextExtractionError ? err.message : 'Could not read this file.')
      setStatus('error')
    }
  }

  function clear(): void {
    setFile(null)
    setText(null)
    setStatus('idle')
    setError(null)
  }

  return { file, text, status, error, selectFile, clear }
}
