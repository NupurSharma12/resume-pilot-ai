import { MessageCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'

// Styled identically to TailoredResumeBanner (same card/icon-tile/copy
// layout) since both are "what's next after analysis" prompts shown in
// the same position — but this one is a real, enabled action, not a
// disabled "coming soon" placeholder.
export default function CareerConversationBanner() {
  const navigate = useNavigate()

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="flex items-center justify-between gap-6 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <MessageCircle size={22} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">Recover Missing Evidence</h3>
            <p className="mt-1 text-sm text-gray-500">
              Have a short conversation with our AI recruiter to surface experience your
              resume doesn't fully capture, before this gets tailored for the role.
            </p>
          </div>
        </div>

        <Button
          variant="solid"
          icon={<MessageCircle size={16} />}
          onClick={() => navigate('/career-conversation')}
        >
          Start Career Conversation
        </Button>
      </div>
    </div>
  )
}
