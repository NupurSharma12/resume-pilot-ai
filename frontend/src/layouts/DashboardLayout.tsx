import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import HelpButton from '../components/HelpButton'
import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeInputValue } from '../components/ResumeInput'
import type { JobDescriptionInputValue } from '../components/JobDescriptionInput'
import { useResumeSession } from '../session/ResumeSessionContext'
import type { AnalysisStatus } from '../session/resumeSessionTypes'

export type { AnalysisStatus }

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

// `resume`/`jobDescription`/`resumeAnalysis`/`status` are owned by
// `ResumeSessionProvider` (see session/ResumeSessionContext.tsx) so they
// survive a full reload, not just SPA navigation -- that's the whole reason
// this layout no longer holds them in its own `useState`. `errorMessage`
// and `isInputCollapsed` stay local: they're transient UI state (an
// in-flight error's text, whether a panel is expanded) that has no business
// surviving a reload, and re-deriving them from scratch on remount is
// exactly the right behavior, not a bug.
export default function DashboardLayout() {
  const {
    resumeAnalysis,
    setResumeAnalysis,
    resume,
    setResume,
    jobDescription,
    setJobDescription,
    status,
    setStatus,
  } = useResumeSession()
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
