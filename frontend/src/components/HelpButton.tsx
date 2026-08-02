import { HelpCircle } from 'lucide-react'

export default function HelpButton() {
  return (
    <button
      type="button"
      aria-label="Help"
      className="fixed bottom-6 right-6 flex h-11 w-11 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-400 shadow-sm transition-colors hover:text-gray-600"
    >
      <HelpCircle size={20} />
    </button>
  )
}
