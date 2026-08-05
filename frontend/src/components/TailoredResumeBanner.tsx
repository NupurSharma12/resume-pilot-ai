import { Wand2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'
import { useResumeSession } from '../session/ResumeSessionContext'

// Reads `careerConversationStatus`/`tailoredResumeResult` from
// `ResumeSessionProvider` rather than owning any state of its own -- the
// same single-source-of-truth signals TailoredResumePage itself renders
// from, so this banner's CTA label can never drift out of sync with what
// clicking it actually leads to.
export default function TailoredResumeBanner() {
  const navigate = useNavigate()
  const { careerConversationStatus, tailoredResumeResult } = useResumeSession()

  const isConversationComplete = careerConversationStatus === 'complete'
  const hasResult = tailoredResumeResult !== null

  const ctaLabel = !isConversationComplete
    ? 'Complete Career Conversation first.'
    : hasResult
      ? 'View Tailored Resume'
      : 'Generate Tailored Resume'

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="flex items-center justify-between gap-6 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Wand2 size={22} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Tailored Resume Generator</h3>
            <p className="mt-1 text-sm text-gray-500">
              {isConversationComplete
                ? 'Generate an evidence-backed resume for this job description.'
                : 'Recover evidence in a Career Conversation first, so this has something real to ground a rewrite in.'}
            </p>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <Button
            variant="outline"
            icon={<Wand2 size={16} />}
            disabled={!isConversationComplete}
            onClick={() => navigate('/tailored-resume')}
          >
            {ctaLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
