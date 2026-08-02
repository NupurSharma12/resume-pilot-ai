import { Building2, CheckCircle2 } from 'lucide-react'
import CircularProgress from './CircularProgress'
import StarRating from './StarRating'
import CategoryScoreRow from './CategoryScoreRow'
import { getThemeForIndex } from '../data/theme'
import type { Candidate, OverallAssessment, SkillMatch } from '../data/types'

interface CandidateHeroCardProps {
  candidate: Candidate
  overallAssessment: OverallAssessment
  skillMatches: SkillMatch[]
}

export default function CandidateHeroCard({
  candidate,
  overallAssessment,
  skillMatches,
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
        <div className="flex items-center gap-3">
          <StarRating rating={candidate.rating} />
          <span className="text-sm font-medium text-gray-400">
            {candidate.rating}/5
          </span>
          <span className="text-sm text-gray-400">|</span>
          <span className="text-sm text-gray-500">{candidate.title}</span>
        </div>

        <h2 className="mt-3 text-2xl font-bold text-gray-900">{candidate.name}</h2>

        <p className="mt-1.5 flex items-center gap-1.5 text-sm text-gray-500">
          <Building2 size={14} />
          {candidate.company} · {candidate.yearsExperience} Years Experience
        </p>

        <p className="mt-4 leading-relaxed text-gray-600">{overallAssessment.summary}</p>
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
