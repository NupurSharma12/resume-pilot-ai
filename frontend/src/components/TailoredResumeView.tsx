import Badge from './Badge'
import type { TailoredResume } from '../data/tailoringTypes'

interface TailoredResumeViewProps {
  tailoredResume: TailoredResume
}

// Renders Stage 4's output only -- every bullet shown here already
// survived Validation (see ValidationReportCard for what didn't). An
// empty `sections` array is a legitimate, non-error outcome (every
// proposed bullet failed validation), not something to treat as
// "still loading" or "broken" -- see docs/features/tailoring-engine.md.
export default function TailoredResumeView({ tailoredResume }: TailoredResumeViewProps) {
  if (tailoredResume.sections.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-gray-300 bg-white px-8 py-12 text-center">
        <p className="text-sm text-gray-500">
          No proposed changes passed validation, so there's nothing new to show here — see the
          validation report below for why.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {tailoredResume.sections.map((section) => (
        <div key={section.heading} className="rounded-2xl border border-gray-200 bg-white p-6">
          <h3 className="font-semibold text-gray-900">{section.heading}</h3>
          <ul className="mt-3 space-y-4">
            {section.bullets.map((bullet, index) => (
              <li key={index} className="text-sm text-gray-700">
                <p>{bullet.text}</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {bullet.supporting_evidence_ids.map((evidenceId) => (
                    <Badge key={evidenceId} variant="green">
                      {evidenceId}
                    </Badge>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
