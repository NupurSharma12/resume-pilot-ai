import { Sparkles } from 'lucide-react'
import Badge from './Badge'
import type { EstimatedImpact } from '../data/careerConversationTypes'

interface ConversationQuestionBubbleProps {
  topic: string
  question: string
  evidenceGoal?: string
  estimatedImpact?: EstimatedImpact
}

const IMPACT_BADGE_VARIANT: Record<EstimatedImpact, 'green' | 'amber' | 'gray'> = {
  high: 'green',
  medium: 'amber',
  low: 'gray',
}

// The AI side of the conversation: the same gradient-circle "avatar"
// treatment used for the app's own logo mark (see Sidebar) and for the
// analyzing-state's pulsing icon, left-aligned like a chat message.
// `evidenceGoal`/`estimatedImpact` are optional so this same component
// renders both the current open question (which has them) and each past
// history exchange (which — per the backend's Topic/Question/Answer-only
// history shape — doesn't).
export default function ConversationQuestionBubble({
  topic,
  question,
  evidenceGoal,
  estimatedImpact,
}: ConversationQuestionBubbleProps) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
        <Sparkles size={16} className="text-white" />
      </div>
      <div className="max-w-[85%] space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="gray">{topic}</Badge>
          {estimatedImpact && (
            <Badge variant={IMPACT_BADGE_VARIANT[estimatedImpact]}>
              {estimatedImpact.toUpperCase()} IMPACT
            </Badge>
          )}
        </div>
        <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-white px-4 py-3 text-sm leading-relaxed text-gray-700">
          {question}
        </div>
        {evidenceGoal && <p className="text-xs text-gray-400">Why we're asking: {evidenceGoal}</p>}
      </div>
    </div>
  )
}
