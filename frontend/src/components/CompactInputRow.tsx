import { CheckCircle2 } from 'lucide-react'

interface CompactInputRowProps {
  label: string
  value: string
  onChange: () => void
}

// One row of the collapsed input summary card shown above the dashboard
// after a successful analysis (requirement 6) — reused identically for
// both the resume row and the job description row.
export default function CompactInputRow({ label, value, onChange }: CompactInputRowProps) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <div className="min-w-0">
        <p className="text-xs font-medium text-gray-400">{label}</p>
        <p className="mt-0.5 flex items-center gap-1.5 truncate text-sm text-gray-700">
          <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />
          <span className="truncate">{value}</span>
        </p>
      </div>
      <button
        type="button"
        onClick={onChange}
        className="shrink-0 text-xs font-medium text-indigo-600 hover:underline"
      >
        Change
      </button>
    </div>
  )
}
