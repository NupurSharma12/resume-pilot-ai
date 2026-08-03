interface TopHeaderProps {
  title: string
  subtitle: string
}

export default function TopHeader({ title, subtitle }: TopHeaderProps) {
  return (
    <header className="border-b border-gray-200 bg-white px-8 py-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
      </div>
    </header>
  )
}
