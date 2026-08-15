import { AlertTriangle } from 'lucide-react'
import Button from './Button'

interface DeleteConfirmationDialogProps {
  jobTitle: string
  company: string | null
  isLoading: boolean
  error: string
  onCancel: () => void
  onConfirm: () => void
}

// The small confirmation shown before "Delete" soft-deletes a preparation
// -- see the History Test Isolation & Delete design review. Deliberately
// no database terminology ("soft delete", "deleted_at") anywhere in this
// copy -- a candidate only ever sees "removed from your History."
export default function DeleteConfirmationDialog({
  jobTitle,
  company,
  isLoading,
  error,
  onCancel,
  onConfirm,
}: DeleteConfirmationDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-preparation-title"
    >
      <div className="w-full max-w-sm rounded-2xl border border-gray-200 bg-white p-6 shadow-xl">
        <h2 id="delete-preparation-title" className="font-semibold text-gray-900">
          Delete this preparation?
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          {jobTitle}
          {company ? ` · ${company}` : ''}
        </p>
        <p className="mt-3 text-sm text-gray-500">This will remove it from your History.</p>

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
          <Button variant="danger" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? 'Deleting…' : 'Delete'}
          </Button>
        </div>
      </div>
    </div>
  )
}
