interface ExtractedContentCardProps {
  title: string
  fileName: string | null
  text: string
  emptyMessage: string
}

// Shared read-only viewer for the Resume and Job Description pages — same
// "card with filename + extracted text" shape for both, so the two pages
// don't each reinvent this markup.
export default function ExtractedContentCard({
  title,
  fileName,
  text,
  emptyMessage,
}: ExtractedContentCardProps) {
  if (!text) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900">{title}</p>
        {fileName && <p className="text-xs text-gray-400">{fileName}</p>}
      </div>
      <pre className="mt-4 max-h-[600px] overflow-y-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-4 font-sans text-sm leading-relaxed text-gray-700">
        {text}
      </pre>
    </div>
  )
}
