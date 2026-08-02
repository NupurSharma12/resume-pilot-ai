interface SkeletonBlockProps {
  className?: string
}

// A single pulsing placeholder rectangle. Composed into shapes that mirror
// the real hero card / metric cards (see AnalyzingState), so the loading
// state occupies the same layout the real content will — no layout jump
// when real data arrives, and the page reads as "working," not "empty."
export default function SkeletonBlock({ className = '' }: SkeletonBlockProps) {
  return <div className={`animate-pulse rounded-md bg-gray-200 ${className}`} />
}
