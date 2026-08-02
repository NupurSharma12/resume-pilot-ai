import DotMeter from './DotMeter'
import { THEME_CLASSES, type ColorTheme } from '../data/theme'
import { getScoreDescriptor } from '../lib/scoreDescriptor'
import type { SkillMatch } from '../data/types'

interface MetricCardProps {
  skillMatch: SkillMatch
  theme: ColorTheme
  recruiterSummary: string
  isSelected?: boolean
  onSelect?: (category: string) => void
}

export default function MetricCard({
  skillMatch,
  theme,
  recruiterSummary,
  isSelected = false,
  onSelect,
}: MetricCardProps) {
  const classes = THEME_CLASSES[theme]
  const descriptor = getScoreDescriptor(skillMatch.score)

  return (
    <button
      type="button"
      onClick={() => onSelect?.(skillMatch.category)}
      aria-pressed={isSelected}
      className={`w-full rounded-2xl border bg-white p-5 text-left shadow-sm transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 ${
        isSelected
          ? 'scale-[1.02] border-blue-500 shadow-md ring-1 ring-blue-100'
          : 'border-gray-200'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-semibold text-gray-900">{skillMatch.category}</span>
        <span className={`text-2xl font-extrabold ${classes.text}`}>{skillMatch.score}</span>
      </div>

      <div className="mt-4">
        <DotMeter score={skillMatch.score} theme={theme} />
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="text-gray-400">{descriptor}</span>
        <span className={`font-semibold ${classes.text}`}>{skillMatch.score}/100</span>
      </div>

      <p className="mt-3 line-clamp-1 text-xs text-gray-500">{recruiterSummary}</p>
    </button>
  )
}
