import { CheckCircle2, Wand2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'

interface ConversationCompleteCardProps {
  stopReason: string | null
  questionsAnswered: number
}

// The completion state's "what's next" half is the one real, enabled
// entry point into the Tailoring Engine (TailoredResumeBanner on the
// Dashboard is still a disabled "coming soon" placeholder — the backend
// requires a Career Conversation session to tailor against, so this is
// the point in the flow where that's actually satisfied).
export default function ConversationCompleteCard({
  stopReason,
  questionsAnswered,
}: ConversationCompleteCardProps) {
  const navigate = useNavigate()

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
              Use what you just shared to generate an evidence-backed resume for this job.
            </p>
          </div>
        </div>

        <Button
          variant="outline"
          icon={<Wand2 size={16} />}
          onClick={() => navigate('/tailored-resume')}
        >
          Generate Tailored Resume
        </Button>
      </div>
    </div>
  )
}
