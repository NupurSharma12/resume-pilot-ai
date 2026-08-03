import { CheckCircle2, Wand2 } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'

interface ConversationCompleteCardProps {
  stopReason: string | null
  questionsAnswered: number
}

// The completion state's "what's next" half deliberately mirrors
// TailoredResumeBanner's exact layout (icon tile, COMING SOON badge,
// disabled outline button) — Tailored Resume is still the same disabled
// placeholder everywhere it appears, this just also appears here as the
// natural next step after a completed conversation.
export default function ConversationCompleteCard({
  stopReason,
  questionsAnswered,
}: ConversationCompleteCardProps) {
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
            <div className="flex items-center gap-2.5">
              <h3 className="font-semibold text-gray-900">Tailored Resume Generator</h3>
              <Badge variant="amber">COMING SOON</Badge>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Use what you just shared to generate an AI-optimized resume for this job.
            </p>
          </div>
        </div>

        <Button variant="outline" icon={<Wand2 size={16} />} disabled>
          Generate Tailored Resume
        </Button>
      </div>
    </div>
  )
}
