import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Sidebar from './Sidebar'
import { fixtureResumeAnalysis } from '../testFixtures'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'

function renderSidebar(
  resumeAnalysis: typeof fixtureResumeAnalysis | null,
  postApplyComparison: ResumeAnalysisComparison | null = null,
) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route
          path="/"
          element={
            <Sidebar resumeAnalysis={resumeAnalysis} postApplyComparison={postApplyComparison} />
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

const fixtureComparison: ResumeAnalysisComparison = {
  score_before: fixtureResumeAnalysis.overall_assessment.overall_score,
  score_after: 91,
  score_delta: 91 - fixtureResumeAnalysis.overall_assessment.overall_score,
  status: 'improved',
  category_comparisons: [],
  strengths_gained: [],
  strengths_lost: [],
  weaknesses_resolved: [],
  weaknesses_remaining: [],
  new_weaknesses: [],
}

describe('Sidebar Tailored Resume nav item', () => {
  it('is disabled, with no "SOON" badge, when there is no resume analysis yet', () => {
    renderSidebar(null)

    expect(screen.queryByText(/soon/i)).not.toBeInTheDocument()
    // Disabled items render as a plain, non-interactive element, not a link.
    expect(screen.queryByRole('link', { name: /tailored resume/i })).not.toBeInTheDocument()
    expect(screen.getByText('Tailored Resume')).toBeInTheDocument()
  })

  it('is enabled and routes to /tailored-resume once a resume analysis exists', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={<Sidebar resumeAnalysis={fixtureResumeAnalysis} postApplyComparison={null} />}
          />
          <Route path="/tailored-resume" element={<div>Tailored Resume Page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    const link = screen.getByRole('link', { name: /tailored resume/i })
    expect(link).toHaveAttribute('href', '/tailored-resume')

    fireEvent.click(link)

    await waitFor(() => expect(screen.getByText('Tailored Resume Page')).toBeInTheDocument())
  })

  it('never shows a "SOON" badge, even when disabled', () => {
    renderSidebar(null)

    expect(screen.queryByText('SOON')).not.toBeInTheDocument()
  })
})

describe('Sidebar candidate score', () => {
  it('shows the original analysis score when there is no post-apply comparison yet', () => {
    renderSidebar(fixtureResumeAnalysis, null)

    expect(
      screen.getByText(`${fixtureResumeAnalysis.overall_assessment.overall_score}%`),
    ).toBeInTheDocument()
    expect(screen.queryByText(/updated after tailoring/i)).not.toBeInTheDocument()
  })

  it('shows the re-analyzed score, with an "updated" note, once a post-apply comparison exists', () => {
    renderSidebar(fixtureResumeAnalysis, fixtureComparison)

    expect(screen.getByText(`${fixtureComparison.score_after}%`)).toBeInTheDocument()
    expect(
      screen.queryByText(`${fixtureResumeAnalysis.overall_assessment.overall_score}%`),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/updated after tailoring/i)).toBeInTheDocument()
  })
})
