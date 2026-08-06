import { CheckCircle2, Sparkles } from 'lucide-react'
import Button from './Button'

interface TailoringPlanSummaryHeaderProps {
  totalCount: number
  recommendedCount: number
  onApplyRecommended: () => void
  onCustomize: () => void
}

// The very first thing a candidate sees on Stage 2: how many suggestions
// exist and how many are already recommended -- answering "is this worth
// my time?" before a single suggestion card is read. "Apply Recommended"
// only changes *which* suggestions are accepted (the same acceptance
// state every card's own checkbox uses) -- it never skips review or
// calls the apply API itself, so the candidate still sees and can adjust
// the selection below before anything about their resume actually changes.
export default function TailoringPlanSummaryHeader({
  totalCount,
  recommendedCount,
  onApplyRecommended,
  onCustomize,
}: TailoringPlanSummaryHeaderProps) {
  const optionalCount = totalCount - recommendedCount

  return (
    <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-indigo-50/60 to-white p-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
          <Sparkles size={18} className="text-white" />
        </div>
        <h2 className="text-lg font-semibold text-gray-900">Tailoring Suggestions</h2>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <p className="text-sm text-gray-600">
          {totalCount} suggestion{totalCount === 1 ? '' : 's'} found
        </p>
        <p className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600">
          <CheckCircle2 size={16} />
          {recommendedCount} recommended
        </p>
        <p className="text-sm text-gray-500">
          {optionalCount} optional
        </p>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <Button variant="solid" onClick={onApplyRecommended} disabled={recommendedCount === 0}>
          Apply Recommended
        </Button>
        <Button variant="outline" onClick={onCustomize}>
          Customize Selection
        </Button>
      </div>
    </div>
  )
}
