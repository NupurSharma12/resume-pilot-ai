import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Sidebar from './Sidebar'
import { fixtureResumeAnalysis } from '../testFixtures'

function renderSidebar(resumeAnalysis: typeof fixtureResumeAnalysis | null) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<Sidebar resumeAnalysis={resumeAnalysis} />} />
      </Routes>
    </MemoryRouter>,
  )
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
          <Route path="/" element={<Sidebar resumeAnalysis={fixtureResumeAnalysis} />} />
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
