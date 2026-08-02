// Tailwind's JIT compiler only picks up class names that appear as literal
// strings in source. Colors are looked up from this table (not built with
// template strings like `bg-${color}-500`) so every class Tailwind needs to
// generate is statically visible here.

export type ColorTheme = 'blue' | 'violet' | 'emerald' | 'amber' | 'rose' | 'cyan'

export interface ThemeClasses {
  dot: string
  text: string
  iconBg: string
  iconText: string
  dotFilled: string
  dotEmpty: string
}

export const THEME_CLASSES: Record<ColorTheme, ThemeClasses> = {
  blue: {
    dot: 'bg-blue-500',
    text: 'text-blue-600',
    iconBg: 'bg-blue-50',
    iconText: 'text-blue-600',
    dotFilled: 'bg-blue-500',
    dotEmpty: 'bg-blue-100',
  },
  violet: {
    dot: 'bg-violet-500',
    text: 'text-violet-600',
    iconBg: 'bg-violet-50',
    iconText: 'text-violet-600',
    dotFilled: 'bg-violet-500',
    dotEmpty: 'bg-violet-100',
  },
  emerald: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-600',
    iconBg: 'bg-emerald-50',
    iconText: 'text-emerald-600',
    dotFilled: 'bg-emerald-500',
    dotEmpty: 'bg-emerald-100',
  },
  amber: {
    dot: 'bg-amber-500',
    text: 'text-amber-600',
    iconBg: 'bg-amber-50',
    iconText: 'text-amber-600',
    dotFilled: 'bg-amber-500',
    dotEmpty: 'bg-amber-100',
  },
  rose: {
    dot: 'bg-rose-500',
    text: 'text-rose-600',
    iconBg: 'bg-rose-50',
    iconText: 'text-rose-600',
    dotFilled: 'bg-rose-500',
    dotEmpty: 'bg-rose-100',
  },
  cyan: {
    dot: 'bg-cyan-500',
    text: 'text-cyan-600',
    iconBg: 'bg-cyan-50',
    iconText: 'text-cyan-600',
    dotFilled: 'bg-cyan-500',
    dotEmpty: 'bg-cyan-100',
  },
}

// The backend has no concept of a display color for a skill category — it
// just returns however many `skill_matches` entries it has. Assigning a
// theme by position (cycling through this list) means the UI never needs
// to know category names or assume a fixed count of five.
const THEME_CYCLE: ColorTheme[] = ['blue', 'violet', 'emerald', 'amber', 'cyan', 'rose']

export function getThemeForIndex(index: number): ColorTheme {
  return THEME_CYCLE[index % THEME_CYCLE.length]
}
