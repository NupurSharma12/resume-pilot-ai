import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TailoringPlanSummaryHeader from './TailoringPlanSummaryHeader'

describe('TailoringPlanSummaryHeader', () => {
  it('renders the suggestion count, recommended count, and optional count', () => {
    render(
      <TailoringPlanSummaryHeader
        totalCount={12}
        recommendedCount={9}
        onApplyRecommended={vi.fn()}
        onCustomize={vi.fn()}
      />,
    )

    expect(screen.getByText('Tailoring Suggestions')).toBeInTheDocument()
    expect(screen.getByText('12 suggestions found')).toBeInTheDocument()
    expect(screen.getByText('9 recommended')).toBeInTheDocument()
    expect(screen.getByText('3 optional')).toBeInTheDocument()
  })

  it('uses singular phrasing for exactly one suggestion', () => {
    render(
      <TailoringPlanSummaryHeader
        totalCount={1}
        recommendedCount={1}
        onApplyRecommended={vi.fn()}
        onCustomize={vi.fn()}
      />,
    )

    expect(screen.getByText('1 suggestion found')).toBeInTheDocument()
    expect(screen.getByText('0 optional')).toBeInTheDocument()
  })

  it('calls onApplyRecommended and onCustomize from their respective buttons', () => {
    const onApplyRecommended = vi.fn()
    const onCustomize = vi.fn()
    render(
      <TailoringPlanSummaryHeader
        totalCount={9}
        recommendedCount={7}
        onApplyRecommended={onApplyRecommended}
        onCustomize={onCustomize}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /apply recommended/i }))
    fireEvent.click(screen.getByRole('button', { name: /customize selection/i }))

    expect(onApplyRecommended).toHaveBeenCalledTimes(1)
    expect(onCustomize).toHaveBeenCalledTimes(1)
  })

  it('disables Apply Recommended when nothing is recommended', () => {
    render(
      <TailoringPlanSummaryHeader
        totalCount={2}
        recommendedCount={0}
        onApplyRecommended={vi.fn()}
        onCustomize={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: /apply recommended/i })).toBeDisabled()
    expect(screen.getByText('2 optional')).toBeInTheDocument()
  })
})
