import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
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
    hydrationStatus,
    resumeAnalysis,
    setResumeAnalysis,
    resume,
    setResume,
    jobDescription,
    setJobDescription,
    status,
    setStatus,
    postApplyComparison,
  } = useResumeSession()
  const [errorMessage, setErrorMessage] = useState('')
  const [isInputCollapsed, setIsInputCollapsed] = useState(false)

  // Every child page (Dashboard, Resume, Job Description, Career
  // Conversation, Tailored Resume) reads `resumeAnalysis`/`resume`/
  // `jobDescription`/`status` (via this layout's Outlet context) or
  // `careerConversationStatus`/`tailoredResumeResult`/
  // `activeCareerConversationSessionId` (via `useResumeSession()`
  // directly) to decide what to show — and every one of those is still
  // `null`/`idle` for one render while `ResumeSessionProvider` is
  // rehydrating from storage after a fresh page load. Gating the *whole*
  // layout here, once, centrally, is what stops that pending-hydration
  // instant from ever painting as "nothing exists yet" (an empty
  // Dashboard with no CareerConversationBanner/TailoredResumeBanner, a
  // Sidebar with no candidate summary, Tailored Resume showing disabled)
  // immediately before flipping to the real, already-restored state a
  // moment later. `CareerConversationPage`/`TailoredResumePage` also gate
  // on this individually (defense in depth, and so they still behave
  // correctly if ever rendered outside this layout, e.g. in tests) — this
  // is what closes the gap for every *other* page, which never had that
  // protection.
  if (hydrationStatus !== 'hydrated') {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f7f8fa]">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 animate-pulse items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
            <Sparkles size={22} className="text-white" />
          </div>
          <p className="text-sm font-medium text-gray-500">Restoring your session…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-[#f7f8fa]">
      <Sidebar resumeAnalysis={resumeAnalysis} postApplyComparison={postApplyComparison} />
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
