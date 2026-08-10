import { describe, it, expect } from 'vitest'
import { buildReplaceRows, buildSuggestionDiffHunks, diffLines } from './resumeSectionDiff'

describe('diffLines', () => {
  it('marks everything as unchanged when nothing differs', () => {
    const result = diffLines(['Python', 'Django'], ['Python', 'Django'])
    expect(result).toEqual([
      { type: 'unchanged', text: 'Python' },
      { type: 'unchanged', text: 'Django' },
    ])
  })

  it('marks an appended line as added, keeping prior lines unchanged', () => {
    const result = diffLines(['Python'], ['Python', 'TypeScript'])
    expect(result).toEqual([
      { type: 'unchanged', text: 'Python' },
      { type: 'added', text: 'TypeScript' },
    ])
  })

  it('marks a removed line as removed', () => {
    const result = diffLines(['Python', 'Django'], ['Python'])
    expect(result).toEqual([
      { type: 'unchanged', text: 'Python' },
      { type: 'removed', text: 'Django' },
    ])
  })

  it('handles a full replacement as a remove plus an add', () => {
    const result = diffLines(['Backend engineer.'], ['Full-stack engineer.'])
    expect(result).toEqual([
      { type: 'removed', text: 'Backend engineer.' },
      { type: 'added', text: 'Full-stack engineer.' },
    ])
  })
})

describe('buildReplaceRows', () => {
  it('returns a single unchanged row for identical text', () => {
    expect(buildReplaceRows('Python', 'Python')).toEqual([
      { left: { type: 'unchanged', text: 'Python' }, right: { type: 'unchanged', text: 'Python' } },
    ])
  })

  it('returns an addition-only row when there was no old text', () => {
    expect(buildReplaceRows('', 'Node.js')).toEqual([
      { left: null, right: { type: 'added', text: 'Node.js' } },
    ])
  })

  it('returns a removal-only row when there is no new text', () => {
    expect(buildReplaceRows('Irrelevant certification.', '')).toEqual([
      { left: { type: 'removed', text: 'Irrelevant certification.' }, right: null },
    ])
  })

  it('splits an append (new text starts with the old text) into an unchanged row plus an addition row', () => {
    const rows = buildReplaceRows('Python', 'Python, TypeScript')
    expect(rows).toEqual([
      { left: { type: 'unchanged', text: 'Python' }, right: { type: 'unchanged', text: 'Python' } },
      { left: null, right: { type: 'added', text: 'TypeScript' } },
    ])
  })

  it('matches the exact motivating example: a sentence extended with a trailing clause', () => {
    const before = 'Engineering Leader and Technical Lead with 15+ years of experience'
    const after =
      'Engineering Leader and Technical Lead with 15+ years of experience, including people management and engineering team leadership'
    const rows = buildReplaceRows(before, after)
    expect(rows).toEqual([
      { left: { type: 'unchanged', text: before }, right: { type: 'unchanged', text: before } },
      {
        left: null,
        right: {
          type: 'added',
          text: 'including people management and engineering team leadership',
        },
      },
    ])
  })

  it('returns a single replace row (old removed, new added) for a genuine rewording', () => {
    const rows = buildReplaceRows('Backend', 'Full-stack')
    expect(rows).toEqual([
      {
        left: { type: 'removed', text: 'Backend', segments: [{ text: 'Backend', changed: true }] },
        right: { type: 'added', text: 'Full-stack', segments: [{ text: 'Full-stack', changed: true }] },
      },
    ])
  })

  it('highlights only the inserted words for a mid-sentence insertion (the bug report this fixes)', () => {
    // The exact motivating case: only "15+ years of " was inserted into the
    // middle of the sentence -- everything else is identical. This must
    // NOT render as though the whole sentence changed.
    const before = 'Senior Software Engineer with experience designing enterprise software.'
    const after =
      'Senior Software Engineer with 15+ years of experience designing enterprise software.'

    const [row] = buildReplaceRows(before, after)

    expect(row.left?.segments?.every((segment) => !segment.changed)).toBe(true)
    expect(row.left?.segments?.map((s) => s.text).join('')).toBe(before)

    const changedRightText = row.right?.segments?.filter((s) => s.changed).map((s) => s.text).join('')
    const unchangedRightText = row.right?.segments
      ?.filter((s) => !s.changed)
      .map((s) => s.text)
      .join('')
    expect(changedRightText).toBe('15+ years of ')
    expect(unchangedRightText).toBe(before)
  })

  it('highlights a single swapped word, leaving the rest of the sentence unmarked', () => {
    const before = 'Managed a team of 5 engineers.'
    const after = 'Managed a team of 12 engineers.'

    const [row] = buildReplaceRows(before, after)

    expect(row.left?.segments?.filter((s) => s.changed).map((s) => s.text)).toEqual(['5'])
    expect(row.right?.segments?.filter((s) => s.changed).map((s) => s.text)).toEqual(['12'])
  })

  it('round-trips: concatenating every segment reproduces the original text exactly', () => {
    const before = 'Managed a team of 5 engineers across two time zones.'
    const after = 'Led a team of 12 engineers across three time zones.'

    const [row] = buildReplaceRows(before, after)

    expect(row.left?.segments?.map((s) => s.text).join('')).toBe(before)
    expect(row.right?.segments?.map((s) => s.text).join('')).toBe(after)
  })
})

