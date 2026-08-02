import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'outline' | 'solid'

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  outline: 'bg-white text-gray-900 border border-gray-200 hover:bg-gray-50',
  solid: 'bg-indigo-600 text-white border border-indigo-600 hover:bg-indigo-700',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  icon?: ReactNode
}

export default function Button({
  variant = 'outline',
  icon,
  children,
  className = '',
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {icon}
      {children}
    </button>
  )
}
