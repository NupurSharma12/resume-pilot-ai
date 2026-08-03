interface ExecutiveSummaryProps {
  bullets: string[]
}

// Replaces the hero card's single summary paragraph with a short bulleted
// recruiter-style take — same position/spacing as the paragraph it
// replaces (see CandidateHeroCard). Dot markers, not native list bullets,
// to match the app's existing "small dot as marker" visual language
// (DotMeter, CategoryScoreRow) rather than introducing a new style.
export default function ExecutiveSummary({ bullets }: ExecutiveSummaryProps) {
  return (
    <ul className="mt-4 space-y-2">
      {bullets.map((bullet) => (
        <li key={bullet} className="flex items-start gap-2 text-sm leading-relaxed text-gray-600">
          <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
          {bullet}
        </li>
      ))}
    </ul>
  )
}
