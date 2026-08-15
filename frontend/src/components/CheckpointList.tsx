import { CheckCircle2, Circle } from 'lucide-react'
import type { CheckpointStatus } from '../data/jobPreparationHistoryTypes'

// The five independent checkpoints, in product order -- see
// docs/features/history-checkpoints-architecture.md. A checkpoint is
// "complete" iff its own timestamp is non-null; never inferred from any
// payload's shape (see CheckpointStatus's own docstring). Shared by
// HistoryPage's list/detail views and ContinuePreparationDialog's
// confirmation, so both always agree on labels/order.
export const CHECKPOINTS: { key: keyof CheckpointStatus; label: string }[] = [
  { key: 'initial_analysis_completed_at', label: 'Initial Analysis' },
  { key: 'career_conversation_completed_at', label: 'Career Conversation' },
  { key: 'tailoring_plan_completed_at', label: 'Tailoring Plan' },
  { key: 'applied_at', label: 'Tailored Resume' },
  { key: 'post_apply_analysis_completed_at', label: 'Re-analysis' },
]

export default function CheckpointList({ checkpoints }: { checkpoints: CheckpointStatus }) {
  return (
    <ul className="space-y-1.5">
      {CHECKPOINTS.map(({ key, label }) => {
        const complete = checkpoints[key] !== null
        return (
          <li
            key={key}
            className={`flex items-center gap-2 text-sm ${complete ? 'text-gray-900' : 'text-gray-400'}`}
          >
            {complete ? (
              <CheckCircle2 size={16} className="shrink-0 text-emerald-500" aria-hidden="true" />
            ) : (
              <Circle size={16} className="shrink-0 text-gray-300" aria-hidden="true" />
            )}
            {label}
          </li>
        )
      })}
    </ul>
  )
}
