import { AlertTriangle, RotateCw } from 'lucide-react'
import Button from './Button'

interface TailoringErrorStateProps {
  message: string
  onRetry: () => void
}

// Same card/icon/copy-layout as ConversationErrorState (rounded-2xl white
// card, rose icon tile, outline retry button) — kept as its own small
// component rather than reusing ConversationErrorState directly, since
// that component's heading text ("Conversation didn't load") is specific
// to the Career Conversation flow.
export default function TailoringErrorState({ message, onRetry }: TailoringErrorStateProps) {
  return (
    <div className="animate-panel-fade flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
        <AlertTriangle size={22} />
      </div>
      <div>
        <h2 className="font-semibold text-gray-900">Tailoring didn't complete</h2>
        <p className="mt-1.5 max-w-sm text-sm text-gray-500">{message}</p>
      </div>
      <Button variant="outline" icon={<RotateCw size={16} />} onClick={onRetry}>
        Try Again
      </Button>
    </div>
  )
}
