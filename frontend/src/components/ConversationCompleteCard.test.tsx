import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ConversationCompleteCard from './ConversationCompleteCard'

function renderCard() {
  return render(
    <MemoryRouter initialEntries={['/career-conversation']}>
      <Routes>
        <Route
          path="/career-conversation"
          element={<ConversationCompleteCard stopReason="Enough evidence." questionsAnswered={3} />}
        />
        <Route path="/tailored-resume" element={<div>Tailored Resume Page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ConversationCompleteCard', () => {
  it('renders an enabled "Generate Tailored Resume" CTA, not a disabled placeholder', () => {
    renderCard()

    const button = screen.getByRole('button', { name: /generate tailored resume/i })
    expect(button).toBeEnabled()
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument()
  })

  it('navigates to /tailored-resume when clicked', async () => {
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /generate tailored resume/i }))

    await waitFor(() => expect(screen.getByText('Tailored Resume Page')).toBeInTheDocument())
  })
})
