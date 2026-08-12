import type { InterviewPreparation } from '../data/jobPreparationHistoryTypes'
import { interviewPreparationStageLabel } from '../lib/interviewPreparationStage'

const DIFFICULTY_STYLES: Record<string, string> = {
  easy: 'bg-emerald-50 text-emerald-600',
  medium: 'bg-amber-50 text-amber-600',
  hard: 'bg-rose-50 text-rose-600',
}

// Shared by HistoryPage (inspecting a past preparation) and
// InterviewPreparationPage (the active preparation) -- one rendering of
// one persisted `InterviewPreparation`, so the two pages can never render
// this guide differently. `title` lets each caller keep its own heading
// context (HistoryPage nests this under its own "Job Preparation
// Details" heading hierarchy; InterviewPreparationPage's TopHeader
// already says "Interview Preparation").
export default function InterviewPreparationCard({
  interviewPreparation,
  title = 'Interview Preparation',
}: {
  interviewPreparation: InterviewPreparation
  title?: string
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold text-gray-900">{title}</h3>
        <span className="shrink-0 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-600">
          {interviewPreparationStageLabel(interviewPreparation.stage)}
        </span>
      </div>

      <h4 className="mt-4 text-sm font-semibold text-gray-700">System Design</h4>
      <ul className="mt-2 space-y-3">
        {interviewPreparation.system_design_questions.map((question, index) => (
          <li key={index} className="text-sm">
            <p className="text-gray-800">{question.question}</p>
            <p className="mt-0.5 text-xs text-gray-500">{question.rationale}</p>
          </li>
        ))}
      </ul>

      <h4 className="mt-6 text-sm font-semibold text-gray-700">Coding / LeetCode</h4>
      <ul className="mt-2 space-y-3">
        {interviewPreparation.coding_questions.map((question, index) => (
          <li key={index} className="text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-gray-800">{question.title}</span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                {question.topic}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${DIFFICULTY_STYLES[question.difficulty] ?? 'bg-gray-100 text-gray-500'}`}
              >
                {question.difficulty}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-gray-500">{question.relevance}</p>
          </li>
        ))}
      </ul>

      <h4 className="mt-6 text-sm font-semibold text-gray-700">Behavioral</h4>
      <ul className="mt-2 space-y-3">
        {interviewPreparation.behavioral_questions.map((question, index) => (
          <li key={index} className="text-sm">
            <div className="flex items-center gap-2">
              <p className="text-gray-800">{question.question}</p>
              {question.source === 'career_conversation' && (
                <span className="shrink-0 rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">
                  From Career Conversation
                </span>
              )}
            </div>
            {question.context && <p className="mt-0.5 text-xs text-gray-500">{question.context}</p>}
          </li>
        ))}
      </ul>
    </div>
  )
}
