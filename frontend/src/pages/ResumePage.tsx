import { useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import ExtractedContentCard from '../components/ExtractedContentCard'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

export default function ResumePage() {
  const { resume } = useOutletContext<DashboardOutletContext>()

  return (
    <>
      <TopHeader title="Resume" subtitle="The resume currently used for analysis" />
      <div className="p-8">
        <ExtractedContentCard
          title="Extracted Resume Text"
          fileName={resume?.fileName ?? null}
          text={resume?.text ?? ''}
          emptyMessage="No resume uploaded yet. Upload one from the Dashboard to see it here."
        />
      </div>
    </>
  )
}
