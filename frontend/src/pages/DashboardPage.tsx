import { useEffect, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import InputSection from '../components/InputSection'
import CandidateHeroCard from '../components/CandidateHeroCard'
import WhyThisScoreCard from '../components/WhyThisScoreCard'
import MetricCard from '../components/MetricCard'
import AnalysisPanel from '../components/AnalysisPanel'
import AnalyzingState from '../components/AnalyzingState'
import AnalysisErrorState from '../components/AnalysisErrorState'
import CareerConversationBanner from '../components/CareerConversationBanner'
import TailoredResumeBanner from '../components/TailoredResumeBanner'
import { getThemeForIndex } from '../data/theme'
import { candidate, skillMatchNarratives, defaultSkillMatchNarrative } from '../data/mockData'
import { buildExecutiveSummary, deriveTopStrengths, deriveTopRisks } from '../lib/insights'
import { analyzeResume, ApiError } from '../lib/api'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

export default function DashboardPage() {
  // Everything here (including status/errorMessage/isInputCollapsed) lives
  // one level up, in DashboardLayout, and is shared via Outlet context —
  // not local state — because this page unmounts whenever the user
  // navigates to /resume, /job-description, /history, or /settings, and
  // needs to show the same result when they come back (see
  // DashboardLayout's docstring).
  const {
    resumeAnalysis,
    setResumeAnalysis,
    resume,
    onResumeChange,
    jobDescription,
    onJobDescriptionChange,
    status,
    setStatus,
    errorMessage,
    setErrorMessage,
    isInputCollapsed,
    setIsInputCollapsed,
  } = useOutletContext<DashboardOutletContext>()

  // Selection is intentionally local (purely cosmetic — which metric card
  // is highlighted) and falls back to the first category below when unset,
  // so navigating back to an already-analyzed dashboard still shows a
  // sensible default panel instead of nothing.
  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(undefined)

  const resultsRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Tracks the previous status (not "is this the first render") so that
  // simply navigating back to an already-successful dashboard doesn't
  // re-trigger the scroll — only an actual ->'success' transition does.
  // A first-render boolean would work for a normal render but silently
  // re-arms on StrictMode's dev-only double effect invocation (the second
  // simulated pass would see "not first render" and scroll anyway even
  // though status never changed); comparing against the last status seen
  // stays correct either way, since both passes see the same status.
  const prevStatusRef = useRef(status)
  useEffect(() => {
    const prevStatus = prevStatusRef.current
    prevStatusRef.current = status
    if (status === 'success' && prevStatus !== 'success') {
      resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [status])

  function handleSelectCategory(category: string) {
    setSelectedCategory(category)
    // `block: 'nearest'` is a no-op if the panel is already fully in
    // view, so this only scrolls "if necessary."
    panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  // Safe defaults for when there's no analysis yet — never read while
  // `resumeAnalysis` is null because rendering below is gated on
  // `hasResult`, but keeping these typed without non-null assertions.
  const skillMatches = resumeAnalysis?.skill_matches ?? []
  const effectiveCategory = selectedCategory ?? skillMatches[0]?.category
  const selectedIndex = skillMatches.findIndex((s) => s.category === effectiveCategory)
  const selectedSkillMatch = selectedIndex >= 0 ? skillMatches[selectedIndex] : undefined
  const selectedNarrative = selectedSkillMatch
    ? (skillMatchNarratives[selectedSkillMatch.category] ?? defaultSkillMatchNarrative)
    : undefined

  // Derived, read-only insights — pure functions of `resumeAnalysis`, no
  // extra state. Recomputed each render; cheap given the small arrays involved.
  const executiveSummary = resumeAnalysis ? buildExecutiveSummary(resumeAnalysis) : []
  const topStrengths = resumeAnalysis ? deriveTopStrengths(resumeAnalysis) : []
  const topRisks = resumeAnalysis ? deriveTopRisks(resumeAnalysis) : []

  const canAnalyze = Boolean(resume) && Boolean(jobDescription)
  const hasResult = status === 'success' && resumeAnalysis !== null

  async function handleAnalyze() {
    if (!resume || !jobDescription) return

    setStatus('loading')
    try {
      const result = await analyzeResume(resume.text, jobDescription.text)
      setResumeAnalysis(result)
      setSelectedCategory(result.skill_matches[0]?.category)
      setStatus('success')
      // Only collapses on success (not immediately on click), per spec —
      // an error or an in-flight request leaves the inputs as the user left them.
      setIsInputCollapsed(true)
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? err.message : 'An unexpected error occurred. Please try again.',
      )
      setStatus('error')
    }
  }

  return (
    <>
      <TopHeader
        title="Resume Analysis Dashboard"
        subtitle="AI-powered recruiter insights and hiring recommendations"
      />

      <div className="space-y-8 p-8">
        <InputSection
          resume={resume}
          jobDescription={jobDescription}
          onResumeChange={onResumeChange}
          onJobDescriptionChange={onJobDescriptionChange}
          isCollapsed={isInputCollapsed}
          onExpand={() => setIsInputCollapsed(false)}
          onAnalyze={handleAnalyze}
          canAnalyze={canAnalyze}
          isAnalyzing={status === 'loading'}
        />

        {status === 'loading' && <AnalyzingState />}

        {status === 'error' && (
          <AnalysisErrorState message={errorMessage} onRetry={handleAnalyze} />
        )}

        {hasResult && resumeAnalysis && (
          <div ref={resultsRef} className="animate-panel-fade space-y-8">
            <CandidateHeroCard
              candidate={candidate}
              overallAssessment={resumeAnalysis.overall_assessment}
              skillMatches={resumeAnalysis.skill_matches}
              executiveSummary={executiveSummary}
            />

            <WhyThisScoreCard topStrengths={topStrengths} topRisks={topRisks} />

            <div className="grid grid-cols-5 gap-5">
              {resumeAnalysis.skill_matches.map((skillMatch, index) => (
                <MetricCard
                  key={skillMatch.category}
                  skillMatch={skillMatch}
                  theme={getThemeForIndex(index)}
                  recruiterSummary={
                    (skillMatchNarratives[skillMatch.category] ?? defaultSkillMatchNarrative)
                      .recruiterSummary
                  }
                  isSelected={effectiveCategory === skillMatch.category}
                  onSelect={handleSelectCategory}
                />
              ))}
            </div>

            {selectedSkillMatch && selectedNarrative && (
              <div ref={panelRef}>
                <AnalysisPanel
                  skillMatch={selectedSkillMatch}
                  theme={getThemeForIndex(selectedIndex)}
                  aiSummary={selectedNarrative.aiSummary}
                  recommendation={selectedNarrative.recommendation}
                />
              </div>
            )}
          </div>
        )}

        {hasResult && <CareerConversationBanner />}

        <TailoredResumeBanner />
      </div>
    </>
  )
}
