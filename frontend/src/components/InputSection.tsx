import { Sparkles } from 'lucide-react'
import ResumeInput, { type ResumeInputValue } from './ResumeInput'
import JobDescriptionInput, { type JobDescriptionInputValue } from './JobDescriptionInput'
import CompactInputRow from './CompactInputRow'
import Button from './Button'

interface InputSectionProps {
  resume: ResumeInputValue | null
  jobDescription: JobDescriptionInputValue | null
  onResumeChange: (value: ResumeInputValue | null) => void
  onJobDescriptionChange: (value: JobDescriptionInputValue | null) => void
  isCollapsed: boolean
  onExpand: () => void
  onAnalyze: () => void
  canAnalyze: boolean
  isAnalyzing: boolean
}

// ResumeInput/JobDescriptionInput stay mounted at all times (only visually
// hidden via `hidden` when collapsed) rather than being conditionally
// removed from the tree — unmounting them on collapse would reset their
// internal file/text state, so clicking "Change" would show an empty form
// instead of what was actually uploaded.
export default function InputSection({
  resume,
  jobDescription,
  onResumeChange,
  onJobDescriptionChange,
  isCollapsed,
  onExpand,
  onAnalyze,
  canAnalyze,
  isAnalyzing,
}: InputSectionProps) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      {isCollapsed && resume && jobDescription && (
        <div className="divide-y divide-gray-100">
          <CompactInputRow label="Resume" value={resume.fileName} onChange={onExpand} />
          <CompactInputRow
            label="Job Description"
            value={jobDescription.fileName ?? `${jobDescription.text.length} characters`}
            onChange={onExpand}
          />
        </div>
      )}

      <div className={isCollapsed ? 'hidden' : ''}>
        <div className="grid grid-cols-2 gap-6">
          <ResumeInput value={resume} onChange={onResumeChange} />
          <JobDescriptionInput value={jobDescription} onChange={onJobDescriptionChange} />
        </div>

        <div className="mt-6 flex justify-end">
          <Button
            variant="solid"
            icon={<Sparkles size={16} />}
            disabled={!canAnalyze || isAnalyzing}
            onClick={onAnalyze}
          >
            Analyze Resume
          </Button>
        </div>
      </div>
    </div>
  )
}
