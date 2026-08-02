import { Loader2, Upload } from 'lucide-react'
import Button from './Button'

interface TopHeaderProps {
  title: string
  subtitle: string
  onAnalyze: () => void
  isAnalyzing: boolean
}

export default function TopHeader({ title, subtitle, onAnalyze, isAnalyzing }: TopHeaderProps) {
  return (
    <header className="border-b border-gray-200 bg-white px-8 py-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <Button variant="outline" icon={<Upload size={16} />} disabled={isAnalyzing}>
            Upload Resume
          </Button>
          {/*
            Stands in for a real "Upload Job Description" flow: file upload
            isn't implemented yet (see sampleInput.ts), so this button
            currently triggers analysis of the hardcoded sample text. Label
            and position are unchanged; only behavior and the transient
            loading content are new.
          */}
          <Button
            variant="solid"
            icon={isAnalyzing ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
            disabled={isAnalyzing}
            onClick={onAnalyze}
          >
            {isAnalyzing ? 'Analyzing…' : 'Upload Job Description'}
          </Button>
        </div>
      </div>
    </header>
  )
}
