import {
  Sparkles,
  FileText,
  Briefcase,
  LayoutGrid,
  Wand2,
  History,
  Settings,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import CandidateSummaryCard from './CandidateSummaryCard'
import { candidate } from '../data/mockData'
import type { ResumeAnalysisResult } from '../data/types'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'

const NAV_ITEMS = [
  { id: 'resume', label: 'Resume', icon: FileText, path: '/resume' },
  { id: 'job-description', label: 'Job Description', icon: Briefcase, path: '/job-description' },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutGrid, path: '/' },
  { id: 'tailored-resume', label: 'Tailored Resume', icon: Wand2, path: '/tailored-resume' },
  { id: 'history', label: 'History', icon: History, path: '/history' },
  { id: 'settings', label: 'Settings', icon: Settings, path: '/settings' },
] as const

interface SidebarProps {
  resumeAnalysis: ResumeAnalysisResult | null
  // The Post-Apply Analysis Loop's latest comparison, if a re-analysis has
  // completed (see docs/features/postapply-analysis-loop.md) -- `null`
  // covers both "never re-analyzed" and "a new apply since re-analyzing
  // superseded it" (see TailoredResumePage's `attemptApply`, which resets
  // this on every commit). Deliberately a *separate* prop from
  // `resumeAnalysis`, never merged into it: `resumeAnalysis` stays the
  // fixed "before" baseline every comparison measures against for the
  // lifetime of the session, so this sidebar can show the latest known
  // score without that baseline ever being overwritten.
  postApplyComparison: ResumeAnalysisComparison | null
}

export default function Sidebar({ resumeAnalysis, postApplyComparison }: SidebarProps) {
  const location = useLocation()

  return (
    <aside className="flex h-screen w-[280px] shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center gap-2.5 px-6 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-600">
          <Sparkles size={18} className="text-white" />
        </div>
        <span className="text-lg font-bold text-gray-900">ResumePilotAI</span>
      </div>
      <div className="border-b border-gray-200" />

      <nav className="flex flex-col gap-1 px-4 py-4">
        {NAV_ITEMS.map((item) => {
          // Tailored Resume is only ever gated on a completed analysis
          // existing to ground it in — same prerequisite
          // CareerConversationPage/TailoredResumePage already enforce; no
          // other nav item is ever disabled.
          const disabled = item.id === 'tailored-resume' && resumeAnalysis === null
          const isActive = location.pathname === item.path
          const Icon = item.icon
          const className = `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${
            isActive
              ? 'bg-indigo-50 text-indigo-600'
              : disabled
                ? 'text-gray-300'
                : 'text-gray-600 hover:bg-gray-50'
          }`
          const content = (
            <>
              <Icon size={18} />
              {item.label}
            </>
          )

          if (disabled) {
            return (
              <div key={item.id} className={className}>
                {content}
              </div>
            )
          }

          return (
            <Link key={item.id} to={item.path} className={className}>
              {content}
            </Link>
          )
        })}
      </nav>

      {resumeAnalysis && (
        <div className="mt-auto p-4">
          <CandidateSummaryCard
            candidate={candidate}
            overallScore={
              postApplyComparison?.score_after ?? resumeAnalysis.overall_assessment.overall_score
            }
            updatedAfterTailoring={postApplyComparison !== null}
          />
        </div>
      )}
    </aside>
  )
}
