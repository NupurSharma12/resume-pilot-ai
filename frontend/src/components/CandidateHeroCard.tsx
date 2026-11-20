import { Building2, CheckCircle2 } from 'lucide-react'
import CircularProgress from './CircularProgress'
import CategoryScoreRow from './CategoryScoreRow'
import ExecutiveSummary from './ExecutiveSummary'
import { getThemeForIndex } from '../data/theme'
import type { Candidate, OverallAssessment, SkillMatch } from '../data/types'

interface CandidateHeroCardProps {
  // Null when the analysis carries no extracted identity -- every analysis
  // created before `candidate_profile` existed. The identity block is
  // replaced by a short explanatory line in that case; the score and skill
  // breakdown either side of it are unaffected, since they never depended
  // on identity.
  candidate: Candidate | null
  overallAssessment: OverallAssessment
  skillMatches: SkillMatch[]
  executiveSummary: string[]
}

export default function CandidateHeroCard({
  candidate,
  overallAssessment,
  skillMatches,
  executiveSummary,
}: CandidateHeroCardProps) {
  return (
    <div className="grid grid-cols-[280px_1fr_260px] overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="flex flex-col items-center justify-center gap-5 bg-indigo-50/60 p-8">
        <CircularProgress percentage={overallAssessment.overall_score}>
          <span className="text-4xl font-extrabold text-gray-900">
            {overallAssessment.overall_score}%
          </span>
          <span className="mt-1 text-xs font-semibold tracking-wider text-gray-400">
            MATCH SCORE
          </span>
        </CircularProgress>

        <span className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-4 py-2 text-sm font-semibold text-green-700">
          <CheckCircle2 size={16} />
          {overallAssessment.hiring_recommendation.decision}
        </span>
      </div>

      <div className="border-l border-gray-200 p-8">
        {candidate ? (
          <>
            {candidate.title && (
              <p className="text-sm text-gray-500">{candidate.title}</p>
            )}

            <h2 className="mt-1.5 text-2xl font-bold text-gray-900">{candidate.name}</h2>

            {/* Rendered only when there's something real to show: a lone
                "·" separator or a bare "Years Experience" with no number
                reads as a rendering bug, so the details line is assembled
                from whichever parts were actually extracted. */}
            {(candidate.company || candidate.yearsExperience !== null) && (
              <p className="mt-1.5 flex items-center gap-1.5 text-sm text-gray-500">
                <Building2 size={14} />
                {[
                  candidate.company,
                  candidate.yearsExperience !== null
                    ? `${candidate.yearsExperience} Years Experience`
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-gray-400">
            Candidate details are not available for this analysis.
          </p>
        )}

        <ExecutiveSummary bullets={executiveSummary} />
      </div>

      <div className="border-l border-gray-200 p-8">
        <div className="divide-y divide-gray-100">
          {skillMatches.map((skillMatch, index) => (
            <CategoryScoreRow
              key={skillMatch.category}
              skillMatch={skillMatch}
              theme={getThemeForIndex(index)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
