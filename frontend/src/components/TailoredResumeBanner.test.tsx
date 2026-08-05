import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TailoredResumeBanner from './TailoredResumeBanner'
import { ResumeSessionProvider } from '../session/ResumeSessionContext'
import { fixturePersistedSession, fixtureTailorResult } from '../testFixtures'
import type { PersistedResumeSession, ResumeSessionStorage } from '../session/resumeSessionTypes'

function createFakeStorage(initial: PersistedResumeSession | null): ResumeSessionStorage {
  let state = initial
  return {
    load: () => state,
    save: (session) => {
      state = session
    },
    clear: () => {
      state = null
    },
  }
}

function renderBanner(overrides: Partial<PersistedResumeSession> = {}) {
  const storage = createFakeStorage(fixturePersistedSession(overrides))
  return render(
    <ResumeSessionProvider storage={storage}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<TailoredResumeBanner />} />
          <Route path="/tailored-resume" element={<div>Tailored Resume Page</div>} />
        </Routes>
      </MemoryRouter>
    </ResumeSessionProvider>,
  )
}

describe('TailoredResumeBanner', () => {
  it('shows a disabled "Complete Career Conversation first." CTA when the conversation is not complete', () => {
    renderBanner({ careerConversationStatus: null })

    const button = screen.getByRole('button', { name: /complete career conversation first/i })
    expect(button).toBeDisabled()
  })

  it('shows a disabled CTA while the conversation is still in progress', () => {
    renderBanner({ careerConversationStatus: 'in_progress' })

    expect(
      screen.getByRole('button', { name: /complete career conversation first/i }),
    ).toBeDisabled()
  })

  it('shows an enabled "Generate Tailored Resume" CTA once the conversation is complete', () => {
    renderBanner({ careerConversationStatus: 'complete' })

    const button = screen.getByRole('button', { name: /generate tailored resume/i })
    expect(button).toBeEnabled()
  })

  it('shows "View Tailored Resume" once a tailored resume already exists this session', () => {
    renderBanner({ careerConversationStatus: 'complete', tailoredResumeResult: fixtureTailorResult })

    expect(screen.getByRole('button', { name: /view tailored resume/i })).toBeEnabled()
  })

  it('navigates to /tailored-resume when the enabled CTA is clicked', async () => {
    renderBanner({ careerConversationStatus: 'complete' })

    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

    await waitFor(() => expect(screen.getByText('Tailored Resume Page')).toBeInTheDocument())
  })

  it('never renders a "COMING SOON" placeholder badge', () => {
    renderBanner()

    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument()
  })
})
