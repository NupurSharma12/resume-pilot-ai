import Badge from './Badge'
import type { TailoringAction, TailoringPlan } from '../data/tailoringTypes'

const ACTION_LABELS: Record<TailoringAction, string> = {
  rewrite: 'Rewrite',
  expand: 'Expand',
  reorder: 'Reorder',
  trim: 'Trim',
  add_emphasis: 'Add Emphasis',
  remove: 'Remove',
}

interface TailoringPlanCardProps {
  plan: TailoringPlan
}

// Renders the Planner's blueprint (Stage 2) -- what should change, why,
// and which evidence justifies it. Deliberately shows no rewritten text
// here: the plan never contains any, by design (see
// docs/features/tailoring-engine.md) -- only TailoredResumeView (Stage 3's
// validated output) ever shows actual resume prose.
export default function TailoringPlanCard({ plan }: TailoringPlanCardProps) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Tailoring Plan</h3>
      <p className="mt-1 text-sm text-gray-500">What the engine decided to change, and why.</p>

      {plan.changes.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">No changes were proposed.</p>
      ) : (
        <ul className="mt-4 space-y-4">
          {plan.changes.map((change, index) => (
            <li key={index} className="border-t border-gray-100 pt-4 first:border-t-0 first:pt-0">
              <div className="flex items-center gap-2">
                <Badge variant="amber">{ACTION_LABELS[change.action]}</Badge>
                <span className="text-sm font-semibold text-gray-900">{change.section}</span>
              </div>
              <p className="mt-1.5 text-sm text-gray-600">{change.reason}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {change.evidence_ids.map((evidenceId) => (
                  <Badge key={evidenceId} variant="gray">
                    {evidenceId}
                  </Badge>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
