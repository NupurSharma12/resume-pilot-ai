import { Star } from 'lucide-react'

interface StarRatingProps {
  rating: number
  outOf?: number
}

export default function StarRating({ rating, outOf = 5 }: StarRatingProps) {
  const filled = Math.floor(rating)

  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: outOf }, (_, i) => (
        <Star
          key={i}
          size={18}
          className={i < filled ? 'fill-amber-400 text-amber-400' : 'text-gray-300'}
        />
      ))}
    </div>
  )
}
