import Badge from './Badge'
import type { ValidationReport } from '../data/tailoringTypes'

interface ValidationReportCardProps {
  report: ValidationReport
}

// Every bullet the Rewrite Engine proposed is accounted for here, one way
// or the other -- accepted (shown in TailoredResumeView) or rejected with
// a specific reason (shown below). Nothing is ever silently dropped; this
// card is what makes that guarantee visible to the candidate, not just
// enforced server-side.
export default function ValidationReportCard({ report }: ValidationReportCardProps) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="font-semibold text-gray-900">Validation Report</h3>
          <p className="mt-1 text-sm text-gray-500">
            Every rewritten bullet is checked against the evidence it cited before it's kept.
          </p>
        </div>
        <Badge variant={report.passed ? 'green' : 'amber'}>
          {report.accepted_count}/{report.total_bullets} accepted
        </Badge>
      </div>

      {report.rejected_bullets.length > 0 && (
        <ul className="mt-4 space-y-3">
          {report.rejected_bullets.map((rejected, index) => (
            <li key={index} className="rounded-xl border border-rose-100 bg-rose-50/60 p-4">
              <p className="text-xs font-semibold text-rose-600">{rejected.section}</p>
              <p className="mt-1 text-sm text-gray-500 line-through decoration-rose-300">
                {rejected.text}
              </p>
              <p className="mt-1.5 text-xs text-gray-600">{rejected.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
