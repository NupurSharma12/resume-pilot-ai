import { AlertTriangle } from 'lucide-react'
import Button from './Button'
import CheckpointList from './CheckpointList'
import type { CheckpointStatus } from '../data/jobPreparationHistoryTypes'

interface ContinuePreparationDialogProps {
  jobTitle: string
  company: string | null
  checkpoints: CheckpointStatus
  isLoading: boolean
  error: string
  onCancel: () => void
  onConfirm: () => void
}

// The small confirmation shown before "Continue" rehydrates a session --
// see the History Resumability design review. Deliberately reuses the
// exact same `CheckpointList` History's own list/detail views render, so
// the checkmarks shown here always agree with what a candidate already
// saw in History -- no separate "confirmation summary" formatting to keep
// in sync.
export default function ContinuePreparationDialog({
  jobTitle,
  company,
  checkpoints,
  isLoading,
  error,
  onCancel,
  onConfirm,
}: ContinuePreparationDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="continue-preparation-title"
    >
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-xl">
        <h2 id="continue-preparation-title" className="font-semibold text-gray-900">
          Continue this preparation?
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          {jobTitle}
          {company ? ` · ${company}` : ''}
        </p>
        <p className="mt-3 text-sm text-gray-500">We've saved your progress.</p>
        <div className="mt-3">
          <CheckpointList checkpoints={checkpoints} />
        </div>

        {error && (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-100 bg-rose-50/60 p-3">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-rose-500" aria-hidden="true" />
            <p className="text-sm text-rose-600">{error}</p>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onCancel} disabled={isLoading}>
            Cancel
          </Button>
          <Button variant="solid" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? 'Continuing…' : 'Continue'}
          </Button>
        </div>
      </div>
    </div>
  )
}
