import { CheckCircle2, XCircle } from 'lucide-react'
import { THEME_CLASSES, type ColorTheme } from '../data/theme'
import type { SkillMatch } from '../data/types'

interface AnalysisPanelProps {
  skillMatch: SkillMatch
  theme: ColorTheme
  aiSummary: string
  recommendation: string
}

export default function AnalysisPanel({
  skillMatch,
  theme,
  aiSummary,
  recommendation,
}: AnalysisPanelProps) {
  const classes = THEME_CLASSES[theme]

  return (
    <div
      key={skillMatch.category}
      className="animate-panel-fade rounded-2xl border border-gray-200 bg-white p-8"
    >
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-xl font-bold text-gray-900">{skillMatch.category}</h2>
        <span className={`text-3xl font-extrabold ${classes.text}`}>{skillMatch.score}</span>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-8 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-500">Matched Skills</h3>
          <ul className="mt-3 space-y-2">
            {skillMatch.matched_skills.length > 0 ? (
              skillMatch.matched_skills.map((skill) => (
                <li key={skill} className="flex items-center gap-2 text-sm text-gray-700">
                  <CheckCircle2 size={15} className="shrink-0 text-emerald-500" />
                  {skill}
                </li>
              ))
            ) : (
              <li className="text-sm text-gray-400">None identified</li>
            )}
          </ul>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-gray-500">Missing Skills</h3>
          <ul className="mt-3 space-y-2">
            {skillMatch.missing_skills.length > 0 ? (
              skillMatch.missing_skills.map((skill) => (
                <li key={skill} className="flex items-center gap-2 text-sm text-gray-700">
                  <XCircle size={15} className="shrink-0 text-rose-500" />
                  {skill}
                </li>
              ))
            ) : (
              <li className="text-sm text-gray-400">None — full coverage</li>
            )}
          </ul>
        </div>
      </div>

      <div className="mt-6">
        <h3 className="text-sm font-semibold text-gray-500">AI Summary</h3>
        <p className="mt-2 leading-relaxed text-gray-600">{aiSummary}</p>
      </div>

      <div className="mt-6 rounded-xl bg-gray-50 p-4">
        <h3 className="text-sm font-semibold text-gray-500">Recommendation</h3>
        <p className="mt-1 text-sm font-medium text-gray-800">{recommendation}</p>
      </div>
    </div>
  )
}
