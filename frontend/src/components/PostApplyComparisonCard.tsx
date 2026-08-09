import { ArrowDown, ArrowRight, ArrowUp, Minus } from 'lucide-react'
import Badge from './Badge'
import type { ResumeAnalysisComparison, ComparisonStatus } from '../data/postApplyTypes'

interface PostApplyComparisonCardProps {
  comparison: ResumeAnalysisComparison
}

const STATUS_COPY: Record<
  ComparisonStatus,
  { headline: (delta: number) => string; detail: string; badge: 'green' | 'amber' | 'rose' }
> = {
  improved: {
    headline: (delta) => `Match score improved by ${delta} point${delta === 1 ? '' : 's'}`,
    detail: 'Re-analysis confirms the applied changes measurably improved the match for this job.',
    badge: 'green',
  },
  // Deliberately not framed as any kind of success -- see this feature's
  // "be honest about the result" requirement (docs/features/postapply-
  // analysis-loop.md): the resume was updated and re-analysis completed,
  // but the overall score did not move.
  unchanged: {
    headline: () => 'Match score did not improve',
    detail:
      'Your resume was updated and re-analysis completed, but the overall score stayed the same. Review the remaining gaps below, or try another round of tailoring.',
    badge: 'amber',
  },
  // Never hidden or softened -- a regression is reported exactly as
  // plainly as an improvement.
  decreased: {
    headline: (delta) => `Match score decreased by ${Math.abs(delta)} point${Math.abs(delta) === 1 ? '' : 's'}`,
    detail:
      'Your resume was updated and re-analysis completed, but the overall score went down. Review the changes below -- further tailoring may be appropriate.',
    badge: 'rose',
  },
}

function StatusIcon({ status }: { status: ComparisonStatus }) {
  if (status === 'improved') return <ArrowUp size={14} />
  if (status === 'decreased') return <ArrowDown size={14} />
  return <Minus size={14} />
}

function CategoryComparisonRow({
  category,
}: {
  category: ResumeAnalysisComparison['category_comparisons'][number]
}) {
  const copy = STATUS_COPY[category.status]
  return (
    <li className="flex items-center justify-between gap-4 py-2.5">
      <span className="text-sm text-gray-500">{category.category}</span>
      <span className="flex items-center gap-3">
        {(category.newly_matched_skills.length > 0 || category.newly_missing_skills.length > 0) && (
          <span className="text-xs text-gray-400">
            {category.newly_matched_skills.length > 0 &&
              `+${category.newly_matched_skills.join(', ')}`}
            {category.newly_matched_skills.length > 0 &&
              category.newly_missing_skills.length > 0 &&
              ' / '}
            {category.newly_missing_skills.length > 0 &&
              `-${category.newly_missing_skills.join(', ')}`}
          </span>
        )}
        <span className="flex items-center gap-1.5 text-sm font-bold text-gray-900">
          {category.score_before}
          <ArrowRight size={12} className="text-gray-300" />
          {category.score_after}
        </span>
        <Badge variant={copy.badge} icon={<StatusIcon status={category.status} />}>
          {category.score_delta > 0 ? `+${category.score_delta}` : category.score_delta}
        </Badge>
      </span>
    </li>
  )
}

function StringListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-400">{title}</h4>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, index) => (
          <li key={index} className="text-sm text-gray-600">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

// The Post-Apply Analysis Loop's result (see
// docs/features/postapply-analysis-loop.md): shows the user whether the
// changes they just applied actually improved their match for this job,
// using the backend's deterministic improved/unchanged/decreased verdict
// verbatim -- this component never re-derives or second-guesses that
// status from the raw scores, and never renders unless a real comparison
// exists (a failed re-analysis is a distinct, separate UI state -- see
// TailoredResumePage -- never routed through here).
export default function PostApplyComparisonCard({ comparison }: PostApplyComparisonCardProps) {
  const copy = STATUS_COPY[comparison.status]

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900">{copy.headline(comparison.score_delta)}</h3>
            <p className="mt-1 max-w-xl text-sm text-gray-500">{copy.detail}</p>
          </div>
          <Badge variant={copy.badge} icon={<StatusIcon status={comparison.status} />}>
            <span className="flex items-center gap-1.5">
              {comparison.score_before}
              <ArrowRight size={12} />
              {comparison.score_after}
            </span>
          </Badge>
        </div>
      </div>

      {comparison.category_comparisons.length > 0 && (
        <div className="rounded-2xl border border-gray-200 bg-white p-6">
          <h3 className="font-semibold text-gray-900">Category breakdown</h3>
          <ul className="mt-2 divide-y divide-gray-100">
            {comparison.category_comparisons.map((category) => (
              <CategoryComparisonRow key={category.category} category={category} />
            ))}
          </ul>
        </div>
      )}

      {(comparison.strengths_gained.length > 0 ||
        comparison.strengths_lost.length > 0 ||
        comparison.weaknesses_resolved.length > 0 ||
        comparison.weaknesses_remaining.length > 0 ||
        comparison.new_weaknesses.length > 0) && (
        <div className="grid gap-6 rounded-2xl border border-gray-200 bg-white p-6 sm:grid-cols-2">
          <StringListSection title="New strengths" items={comparison.strengths_gained} />
          <StringListSection title="Lost strengths" items={comparison.strengths_lost} />
          <StringListSection title="Resolved gaps" items={comparison.weaknesses_resolved} />
          <StringListSection title="Remaining gaps" items={comparison.weaknesses_remaining} />
          <StringListSection title="New gaps" items={comparison.new_weaknesses} />
        </div>
      )}
    </div>
  )
}
