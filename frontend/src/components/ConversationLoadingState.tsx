import { Sparkles } from 'lucide-react'
import IndeterminateBar from './IndeterminateBar'

interface ConversationLoadingStateProps {
  message: string
}

// Reuses AnalyzingState's exact building blocks (IndeterminateBar, the
// pulsing gradient-circle Sparkles avatar) in a compact, chat-sized card
// instead of that component's full dashboard-skeleton layout — this is a
// much smaller loading footprint (one question card, not a whole page of
// skeletons), so it borrows the pieces rather than the whole component.
export default function ConversationLoadingState({ message }: ConversationLoadingStateProps) {
  return (
    <div className="animate-panel-fade overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <IndeterminateBar />
      <div className="flex items-center gap-3 px-6 py-8">
        <span className="flex h-9 w-9 shrink-0 animate-pulse items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
          <Sparkles size={16} className="text-white" />
        </span>
        <p aria-live="polite" className="text-sm font-medium text-gray-500">
          {message}
        </p>
      </div>
    </div>
  )
}
