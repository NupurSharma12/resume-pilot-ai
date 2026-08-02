import { useState } from 'react'
import TopHeader from '../components/TopHeader'
import CandidateHeroCard from '../components/CandidateHeroCard'
import MetricCard from '../components/MetricCard'
import AnalysisPanel from '../components/AnalysisPanel'
import TailoredResumeBanner from '../components/TailoredResumeBanner'
import { getThemeForIndex } from '../data/theme'
import {
  candidate,
  mockResumeAnalysis,
  skillMatchNarratives,
  defaultSkillMatchNarrative,
} from '../data/mockData'

export default function DashboardPage() {
  const { overall_assessment, skill_matches } = mockResumeAnalysis

  // No assumption of exactly five (or any fixed number of) categories:
  // whatever `skill_matches` contains is what gets rendered and selected.
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(
    skill_matches[0]?.category,
  )

  const selectedIndex = skill_matches.findIndex((s) => s.category === selectedCategory)
  const selectedSkillMatch = selectedIndex >= 0 ? skill_matches[selectedIndex] : undefined
  const selectedNarrative = selectedSkillMatch
    ? (skillMatchNarratives[selectedSkillMatch.category] ?? defaultSkillMatchNarrative)
    : undefined

  return (
    <>
      <TopHeader
        title="Resume Analysis Dashboard"
        subtitle="AI-powered recruiter insights and hiring recommendations"
      />

      <div className="space-y-8 p-8">
        <CandidateHeroCard
          candidate={candidate}
          overallAssessment={overall_assessment}
          skillMatches={skill_matches}
        />

        <div className="grid grid-cols-5 gap-5">
          {skill_matches.map((skillMatch, index) => (
            <MetricCard
              key={skillMatch.category}
              skillMatch={skillMatch}
              theme={getThemeForIndex(index)}
              recruiterSummary={
                (skillMatchNarratives[skillMatch.category] ?? defaultSkillMatchNarrative)
                  .recruiterSummary
              }
              isSelected={selectedCategory === skillMatch.category}
              onSelect={setSelectedCategory}
            />
          ))}
        </div>

        {selectedSkillMatch && selectedNarrative && (
          <AnalysisPanel
            skillMatch={selectedSkillMatch}
            theme={getThemeForIndex(selectedIndex)}
            aiSummary={selectedNarrative.aiSummary}
            recommendation={selectedNarrative.recommendation}
          />
        )}

        <TailoredResumeBanner />
      </div>
    </>
  )
}
