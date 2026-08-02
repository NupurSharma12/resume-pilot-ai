import { Upload } from 'lucide-react'
import Button from './Button'

interface TopHeaderProps {
  title: string
  subtitle: string
}

export default function TopHeader({ title, subtitle }: TopHeaderProps) {
  return (
    <header className="border-b border-gray-200 bg-white px-8 py-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <Button variant="outline" icon={<Upload size={16} />}>
            Upload Resume
          </Button>
          <Button variant="solid" icon={<Upload size={16} />}>
            Upload Job Description
          </Button>
        </div>
      </div>
    </header>
  )
}
