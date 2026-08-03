import { AlertTriangle, CheckCircle2 } from 'lucide-react'

interface WhyThisScoreCardProps {
  topStrengths: string[]
  topRisks: string[]
}

// Mirrors AnalysisPanel's existing "Matched Skills / Missing Skills"
// two-column layout (same grid, same heading treatment, same icon+text
// row pattern) rather than inventing a new visual pattern for what is
// conceptually the same kind of content at the top level.
export default function WhyThisScoreCard({ topStrengths, topRisks }: WhyThisScoreCardProps) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h2 className="text-lg font-bold text-gray-900">Why this Score?</h2>

      <div className="mt-5 grid grid-cols-1 gap-8 sm:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-500">Top Strengths</h3>
          <ul className="mt-3 space-y-2.5">
            {topStrengths.map((item) => (
              <li key={item} className="flex items-center gap-2 text-sm text-gray-700">
                <CheckCircle2 size={16} className="shrink-0 text-emerald-500" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-gray-500">Top Risks</h3>
          <ul className="mt-3 space-y-2.5">
            {topRisks.map((item) => (
              <li key={item} className="flex items-center gap-2 text-sm text-gray-700">
                <AlertTriangle size={16} className="shrink-0 text-amber-500" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
