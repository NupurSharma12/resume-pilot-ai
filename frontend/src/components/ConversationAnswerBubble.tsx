interface ConversationAnswerBubbleProps {
  answer: string
}

// The candidate's side of the conversation: right-aligned, filled with
// the same indigo-600 used by Button's "solid" variant, so the answer
// bubble reads as "the user's own action" using an already-established
// color rather than introducing a new one.
export default function ConversationAnswerBubble({ answer }: ConversationAnswerBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-white">
        {answer}
      </div>
    </div>
  )
}
