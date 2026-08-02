import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'
import SkeletonBlock from './SkeletonBlock'
import IndeterminateBar from './IndeterminateBar'

const STATUS_MESSAGES = [
  'Reading resume details…',
  'Comparing experience against job requirements…',
  'Evaluating technical and leadership signals…',
  'Assessing domain expertise and communication…',
  'Compiling hiring recommendation…',
]

const MESSAGE_INTERVAL_MS = 1800

// Fills the same layout footprint as the real dashboard content it will be
// replaced by (hero card + five metric cards), using skeleton shapes in the
// same positions, so the transition to real data doesn't jump the page
// around — only content fades in where gray placeholders already were.
export default function AnalyzingState() {
  const [messageIndex, setMessageIndex] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setMessageIndex((current) => (current + 1) % STATUS_MESSAGES.length)
    }, MESSAGE_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="animate-panel-fade space-y-8">
      <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
        <IndeterminateBar />

        <div className="grid grid-cols-[280px_1fr_260px]">
          <div className="flex flex-col items-center justify-center gap-5 bg-indigo-50/60 p-8">
            <div className="flex h-32 w-32 items-center justify-center rounded-full bg-white/70">
              <span className="flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
                <Sparkles size={28} className="text-white" />
              </span>
            </div>
            <p
              aria-live="polite"
              className="min-h-[2.5rem] max-w-[200px] text-center text-sm font-medium text-gray-500"
            >
              {STATUS_MESSAGES[messageIndex]}
            </p>
          </div>

          <div className="border-l border-gray-200 p-8">
            <SkeletonBlock className="h-4 w-40" />
            <SkeletonBlock className="mt-4 h-7 w-56" />
            <SkeletonBlock className="mt-3 h-4 w-64" />
            <div className="mt-4 space-y-2">
              <SkeletonBlock className="h-3.5 w-full" />
              <SkeletonBlock className="h-3.5 w-full" />
              <SkeletonBlock className="h-3.5 w-2/3" />
            </div>
          </div>

          <div className="border-l border-gray-200 p-8">
            <div className="space-y-4">
              {Array.from({ length: 5 }, (_, i) => (
                <div key={i} className="flex items-center justify-between">
                  <SkeletonBlock className="h-3.5 w-20" />
                  <SkeletonBlock className="h-3.5 w-8" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="rounded-2xl border border-gray-200 bg-white p-5">
            <div className="flex items-start justify-between gap-2">
              <SkeletonBlock className="h-4 w-24" />
              <SkeletonBlock className="h-6 w-8" />
            </div>
            <SkeletonBlock className="mt-4 h-1.5 w-full" />
            <div className="mt-3 flex items-center justify-between">
              <SkeletonBlock className="h-3.5 w-16" />
              <SkeletonBlock className="h-3.5 w-10" />
            </div>
            <SkeletonBlock className="mt-3 h-3 w-full" />
          </div>
        ))}
      </div>
    </div>
  )
}
