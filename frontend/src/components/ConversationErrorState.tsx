import { AlertTriangle, RotateCw } from 'lucide-react'
import Button from './Button'

interface ConversationErrorStateProps {
  message: string
  onRetry: () => void
}

// Same card/icon/copy-layout as AnalysisErrorState (rounded-2xl white
// card, rose icon tile, outline retry button) — kept as its own small
// component rather than reusing AnalysisErrorState directly, since that
// component's heading text ("Analysis didn't complete") is specific to
// the resume-analysis flow, which this feature must not touch.
export default function ConversationErrorState({ message, onRetry }: ConversationErrorStateProps) {
  return (
    <div className="animate-panel-fade flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
        <AlertTriangle size={22} />
      </div>
      <div>
        <h2 className="font-semibold text-gray-900">Conversation didn't load</h2>
        <p className="mt-1.5 max-w-sm text-sm text-gray-500">{message}</p>
      </div>
      <Button variant="outline" icon={<RotateCw size={16} />} onClick={onRetry}>
        Try Again
      </Button>
    </div>
  )
}
