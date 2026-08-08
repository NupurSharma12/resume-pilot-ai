import Badge from './Badge'
import Button from './Button'
import type { FinalValidationReport, TailoringSuggestion } from '../data/tailoringSuggestionsTypes'
import { getReadableSectionName } from '../lib/suggestionPresentation'

interface TailoringFinalResumeCardProps {
  finalResumeText: string
  appliedSuggestionIds: string[]
  allSuggestions: TailoringSuggestion[]
  validationReport: FinalValidationReport
  // Same precomputed maps TailoredResumePage builds once for the whole
  // suggestion list (see suggestionPresentation.ts) -- passed in rather
  // than recomputed here, and never the raw `target_section_id`.
  sectionNames: Map<string, string>
  sectionFallbackOrdinals: Map<string, number>
  // Scrolls back up to the review list -- this card is never a dead end:
  // applying is phased, so a candidate is always expected to be able to
  // keep selecting/previewing/applying more suggestions afterward (see
  // this feature's "Preview-first workflow" docs).
  onContinueEditing: () => void
}

// Stage 4/5's result card: the assembled final resume (plain-text
// preview -- an ATS-friendly rendering, not a facsimile of any original
// file's layout, see this feature's docs on why), which suggestions
// actually produced it, which proposed suggestions were left out, and
// the structural validation report run over the assembled result. Every
// suggestion in `allSuggestions` is accounted for here one way or the
// other, the same "nothing silently dropped" guarantee the superseded
// ValidationReportCard made for whole-section rewrites.
export default function TailoringFinalResumeCard({
  finalResumeText,
  appliedSuggestionIds,
  allSuggestions,
  validationReport,
  sectionNames,
  sectionFallbackOrdinals,
  onContinueEditing,
}: TailoringFinalResumeCardProps) {
  const appliedIds = new Set(appliedSuggestionIds)
  const applied = allSuggestions.filter((s) => appliedIds.has(s.suggestion_id))
  const notIncluded = allSuggestions.filter((s) => !appliedIds.has(s.suggestion_id))

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-gray-900">Final Resume Preview</h3>
            <p className="mt-1 text-sm text-gray-500">
              An ATS-friendly preview of your resume with only the changes you approved.
            </p>
          </div>
          <Button variant="outline" onClick={onContinueEditing}>
            Continue Editing
          </Button>
        </div>
        <pre className="mt-4 max-h-[32rem] overflow-y-auto whitespace-pre-wrap rounded-xl border border-gray-100 bg-gray-50 p-4 font-sans text-sm text-gray-800">
          {finalResumeText}
        </pre>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <h3 className="font-semibold text-gray-900">Final Validation</h3>
          <Badge variant={validationReport.is_valid ? 'green' : 'amber'}>
            {validationReport.is_valid ? 'No issues found' : `${validationReport.messages.length} issue(s)`}
          </Badge>
        </div>
        {validationReport.messages.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {validationReport.messages.map((message, index) => (
              <li key={index} className="text-sm text-amber-700">
                {message}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <h3 className="font-semibold text-gray-900">Applied changes ({applied.length})</h3>
        {applied.length === 0 ? (
          <p className="mt-2 text-sm text-gray-500">No suggestions were selected.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {applied.map((suggestion) => (
              <li key={suggestion.suggestion_id} className="text-sm text-gray-600">
                <span className="font-medium text-gray-900">
                  {getReadableSectionName(suggestion, sectionNames, sectionFallbackOrdinals)}:
                </span>{' '}
                {suggestion.reason}
              </li>
            ))}
          </ul>
        )}

        {notIncluded.length > 0 && (
          <>
            <h4 className="mt-5 text-sm font-semibold text-gray-500">
              Not included ({notIncluded.length})
            </h4>
            <ul className="mt-2 space-y-2">
              {notIncluded.map((suggestion) => (
                <li key={suggestion.suggestion_id} className="text-sm text-gray-400">
                  <span className="font-medium text-gray-500">
                    {getReadableSectionName(suggestion, sectionNames, sectionFallbackOrdinals)}:
                  </span>{' '}
                  {suggestion.reason}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
