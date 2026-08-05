import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ValidationReportCard from './ValidationReportCard'
import { fixtureTailorResult } from '../testFixtures'

describe('ValidationReportCard', () => {
  it('shows the accepted/total summary and every rejected bullet with its reason', () => {
    render(<ValidationReportCard report={fixtureTailorResult.validation_report} />)

    expect(screen.getByText('1/2 accepted')).toBeInTheDocument()
    expect(
      screen.getByText('Reduced infrastructure costs by 40% using Kubernetes.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Contains term\(s\) not present in cited evidence: Kubernetes\./),
    ).toBeInTheDocument()
  })

  it('renders no rejected-bullet list when everything passed', () => {
    render(
      <ValidationReportCard
        report={{
          total_bullets: 1,
          accepted_count: 1,
          rejected_count: 0,
          rejected_bullets: [],
          passed: true,
        }}
      />,
    )

    expect(screen.getByText('1/1 accepted')).toBeInTheDocument()
    expect(screen.queryByText(/Contains term/)).not.toBeInTheDocument()
  })
})
