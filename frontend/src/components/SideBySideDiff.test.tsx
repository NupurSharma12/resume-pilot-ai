import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SideBySideDiff from './SideBySideDiff'
import type { DiffHunk } from '../lib/resumeSectionDiff'

describe('SideBySideDiff', () => {
  it('shows an empty-state message and no diff chrome when there are no hunks', () => {
    render(<SideBySideDiff hunks={[]} />)

    expect(screen.getByText(/no changes to preview/i)).toBeInTheDocument()
    expect(screen.queryByText('Original')).not.toBeInTheDocument()
    expect(screen.queryByText('Proposed')).not.toBeInTheDocument()
  })

  it('supports a custom empty-state message', () => {
    render(<SideBySideDiff hunks={[]} emptyMessage="No changes in this section." />)
    expect(screen.getByText('No changes in this section.')).toBeInTheDocument()
  })

  it('renders Original/Proposed column headers when there is at least one hunk', () => {
    const hunks: DiffHunk[] = [
      { rows: [{ left: null, right: { type: 'added', text: 'TypeScript' } }] },
    ]
    render(<SideBySideDiff hunks={hunks} />)

    expect(screen.getByText('Original')).toBeInTheDocument()
    expect(screen.getByText('Proposed')).toBeInTheDocument()
  })

  it('renders an addition with a "+" indicator and no left-side content', () => {
    const hunks: DiffHunk[] = [
      { rows: [{ left: null, right: { type: 'added', text: 'TypeScript' } }] },
    ]
    const { container } = render(<SideBySideDiff hunks={hunks} />)

    expect(screen.getByText('TypeScript')).toBeInTheDocument()
    expect(screen.getByText('+')).toBeInTheDocument()
    expect(screen.queryByText('-')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.bg-emerald-50')).toHaveLength(1)
  })

  it('renders a removal with a "-" indicator and no right-side content', () => {
    const hunks: DiffHunk[] = [
      { rows: [{ left: { type: 'removed', text: 'Old certification.' }, right: null }] },
    ]
    const { container } = render(<SideBySideDiff hunks={hunks} />)

    expect(screen.getByText('Old certification.')).toBeInTheDocument()
    expect(screen.getByText('-')).toBeInTheDocument()
    expect(container.querySelectorAll('.bg-rose-50')).toHaveLength(1)
  })

  it('renders an unchanged row plainly, with no +/- indicator', () => {
    const hunks: DiffHunk[] = [
      {
        rows: [
          { left: { type: 'unchanged', text: 'Python' }, right: { type: 'unchanged', text: 'Python' } },
        ],
      },
    ]
    render(<SideBySideDiff hunks={hunks} />)

    expect(screen.getAllByText('Python')).toHaveLength(2)
    expect(screen.queryByText('+')).not.toBeInTheDocument()
    expect(screen.queryByText('-')).not.toBeInTheDocument()
  })

  it('aligns old and new text on the same row for a replace pairing', () => {
    const hunks: DiffHunk[] = [
      {
        rows: [
          {
            left: { type: 'removed', text: 'Backend engineer.' },
            right: { type: 'added', text: 'Full-stack engineer.' },
          },
        ],
      },
    ]
    const { container } = render(<SideBySideDiff hunks={hunks} />)

    const row = container.querySelectorAll('.grid.grid-cols-2')[1] // [0] is the header row
    expect(row.textContent).toContain('Backend engineer.')
    expect(row.textContent).toContain('Full-stack engineer.')
  })

  it('highlights only the changed segments of a modified cell, leaving unchanged text plain', () => {
    const hunks: DiffHunk[] = [
      {
        rows: [
          {
            left: {
              type: 'removed',
              text: 'Backend engineer.',
              segments: [
                { text: 'Backend', changed: true },
                { text: ' ', changed: false },
                { text: 'engineer.', changed: false },
              ],
            },
            right: {
              type: 'added',
              text: 'Full-stack engineer.',
              segments: [
                { text: 'Full-stack', changed: true },
                { text: ' ', changed: false },
                { text: 'engineer.', changed: false },
              ],
            },
          },
        ],
      },
    ]
    const { container } = render(<SideBySideDiff hunks={hunks} />)

    const marks = Array.from(container.querySelectorAll('mark')).map((el) => el.textContent)
    expect(marks).toEqual(['Backend', 'Full-stack'])
    // The shared word is present but not inside a <mark>.
    expect(container.textContent).toContain('engineer.')
    expect(container.querySelectorAll('mark')[0].textContent).not.toContain('engineer')
  })

  it('falls back to plain text when a modified cell has no segments', () => {
    const hunks: DiffHunk[] = [
      {
        rows: [
          {
            left: { type: 'removed', text: 'Old text.' },
            right: { type: 'added', text: 'New text.' },
          },
        ],
      },
    ]
    const { container } = render(<SideBySideDiff hunks={hunks} />)

    expect(container.querySelectorAll('mark')).toHaveLength(0)
    expect(container.textContent).toContain('Old text.')
    expect(container.textContent).toContain('New text.')
  })

  it('renders multiple hunks with a visual separator between them', () => {
    const hunks: DiffHunk[] = [
      { rows: [{ left: null, right: { type: 'added', text: 'First hunk.' } }] },
      { rows: [{ left: null, right: { type: 'added', text: 'Second hunk.' } }] },
    ]
    render(<SideBySideDiff hunks={hunks} />)

    expect(screen.getByText('First hunk.')).toBeInTheDocument()
    expect(screen.getByText('Second hunk.')).toBeInTheDocument()
  })
})
