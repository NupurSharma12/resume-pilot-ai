import { Sparkles } from 'lucide-react'

interface ConversationAssistantReplyBubbleProps {
  text: string
}

// A separate message from ConversationQuestionBubble, though from the
// same speaker (same avatar) — the recruiter's own reply to the
// candidate's previous answer (answering a clarifying question they
// asked back, or acknowledging a correction), shown immediately before
// the next question it leads into. Visually distinguished from the
// question bubble (tinted background, no topic/impact badges) since it
// isn't itself a new topic, just a reply.
export default function ConversationAssistantReplyBubble({
  text,
}: ConversationAssistantReplyBubbleProps) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
        <Sparkles size={16} className="text-white" />
      </div>
      <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-indigo-50/70 px-4 py-3 text-sm leading-relaxed text-gray-700">
        {text}
      </div>
    </div>
  )
}
