import { AlertTriangle, RotateCw } from 'lucide-react'
import Button from './Button'

interface AnalysisErrorStateProps {
  message: string
  onRetry: () => void
}

// Deliberately styled like the rest of the app (rounded-2xl white card,
// same border/spacing as every other panel) rather than a jarring red
// banner — a failed analysis is a normal, expected outcome to design for,
// not an exceptional crash state.
export default function AnalysisErrorState({ message, onRetry }: AnalysisErrorStateProps) {
  return (
    <div className="animate-panel-fade flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
        <AlertTriangle size={22} />
      </div>
      <div>
        <h2 className="font-semibold text-gray-900">Analysis didn't complete</h2>
        <p className="mt-1.5 max-w-sm text-sm text-gray-500">{message}</p>
      </div>
      <Button variant="outline" icon={<RotateCw size={16} />} onClick={onRetry}>
        Try Again
      </Button>
    </div>
  )
}
