import { CheckCircle2, Wand2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'
import { useResumeSession } from '../session/ResumeSessionContext'

interface ConversationCompleteCardProps {
  stopReason: string | null
  questionsAnswered: number
}

// The completion state's "what's next" half is a real, enabled entry
// point into the Tailoring Engine (this card only ever renders once the
// conversation itself is complete, so unlike TailoredResumeBanner there's
// no "complete the conversation first" state to show here). The CTA label
// mirrors TailoredResumeBanner's plan/final-resume lifecycle toggle,
// reading the same `tailoringPlan`/`finalTailoredResume` signals from
// ResumeSessionProvider, so it can't drift out of sync with what clicking
// it actually leads to.
export default function ConversationCompleteCard({
  stopReason,
  questionsAnswered,
}: ConversationCompleteCardProps) {
  const navigate = useNavigate()
  const { tailoringPlan, finalTailoredResume } = useResumeSession()
  const hasPlan = tailoringPlan !== null
  const hasResult = finalTailoredResume !== null

  return (
    <div className="animate-panel-fade overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="flex flex-col items-center gap-4 px-8 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-50 text-green-600">
          <CheckCircle2 size={24} />
        </div>
        <div>
          <h2 className="font-semibold text-gray-900">Career Conversation complete</h2>
          <p className="mt-1.5 max-w-md text-sm text-gray-500">
            {stopReason ?? "We've gathered enough evidence to strengthen this resume for the role."}
          </p>
          <p className="mt-1.5 text-xs text-gray-400">
            {questionsAnswered} question{questionsAnswered === 1 ? '' : 's'} answered.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-6 border-t border-gray-200 bg-gray-50/60 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Wand2 size={22} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Tailored Resume Generator</h3>
            <p className="mt-1 text-sm text-gray-500">
              {hasResult
                ? 'Your tailored resume is ready.'
                : hasPlan
                  ? 'Suggestions are ready for your review.'
                  : 'Use what you just shared to generate evidence-backed edit suggestions for this job.'}
            </p>
          </div>
        </div>

        <Button
          variant="outline"
          icon={<Wand2 size={16} />}
          onClick={() => navigate('/tailored-resume')}
        >
          {hasResult ? 'View Tailored Resume' : hasPlan ? 'Review Suggestions' : 'Generate Tailoring Plan'}
        </Button>
      </div>
    </div>
  )
}
