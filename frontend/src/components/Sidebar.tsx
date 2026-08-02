import {
  Sparkles,
  FileText,
  Briefcase,
  LayoutGrid,
  Wand2,
  History,
  Settings,
} from 'lucide-react'
import { useLocation } from 'react-router-dom'
import Badge from './Badge'
import CandidateSummaryCard from './CandidateSummaryCard'
import { candidate, mockResumeAnalysis } from '../data/mockData'

const NAV_ITEMS = [
  { id: 'resume', label: 'Resume', icon: FileText },
  { id: 'job-description', label: 'Job Description', icon: Briefcase },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutGrid },
  { id: 'tailored-resume', label: 'Tailored Resume', icon: Wand2, disabled: true },
  { id: 'history', label: 'History', icon: History },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const location = useLocation()
  const isDashboardActive = location.pathname === '/'

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
          const isActive = item.id === 'dashboard' && isDashboardActive
          const Icon = item.icon

          return (
            <div
              key={item.id}
              className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm font-medium ${
                isActive
                  ? 'bg-indigo-50 text-indigo-600'
                  : item.disabled
                    ? 'text-gray-300'
                    : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              <span className="flex items-center gap-3">
                <Icon size={18} />
                {item.label}
              </span>
              {item.disabled && <Badge variant="gray">SOON</Badge>}
            </div>
          )
        })}
      </nav>

      <div className="mt-auto p-4">
        <CandidateSummaryCard
          candidate={candidate}
          overallScore={mockResumeAnalysis.overall_assessment.overall_score}
        />
      </div>
    </aside>
  )
}
