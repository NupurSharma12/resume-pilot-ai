import { describe, it, expect } from 'vitest'
import {
  buildHunks,
  buildReplaceRows,
  buildSectionDiffs,
  buildSuggestionDiffHunks,
  diffLines,
  splitResumeIntoSections,
} from './resumeSectionDiff'

describe('splitResumeIntoSections', () => {
  it('splits on blank lines, taking the first line of each block as the heading', () => {
    const text = 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython\nDjango\n'

    const sections = splitResumeIntoSections(text)

    expect(sections).toEqual([
      { heading: 'SUMMARY', body: 'Backend engineer.' },
      { heading: 'SKILLS', body: 'Python\nDjango' },
    ])
  })

  it('returns an empty list for empty text', () => {
    expect(splitResumeIntoSections('')).toEqual([])
  })
})

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
    const rows = buildReplaceRows('Backend engineer with 5 years of experience.', 'Full-stack engineer.')
    expect(rows).toEqual([
      {
        left: { type: 'removed', text: 'Backend engineer with 5 years of experience.' },
        right: { type: 'added', text: 'Full-stack engineer.' },
      },
    ])
  })
})

describe('buildHunks', () => {
  it('produces no hunks when nothing changed', () => {
    expect(buildHunks(['Python', 'Django'], ['Python', 'Django'])).toEqual([])
  })

  it('omits unchanged lines far from any change, keeping only a small window of context', () => {
    const before = ['SUMMARY line', 'unrelated 1', 'unrelated 2', 'unrelated 3', 'Python', 'unrelated 4']
    const after = ['SUMMARY line', 'unrelated 1', 'unrelated 2', 'unrelated 3', 'Python, TypeScript', 'unrelated 4']

    const hunks = buildHunks(before, after, 1)

    expect(hunks).toHaveLength(1)
    // Only "unrelated 3" (1 line before) and "unrelated 4" (1 line after)
    // are kept as context -- "SUMMARY line", "unrelated 1", "unrelated 2"
    // never appear anywhere in the output.
    const allText = hunks[0].rows.flatMap((r) => [r.left?.text, r.right?.text]).filter(Boolean)
    expect(allText).not.toContain('SUMMARY line')
    expect(allText).not.toContain('unrelated 1')
    expect(allText).not.toContain('unrelated 2')
    expect(allText).toContain('unrelated 3')
    expect(allText).toContain('unrelated 4')
  })

  it('produces a single coherent hunk for a line that changes in one place', () => {
    const before = ['Python', 'Django']
    const after = ['Python, TypeScript', 'Django']

    const hunks = buildHunks(before, after, 1)

    expect(hunks).toHaveLength(1)
    expect(hunks[0].rows).toEqual([
      { left: { type: 'unchanged', text: 'Python' }, right: { type: 'unchanged', text: 'Python' } },
      { left: null, right: { type: 'added', text: 'TypeScript' } },
      { left: { type: 'unchanged', text: 'Django' }, right: { type: 'unchanged', text: 'Django' } },
    ])
  })

  it('merges two nearby changes separated by a small gap into one hunk', () => {
    const before = ['Python', 'middle', 'Django']
    const after = ['Python, TypeScript', 'middle', 'Django, Flask']

    const hunks = buildHunks(before, after, 1)

    expect(hunks).toHaveLength(1)
    const allText = hunks[0].rows.flatMap((r) => [r.left?.text, r.right?.text])
    expect(allText).toContain('middle')
  })

  it('splits two distant changes into two separate hunks', () => {
    const before = ['Python', 'a', 'b', 'c', 'd', 'e', 'Django']
    const after = ['Python, TypeScript', 'a', 'b', 'c', 'd', 'e', 'Django, Flask']

    const hunks = buildHunks(before, after, 1)

    expect(hunks).toHaveLength(2)
  })
})

describe('buildSectionDiffs', () => {
  const original = 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython\nDjango\n'

  it('flags only the section whose body actually changed', () => {
    const preview = 'SUMMARY\nBackend engineer.\n\nSKILLS\nPython, TypeScript\nDjango\n'

    const diffs = buildSectionDiffs(original, preview)

    expect(diffs.find((d) => d.sectionId === 'SUMMARY')?.isChanged).toBe(false)
    expect(diffs.find((d) => d.sectionId === 'SUMMARY')?.hunks).toEqual([])
    expect(diffs.find((d) => d.sectionId === 'SKILLS')?.isChanged).toBe(true)
  })

  it('gives each section a human-readable, title-cased sectionTitle', () => {
    const diffs = buildSectionDiffs(original, original)
    expect(diffs.find((d) => d.sectionId === 'SUMMARY')?.sectionTitle).toBe('Summary')
  })

  it('reports no changed sections and no hunks when the preview matches the original', () => {
    const diffs = buildSectionDiffs(original, original)
    expect(diffs.every((d) => !d.isChanged && d.hunks.length === 0)).toBe(true)
  })

  it('treats a section with no matching heading in the original as fully added', () => {
    const preview = `${original}\nCERTIFICATIONS\nAWS Certified.\n`

    const diffs = buildSectionDiffs(original, preview)
    const certifications = diffs.find((d) => d.sectionId === 'CERTIFICATIONS')

    expect(certifications?.isChanged).toBe(true)
    expect(certifications?.hunks).toEqual([
      { rows: [{ left: null, right: { type: 'added', text: 'AWS Certified.' } }] },
    ])
  })

  it('produces a combined diff across two changed sections, each independently correct', () => {
    const preview = 'SUMMARY\nFull-stack engineer.\n\nSKILLS\nPython, TypeScript\nDjango\n'

    const diffs = buildSectionDiffs(original, preview)

    const summary = diffs.find((d) => d.sectionId === 'SUMMARY')
    expect(summary?.isChanged).toBe(true)
    expect(summary?.hunks[0].rows).toEqual([
      { left: { type: 'removed', text: 'Backend engineer.' }, right: { type: 'added', text: 'Full-stack engineer.' } },
    ])

    const skills = diffs.find((d) => d.sectionId === 'SKILLS')
    expect(skills?.isChanged).toBe(true)
    expect(skills?.hunks[0].rows[0]).toEqual({
      left: { type: 'unchanged', text: 'Python' },
      right: { type: 'unchanged', text: 'Python' },
    })
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

  it('produces a single old-vs-new replace row for an update/replace', () => {
    const hunks = buildSuggestionDiffHunks(
      'Backend engineer with 5 years of experience.',
      'Full-stack engineer with React and Python experience.',
    )
    expect(hunks).toEqual([
      {
        rows: [
          {
            left: { type: 'removed', text: 'Backend engineer with 5 years of experience.' },
            right: { type: 'added', text: 'Full-stack engineer with React and Python experience.' },
          },
        ],
      },
    ])
  })

  it('returns no hunks when current and suggested text are identical', () => {
    expect(buildSuggestionDiffHunks('Python', 'Python')).toEqual([])
  })
})
