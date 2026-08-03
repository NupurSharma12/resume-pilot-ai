import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import HelpButton from '../components/HelpButton'
import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'

export type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error'

export interface DashboardOutletContext {
  resumeAnalysis: ResumeAnalysisResult | null
  setResumeAnalysis: (result: ResumeAnalysisResult) => void
  resume: ResumeInputValue | null
  onResumeChange: (value: ResumeInputValue | null) => void
  jobDescription: JobDescriptionInputValue | null
  onJobDescriptionChange: (value: JobDescriptionInputValue | null) => void
  status: AnalysisStatus
  setStatus: (status: AnalysisStatus) => void
  errorMessage: string
  setErrorMessage: (message: string) => void
  isInputCollapsed: boolean
  setIsInputCollapsed: (collapsed: boolean) => void
}

export default function DashboardLayout() {
  // Owned here, not in DashboardPage: the sidebar's mini summary card, the
  // Dashboard/Resume/Job Description routes all need the same upload and
  // analysis state, so there must be exactly one instance of each, shared
  // via Outlet context below, not several components each holding their
  // own copy that could drift apart.
  //
  // `resumeAnalysis` starts `null` — there is no mock fallback — so the
  // app's initial state is genuinely "nothing analyzed yet" rather than a
  // pre-filled dashboard.
  //
  // `status`/`errorMessage`/`isInputCollapsed` live here (not in
  // DashboardPage) for the same reason: DashboardPage unmounts whenever
  // the user navigates to /resume, /job-description, /history, or
  // /settings, so anything that needs to survive that navigation — e.g.
  // "the dashboard should still show results when you come back" — can't
  // be local page state.
  const [resumeAnalysis, setResumeAnalysis] = useState<ResumeAnalysisResult | null>(null)
  const [resume, setResume] = useState<ResumeInputValue | null>(null)
  const [jobDescription, setJobDescription] = useState<JobDescriptionInputValue | null>(null)
  const [status, setStatus] = useState<AnalysisStatus>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [isInputCollapsed, setIsInputCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-[#f7f8fa]">
      <Sidebar resumeAnalysis={resumeAnalysis} />
      <main className="flex-1 overflow-y-auto">
        <Outlet
          context={
            {
              resumeAnalysis,
              setResumeAnalysis,
              resume,
              onResumeChange: setResume,
              jobDescription,
              onJobDescriptionChange: setJobDescription,
              status,
              setStatus,
              errorMessage,
              setErrorMessage,
              isInputCollapsed,
              setIsInputCollapsed,
            } satisfies DashboardOutletContext
          }
        />
      </main>
      <HelpButton />
    </div>
  )
}
