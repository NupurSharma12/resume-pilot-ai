import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ConversationCompleteCard from './ConversationCompleteCard'
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

function renderCard(overrides: Partial<PersistedResumeSession> = {}) {
  const storage = createFakeStorage(fixturePersistedSession(overrides))
  return render(
    <ResumeSessionProvider storage={storage}>
      <MemoryRouter initialEntries={['/career-conversation']}>
        <Routes>
          <Route
            path="/career-conversation"
            element={
              <ConversationCompleteCard stopReason="Enough evidence." questionsAnswered={3} />
            }
          />
          <Route path="/tailored-resume" element={<div>Tailored Resume Page</div>} />
        </Routes>
      </MemoryRouter>
    </ResumeSessionProvider>,
  )
}

describe('ConversationCompleteCard', () => {
  it('renders an enabled "Generate Tailoring Plan" CTA when no plan exists yet', () => {
    renderCard()

    const button = screen.getByRole('button', { name: /generate tailoring plan/i })
    expect(button).toBeEnabled()
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument()
  })

  it('shows "Review Suggestions" once a plan exists but nothing has been applied yet', () => {
    renderCard({ tailoringPlan: fixtureGenerateSuggestionsResponse })

    expect(screen.getByRole('button', { name: /review suggestions/i })).toBeInTheDocument()
  })

  it('shows "View Tailored Resume" once a final resume already exists in session', () => {
    renderCard({
      tailoringPlan: fixtureGenerateSuggestionsResponse,
      finalTailoredResume: {
        finalResumeText: fixtureApplySuggestionsResponse.final_resume_text,
        appliedSuggestionIds: fixtureApplySuggestionsResponse.applied_suggestion_ids,
      },
    })

    expect(screen.getByRole('button', { name: /view tailored resume/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /^generate tailoring plan$/i }),
    ).not.toBeInTheDocument()
  })

  it('navigates to /tailored-resume when clicked', async () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /generate tailoring plan/i }))

    await waitFor(() => expect(screen.getByText('Tailored Resume Page')).toBeInTheDocument())
  })
})
