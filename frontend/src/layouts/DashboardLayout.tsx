import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import HelpButton from '../components/HelpButton'
import { mockResumeAnalysis } from '../data/mockData'
import type { ResumeAnalysisResult } from '../data/types'

export interface DashboardOutletContext {
  resumeAnalysis: ResumeAnalysisResult
  setResumeAnalysis: (result: ResumeAnalysisResult) => void
}

export default function DashboardLayout() {
  // Owned here, not in DashboardPage: the sidebar's mini summary card and
  // the routed page content both need the latest analysis, so there must
  // be exactly one instance of this state for them to share (via Outlet
  // context below), not two components each defaulting to their own copy
  // of the mock data and silently drifting apart after a real analysis.
  const [resumeAnalysis, setResumeAnalysis] = useState<ResumeAnalysisResult>(mockResumeAnalysis)

  return (
    <div className="flex h-screen bg-[#f7f8fa]">
      <Sidebar overallScore={resumeAnalysis.overall_assessment.overall_score} />
      <main className="flex-1 overflow-y-auto">
        <Outlet context={{ resumeAnalysis, setResumeAnalysis } satisfies DashboardOutletContext} />
      </main>
      <HelpButton />
    </div>
  )
}
