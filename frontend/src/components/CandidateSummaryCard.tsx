import { Building2, CalendarDays } from 'lucide-react'
import { getMatchLabel } from '../lib/scoreDescriptor'
import type { Candidate } from '../data/types'

interface CandidateSummaryCardProps {
  candidate: Candidate
  overallScore: number
}

export default function CandidateSummaryCard({
  candidate,
  overallScore,
}: CandidateSummaryCardProps) {
  const matchLabel = getMatchLabel(overallScore)

  return (
    <div className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
      <p className="mb-3 text-[11px] font-semibold tracking-wider text-gray-400">
        CURRENT CANDIDATE
      </p>

      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-bold text-white">
          {candidate.initials}
        </div>
        <div className="min-w-0">
          <p className="truncate font-semibold text-gray-900">{candidate.name}</p>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <Building2 size={12} />
              {candidate.company}
            </span>
            <span aria-hidden>·</span>
            <span className="flex items-center gap-1">
              <CalendarDays size={12} />
              {candidate.yearsExperience} yrs
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-gray-500">Overall Match</span>
        <span className="font-bold text-indigo-600">{overallScore}%</span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-violet-500"
          style={{ width: `${overallScore}%` }}
        />
      </div>

      <div className="mt-3 flex items-center gap-1.5 text-xs font-medium text-emerald-600">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        {matchLabel}
      </div>
    </div>
  )
}
