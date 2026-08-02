import { THEME_CLASSES, type ColorTheme } from '../data/theme'
import type { SkillMatch } from '../data/types'

interface CategoryScoreRowProps {
  skillMatch: SkillMatch
  theme: ColorTheme
}

export default function CategoryScoreRow({ skillMatch, theme }: CategoryScoreRowProps) {
  const classes = THEME_CLASSES[theme]

  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-sm text-gray-500">{skillMatch.category}</span>
      <span className="flex items-center gap-2.5">
        <span className={`h-2 w-2 rounded-full ${classes.dot}`} />
        <span className="text-sm font-bold text-gray-900">{skillMatch.score}</span>
      </span>
    </div>
  )
}
