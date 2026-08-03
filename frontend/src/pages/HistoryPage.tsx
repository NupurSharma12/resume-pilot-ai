import TopHeader from '../components/TopHeader'

export default function HistoryPage() {
  return (
    <>
      <TopHeader title="History" subtitle="Past analyses will appear here" />
      <div className="p-8">
        <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
          Analysis history is coming soon.
        </div>
      </div>
    </>
  )
}
