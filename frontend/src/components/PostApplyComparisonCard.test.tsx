import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PostApplyComparisonCard from './PostApplyComparisonCard'
import type { ResumeAnalysisComparison } from '../data/postApplyTypes'

function comparison(overrides: Partial<ResumeAnalysisComparison> = {}): ResumeAnalysisComparison {
  return {
    score_before: 70,
    score_after: 70,
    score_delta: 0,
    status: 'unchanged',
    category_comparisons: [],
    strengths_gained: [],
    strengths_lost: [],
    weaknesses_resolved: [],
    weaknesses_remaining: [],
    new_weaknesses: [],
    ...overrides,
  }
}

describe('PostApplyComparisonCard', () => {
  it('presents an improved score as a measurable improvement', () => {
    render(
      <PostApplyComparisonCard
        comparison={comparison({ score_before: 72, score_after: 81, score_delta: 9, status: 'improved' })}
      />,
    )

    expect(screen.getByText(/improved by 9 points/i)).toBeInTheDocument()
    expect(screen.getByText(/measurably improved/i)).toBeInTheDocument()
  })

  it('never presents an unchanged score as a success', () => {
    render(
      <PostApplyComparisonCard
        comparison={comparison({ score_before: 78, score_after: 78, score_delta: 0, status: 'unchanged' })}
      />,
    )

    expect(screen.getByText(/did not improve/i)).toBeInTheDocument()
    expect(screen.getByText(/stayed the same/i)).toBeInTheDocument()
    expect(screen.getByText(/review the remaining gaps/i)).toBeInTheDocument()
    expect(screen.queryByText(/improved/i, { selector: 'h3' })).not.toBeInTheDocument()
  })

  it('never hides or softens a decreased score', () => {
    render(
      <PostApplyComparisonCard
        comparison={comparison({ score_before: 78, score_after: 74, score_delta: -4, status: 'decreased' })}
      />,
    )

    expect(screen.getByText(/decreased by 4 points/i)).toBeInTheDocument()
    expect(screen.getByText(/went down/i)).toBeInTheDocument()
    expect(screen.getByText(/further tailoring may be appropriate/i)).toBeInTheDocument()
  })

  it('renders category-level comparisons when present', () => {
    render(
      <PostApplyComparisonCard
        comparison={comparison({
          status: 'improved',
          score_delta: 20,
          category_comparisons: [
            {
              category: 'Frontend',
              score_before: 40,
              score_after: 60,
              score_delta: 20,
              status: 'improved',
              newly_matched_skills: ['React'],
              newly_missing_skills: [],
            },
          ],
        })}
      />,
    )

    expect(screen.getByText('Frontend')).toBeInTheDocument()
    expect(screen.getByText('+React')).toBeInTheDocument()
  })

  it('renders regressions (lost strengths, new weaknesses) without hiding them', () => {
    render(
      <PostApplyComparisonCard
        comparison={comparison({
          status: 'decreased',
          score_delta: -5,
          strengths_lost: ['Strong backend ownership.'],
          new_weaknesses: ['Resume no longer demonstrates ownership clearly.'],
        })}
      />,
    )

    expect(screen.getByText('Lost strengths')).toBeInTheDocument()
    expect(screen.getByText('Strong backend ownership.')).toBeInTheDocument()
    expect(screen.getByText('New gaps')).toBeInTheDocument()
    expect(
      screen.getByText('Resume no longer demonstrates ownership clearly.'),
    ).toBeInTheDocument()
  })

  it('omits empty sections rather than rendering blank headings', () => {
    render(<PostApplyComparisonCard comparison={comparison()} />)

    expect(screen.queryByText('Category breakdown')).not.toBeInTheDocument()
    expect(screen.queryByText('New strengths')).not.toBeInTheDocument()
  })
})
