import { useOutletContext } from 'react-router-dom'
import TopHeader from '../components/TopHeader'
import ExtractedContentCard from '../components/ExtractedContentCard'
import type { DashboardOutletContext } from '../layouts/DashboardLayout'

export default function JobDescriptionPage() {
  const { jobDescription } = useOutletContext<DashboardOutletContext>()

  return (
    <>
      <TopHeader
        title="Job Description"
        subtitle="The job description currently used for analysis"
      />
      <div className="p-8">
        <ExtractedContentCard
          title="Job Description Text"
          fileName={jobDescription?.fileName ?? null}
          text={jobDescription?.text ?? ''}
          emptyMessage="No job description added yet. Paste or upload one from the Dashboard to see it here."
        />
      </div>
    </>
  )
}
