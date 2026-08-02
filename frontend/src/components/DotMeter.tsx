import { THEME_CLASSES, type ColorTheme } from '../data/theme'

interface DotMeterProps {
  score: number
  theme: ColorTheme
  totalDots?: number
}

export default function DotMeter({ score, theme, totalDots = 10 }: DotMeterProps) {
  const filled = Math.round((score / 100) * totalDots)
  const classes = THEME_CLASSES[theme]

  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: totalDots }, (_, i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${i < filled ? classes.dotFilled : classes.dotEmpty}`}
        />
      ))}
    </div>
  )
}
