import { Wand2 } from 'lucide-react'
import Badge from './Badge'
import Button from './Button'

export default function TailoredResumeBanner() {
  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white">
      <div className="flex items-center justify-between gap-6 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Wand2 size={22} />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h3 className="font-semibold text-gray-900">Tailored Resume Generator</h3>
              <Badge variant="amber">COMING SOON</Badge>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Generate an AI-optimized resume for this job description — boosted for ATS
              scoring and recruiter readability.
            </p>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <Button variant="outline" icon={<Wand2 size={16} />} disabled>
            Generate Tailored Resume
          </Button>
          <p className="mt-1.5 text-xs text-gray-400">Feature not yet available</p>
        </div>
      </div>

      <div className="h-1 w-full bg-gray-100">
        <div className="h-full w-[6%] bg-indigo-600" />
      </div>
    </div>
  )
}
