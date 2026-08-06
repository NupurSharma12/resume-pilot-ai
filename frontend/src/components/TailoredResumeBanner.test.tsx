import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TailoredResumeBanner from './TailoredResumeBanner'
import { ResumeSessionProvider } from '../session/ResumeSessionContext'
import {
  fixtureApplySuggestionsResponse,
  fixtureGenerateSuggestionsResponse,
  fixturePersistedSession,
} from '../testFixtures'
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

  it('shows an enabled "Generate Tailoring Plan" CTA once the conversation is complete and no plan exists', () => {
    renderBanner({ careerConversationStatus: 'complete' })

    const button = screen.getByRole('button', { name: /generate tailoring plan/i })
    expect(button).toBeEnabled()
  })

  it('shows "Review Suggestions" once a plan exists but nothing has been applied yet', () => {
    renderBanner({
      careerConversationStatus: 'complete',
      tailoringPlan: fixtureGenerateSuggestionsResponse,
    })

    expect(screen.getByRole('button', { name: /review suggestions/i })).toBeEnabled()
  })

  it('shows "View Tailored Resume" once a final resume already exists this session', () => {
    renderBanner({
      careerConversationStatus: 'complete',
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
    })

    expect(screen.getByRole('button', { name: /view tailored resume/i })).toBeEnabled()
  })

  it('navigates to /tailored-resume when the enabled CTA is clicked', async () => {
    renderBanner({ careerConversationStatus: 'complete' })

    fireEvent.click(screen.getByRole('button', { name: /generate tailoring plan/i }))

    await waitFor(() => expect(screen.getByText('Tailored Resume Page')).toBeInTheDocument())
  })

  it('never renders a "COMING SOON" placeholder badge', () => {
    renderBanner()

    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument()
  })
})