describe('buildSuggestionDiffHunks', () => {
  it('produces an addition-only hunk for an append', () => {
    const hunks = buildSuggestionDiffHunks('Python', 'Python, TypeScript')
    expect(hunks).toEqual([
      {
        rows: [
          { left: { type: 'unchanged', text: 'Python' }, right: { type: 'unchanged', text: 'Python' } },
          { left: null, right: { type: 'added', text: 'TypeScript' } },
        ],
      },
    ])
  })

  it('produces a removal-only hunk for a remove (empty suggested_text)', () => {
    const hunks = buildSuggestionDiffHunks('Irrelevant certification from 2005.', '')
    expect(hunks).toEqual([
      { rows: [{ left: { type: 'removed', text: 'Irrelevant certification from 2005.' }, right: null }] },
    ])
  })

  it('produces an addition-only hunk for an insertion (null current_text)', () => {
    const hunks = buildSuggestionDiffHunks(null, 'Node.js')
    expect(hunks).toEqual([{ rows: [{ left: null, right: { type: 'added', text: 'Node.js' } }] }])
  })

  it('produces a single old-vs-new replace row for an update/replace, word-diffed', () => {
    const hunks = buildSuggestionDiffHunks(
      'Backend engineer with 5 years of experience.',
      'Full-stack engineer with React and Python experience.',
    )
    const [row] = hunks[0].rows

    // Shared words ("engineer", "with", "experience.") must not be
    // highlighted -- only the words that actually differ.
    expect(row.left?.segments?.find((s) => s.text === 'engineer')?.changed).toBe(false)
    expect(row.left?.segments?.find((s) => s.text === 'with')?.changed).toBe(false)
    expect(row.left?.segments?.find((s) => s.text === 'experience.')?.changed).toBe(false)
    expect(row.right?.segments?.find((s) => s.text === 'engineer')?.changed).toBe(false)
    expect(row.right?.segments?.find((s) => s.text === 'with')?.changed).toBe(false)
    expect(row.right?.segments?.find((s) => s.text === 'experience.')?.changed).toBe(false)

    expect(row.left?.segments?.filter((s) => s.changed).map((s) => s.text)).toEqual([
      'Backend',
      '5',
      'years',
      'of',
    ])
    expect(row.right?.segments?.filter((s) => s.changed).map((s) => s.text)).toEqual([
      'Full-stack',
      'React',
      'and',
      'Python',
    ])

    expect(hunks).toEqual([
      {
        rows: [
          {
            left: expect.objectContaining({
              type: 'removed',
              text: 'Backend engineer with 5 years of experience.',
            }),
            right: expect.objectContaining({
              type: 'added',
              text: 'Full-stack engineer with React and Python experience.',
            }),
          },
        ],
      },
    ])
  })

  it('returns no hunks when current and suggested text are identical', () => {
    expect(buildSuggestionDiffHunks('Python', 'Python')).toEqual([])
  })
})
