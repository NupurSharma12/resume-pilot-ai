import type { ReactNode } from 'react'

type BadgeVariant = 'gray' | 'green' | 'amber'

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  gray: 'bg-gray-100 text-gray-500',
  green: 'bg-green-50 text-green-700',
  amber: 'bg-amber-100 text-amber-700',
}

interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  icon?: ReactNode
}

export default function Badge({ children, variant = 'gray', icon }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${VARIANT_CLASSES[variant]}`}
    >
      {icon}
      {children}
    </span>
  )
}
