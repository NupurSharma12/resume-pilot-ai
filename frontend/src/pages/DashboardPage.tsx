import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import InputSection from '../components/InputSection'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import CandidateHeroCard from '../components/CandidateHeroCard'
import MetricCard from '../components/MetricCard'
import AnalysisPanel from '../components/AnalysisPanel'
import AnalyzingState from '../components/AnalyzingState'
import AnalysisErrorState from '../components/AnalysisErrorState'
import TailoredResumeBanner from '../components/TailoredResumeBanner'
import { getThemeForIndex } from '../data/theme'
import { candidate, skillMatchNarratives, defaultSkillMatchNarrative } from '../data/mockData'
import { analyzeResume, ApiError } from '../lib/api'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

export default function DashboardPage() {
  // `resumeAnalysis` lives one level up, in DashboardLayout, and is shared
  // via Outlet context — not local state here — so the sidebar's summary
  // card and this page always render the same analysis, never two
  // independently-drifting copies of it (see DashboardLayout's docstring).
  const { resumeAnalysis, setResumeAnalysis } = useOutletContext<DashboardOutletContext>()

  // Starts 'idle', looking exactly like the pre-integration mock dashboard —
  // nothing changes on screen until a user actually triggers an analysis.
  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  // The two real inputs. Only the resolved {text, fileName} is kept here —
  // file objects and extraction status stay local to ResumeInput/
  // JobDescriptionInput (see their own comments).
  const [resume, setResume] = useState<ResumeInputValue | null>(null)
  const [jobDescription, setJobDescription] = useState<JobDescriptionInputValue | null>(null)
  const [isInputCollapsed, setIsInputCollapsed] = useState(false)

  const { overall_assessment, skill_matches } = resumeAnalysis

  const [selectedCategory, setSelectedCategory] = useState<string | undefined>(
    skill_matches[0]?.category,
  )

  const selectedIndex = skill_matches.findIndex((s) => s.category === selectedCategory)
  const selectedSkillMatch = selectedIndex >= 0 ? skill_matches[selectedIndex] : undefined
  const selectedNarrative = selectedSkillMatch
    ? (skillMatchNarratives[selectedSkillMatch.category] ?? defaultSkillMatchNarrative)
    : undefined

  const canAnalyze = Boolean(resume) && Boolean(jobDescription)

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
          onResumeChange={setResume}
          onJobDescriptionChange={setJobDescription}
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

        {(status === 'idle' || status === 'success') && (
          <div key={status} className="animate-panel-fade space-y-8">
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
          </div>
        )}

        <TailoredResumeBanner />
      </div>
    </>
  )
}
