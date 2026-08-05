import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import TailoredResumeView from './TailoredResumeView'
import { fixtureTailorResult } from '../testFixtures'

describe('TailoredResumeView', () => {
  it('renders accepted sections with their bullets and supporting evidence ids', () => {
    render(<TailoredResumeView tailoredResume={fixtureTailorResult.tailored_resume} />)

    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(
      screen.getByText('Led the migration of the dashboard from Angular to React.'),
    ).toBeInTheDocument()
    expect(screen.getByText('conversation-turn-1')).toBeInTheDocument()
  })

  it('shows a fallback message when no sections survived validation', () => {
    render(<TailoredResumeView tailoredResume={{ sections: [] }} />)

    expect(screen.getByText(/No proposed changes passed validation/)).toBeInTheDocument()
  })
})
