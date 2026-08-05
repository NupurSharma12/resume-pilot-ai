import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import TailoringPlanCard from './TailoringPlanCard'
import { fixtureTailorResult } from '../testFixtures'

describe('TailoringPlanCard', () => {
  it('renders each planned change with its section, action, reason, and evidence ids', () => {
    render(<TailoringPlanCard plan={fixtureTailorResult.tailoring_plan} />)

    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('Rewrite')).toBeInTheDocument()
    expect(screen.getByText(/Recent backend engineering work is missing/)).toBeInTheDocument()
    expect(screen.getByText('conversation-turn-1')).toBeInTheDocument()
  })

  it('shows a fallback message when no changes were proposed', () => {
    render(<TailoringPlanCard plan={{ changes: [] }} />)

    expect(screen.getByText('No changes were proposed.')).toBeInTheDocument()
  })
})
