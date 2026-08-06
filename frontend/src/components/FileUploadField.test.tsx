import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FileUploadField from './FileUploadField'

const ACCEPT = '.pdf,.docx,.txt,.md'

function baseProps() {
  return {
    accept: ACCEPT,
    acceptLabel: 'PDF, DOCX, TXT, or MD',
    file: null,
    restoredFileName: null,
    status: 'idle' as const,
    error: null,
    onFileSelected: vi.fn(),
    onRemove: vi.fn(),
  }
}

describe('FileUploadField (dropzone variant): empty state', () => {
  it('shows the drag-and-drop dropzone when there is no file yet', () => {
    render(<FileUploadField {...baseProps()} />)

    expect(screen.getByText(/drag & drop your file here/i)).toBeInTheDocument()
  })

  it('selecting via Browse Files calls onFileSelected with the picked file', () => {
    const onFileSelected = vi.fn()
    render(<FileUploadField {...baseProps()} onFileSelected={onFileSelected} />)

    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })

    expect(onFileSelected).toHaveBeenCalledWith(file)
  })

  it('dropping a file calls onFileSelected', () => {
    const onFileSelected = vi.fn()
    render(<FileUploadField {...baseProps()} onFileSelected={onFileSelected} />)

    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    const dropzone = screen.getByText(/drag & drop your file here/i).closest('div')!
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } })

    expect(onFileSelected).toHaveBeenCalledWith(file)
  })

  it('rejects an unsupported extension without calling onFileSelected', () => {
    const onFileSelected = vi.fn()
    render(<FileUploadField {...baseProps()} onFileSelected={onFileSelected} />)

    const file = new File(['content'], 'resume.jpeg', { type: 'image/jpeg' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByText(/unsupported file type/i)).toBeInTheDocument()
  })
})

describe('FileUploadField (dropzone variant): a file already exists', () => {
  it('shows the compact filename row, not the dropzone, once a file is selected', () => {
    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    render(<FileUploadField {...baseProps()} file={file} status="ready" />)

    expect(screen.getByText('resume.pdf')).toBeInTheDocument()
    expect(screen.queryByText(/drag & drop your file here/i)).not.toBeInTheDocument()
  })

  it('shows the compact row for a restored filename from a previous session too', () => {
    render(<FileUploadField {...baseProps()} restoredFileName="old-resume.pdf" />)

    expect(screen.getByText('old-resume.pdf')).toBeInTheDocument()
  })

  it('clicking Change brings back the full drag-and-drop dropzone, not the native picker directly', () => {
    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    render(<FileUploadField {...baseProps()} file={file} status="ready" />)

    fireEvent.click(screen.getByRole('button', { name: /change/i }))

    expect(screen.getByText(/drag & drop your file here/i)).toBeInTheDocument()
    // The previously selected filename's compact row is gone while replacing.
    expect(screen.queryByRole('button', { name: /^remove$/i })).not.toBeInTheDocument()
  })

  it('dropping a new file while replacing calls onFileSelected and returns to the compact row', () => {
    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    const onFileSelected = vi.fn()
    const { rerender } = render(
      <FileUploadField {...baseProps()} file={file} status="ready" onFileSelected={onFileSelected} />,
    )

    fireEvent.click(screen.getByRole('button', { name: /change/i }))
    expect(screen.getByText(/drag & drop your file here/i)).toBeInTheDocument()

    const newFile = new File(['new content'], 'new-resume.pdf', { type: 'application/pdf' })
    const dropzone = screen.getByText(/drag & drop your file here/i).closest('div')!
    fireEvent.drop(dropzone, { dataTransfer: { files: [newFile] } })

    expect(onFileSelected).toHaveBeenCalledWith(newFile)

    // Once the parent supplies the new file back down as `file`, the
    // compact row reappears (mirrors how ResumeInput/JobDescriptionInput
    // actually flow a selection back through `onChange`/props).
    rerender(
      <FileUploadField {...baseProps()} file={newFile} status="ready" onFileSelected={onFileSelected} />,
    )
    expect(screen.getByText('new-resume.pdf')).toBeInTheDocument()
    expect(screen.queryByText(/drag & drop your file here/i)).not.toBeInTheDocument()
  })

  it('Cancel returns to the compact row without discarding the existing file', () => {
    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    const onRemove = vi.fn()
    render(<FileUploadField {...baseProps()} file={file} status="ready" onRemove={onRemove} />)

    fireEvent.click(screen.getByRole('button', { name: /change/i }))
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    expect(screen.getByText('resume.pdf')).toBeInTheDocument()
    expect(onRemove).not.toHaveBeenCalled()
  })

  it('Remove still works from the compact row', () => {
    const file = new File(['content'], 'resume.pdf', { type: 'application/pdf' })
    const onRemove = vi.fn()
    render(<FileUploadField {...baseProps()} file={file} status="ready" onRemove={onRemove} />)

    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }))

    expect(onRemove).toHaveBeenCalledTimes(1)
  })
})

describe('FileUploadField (button variant)', () => {
  it('Change opens the native picker directly -- no dropzone concept for this variant', () => {
    const file = new File(['content'], 'jd.txt', { type: 'text/plain' })
    render(<FileUploadField {...baseProps()} variant="button" file={file} status="ready" />)

    fireEvent.click(screen.getByRole('button', { name: /change/i }))

    // No drag-and-drop affordance ever exists for the button variant.
    expect(screen.queryByText(/drag & drop/i)).not.toBeInTheDocument()
    expect(screen.getByText('jd.txt')).toBeInTheDocument()
  })

  it('shows a Browse Files button when empty', () => {
    render(<FileUploadField {...baseProps()} variant="button" buttonLabel="Upload a file" />)

    expect(screen.getByRole('button', { name: /upload a file/i })).toBeInTheDocument()
  })
})
