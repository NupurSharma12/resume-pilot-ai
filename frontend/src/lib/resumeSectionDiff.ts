// Frontend-only, best-effort resume section splitting and hunk diffing for
// the Preview Changes stage (see TailoringPreviewPanel/TailoringSuggestionCard).
// Deliberately not a port of the backend's `ResumeStructureParser` -- there
// is no API that returns a previewed resume's structure, only its plain
// assembled text (`ApplySuggestionsResponse.final_resume_text`), so section
// boundaries have to be re-derived heuristically here, purely for *display*
// grouping. If this heuristic misjudges a boundary, the worst case is a
// slightly odd section split in the preview UI -- it never affects what
// actually gets applied, which is always the backend's own structured
// result. Everything here diffs real before/after text; nothing is ever
// fabricated from a suggestion's `reason` or other metadata.

import { prettifyHeading } from './suggestionPresentation'

export interface ResumeTextSection {
  heading: string
  body: string
}

// Sections in this app's resumes are separated by a blank line, with the
// section heading as the first line of each block -- the same shape every
// resume fixture in this codebase already uses (see testFixtures.ts /
// backend test fixtures' `_RESUME_TEXT`). A block with no blank-line
// separation from the rest of the document is still its own section here;
// nothing is merged.
export function splitResumeIntoSections(text: string): ResumeTextSection[] {
  const blocks = text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block.length > 0)

  return blocks.map((block) => {
    const lines = block.split('\n')
    const [heading, ...rest] = lines
    return { heading: heading.trim(), body: rest.join('\n').trim() }
  })
}

export type DiffLineType = 'unchanged' | 'added' | 'removed'

export interface DiffLine {
  type: DiffLineType
  text: string
}

// A standard LCS-based line diff -- resume section bodies are small enough
// (typically well under a hundred lines) that the O(n*m) dynamic-programming
// table is trivial, so there's no need for a more elaborate algorithm.
export function diffLines(before: string[], after: string[]): DiffLine[] {
  const n = before.length
  const m = after.length
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))

  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] =
        before[i] === after[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const result: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (before[i] === after[j]) {
      result.push({ type: 'unchanged', text: before[i] })
      i += 1
      j += 1
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: 'removed', text: before[i] })
      i += 1
    } else {
      result.push({ type: 'added', text: after[j] })
      j += 1
    }
  }
  while (i < n) {
    result.push({ type: 'removed', text: before[i] })
    i += 1
  }
  while (j < m) {
    result.push({ type: 'added', text: after[j] })
    j += 1
  }
  return result
}

// ---------------------------------------------------------------------------
// Hunk model -- a GitHub-style side-by-side diff: two cells per row (one per
// column), either of which may be `null` (nothing to show on that side, e.g.
// a pure addition has no left cell). Only changed regions plus a little
// surrounding context ever become a hunk -- unrelated unchanged content
// between hunks is simply never included, never rendered as a giant
// unchanged block (see `buildHunks`'s context-window logic).
// ---------------------------------------------------------------------------

export interface DiffCell {
  type: DiffLineType
  text: string
}

export interface DiffRow {
  left: DiffCell | null
  right: DiffCell | null
}

export interface DiffHunk {
  rows: DiffRow[]
}

export interface DiffSection {
  sectionId: string
  sectionTitle: string
  hunks: DiffHunk[]
  isChanged: boolean
}

function stripLeadingPunctuation(text: string): string {
  return text.replace(/^[,;:\s]+/, '')
}

// The one place this module decides how to *pair* one "old" unit of text
// against one "new" unit of text -- used both for a single paired
// remove/add row inside a bigger section hunk, and (via
// `buildSuggestionDiffHunks`) for a single suggestion's own current/
// suggested text. Never guesses beyond a literal substring relationship in
// the actual text:
//
// - Identical text -> one unchanged row (nothing to show as a change).
// - Old text empty -> a pure addition (matches `insert_before`/
//   `insert_after`, whose `current_text` is always null): one row, added
//   on the right only.
// - New text empty -> a pure removal (matches `remove`, whose
//   `suggested_text` is always empty): one row, removed on the left only.
// - New text starts with the old text verbatim -- the exact shape an
//   `append` suggestion's contract guarantees (`suggested_text` always
//   contains `current_text` as a substring) -- the common prefix is shown
//   once, as unchanged context on *both* sides, and only the genuinely new
//   suffix appears as its own added-only row. This is what turns "Python"
//   -> "Python, TypeScript" into "unchanged: Python" + "added: TypeScript"
//   instead of a misleading full-line replace.
// - Anything else is a genuine replacement (`update`/`replace`/
//   `add_emphasis`, or a section-level pairing with no simple prefix
//   relationship): one row, the old text removed on the left and the new
//   text added on the right, aligned in the same row.
export function buildReplaceRows(oldText: string, newText: string): DiffRow[] {
  if (oldText === newText) {
    return [{ left: { type: 'unchanged', text: oldText }, right: { type: 'unchanged', text: newText } }]
  }
  if (oldText.length === 0) {
    return [{ left: null, right: { type: 'added', text: newText } }]
  }
  if (newText.length === 0) {
    return [{ left: { type: 'removed', text: oldText }, right: null }]
  }
  if (newText.startsWith(oldText)) {
    const suffix = stripLeadingPunctuation(newText.slice(oldText.length)).trim()
    const rows: DiffRow[] = [
      { left: { type: 'unchanged', text: oldText }, right: { type: 'unchanged', text: oldText } },
    ]
    if (suffix.length > 0) {
      rows.push({ left: null, right: { type: 'added', text: suffix } })
    }
    return rows
  }
  return [{ left: { type: 'removed', text: oldText }, right: { type: 'added', text: newText } }]
}

type Segment =
  | { kind: 'unchanged'; lines: string[] }
  | { kind: 'change'; removed: string[]; added: string[] }

// Regroups a flat line diff into alternating runs of unchanged lines and
// "change blocks" (a maximal run of only removed/added lines) -- the
// intermediate shape `buildHunks` walks to decide what becomes context vs.
// what starts a new hunk.
function toSegments(flat: DiffLine[]): Segment[] {
  const segments: Segment[] = []
  let i = 0
  while (i < flat.length) {
    if (flat[i].type === 'unchanged') {
      const lines: string[] = []
      while (i < flat.length && flat[i].type === 'unchanged') {
        lines.push(flat[i].text)
        i += 1
      }
      segments.push({ kind: 'unchanged', lines })
    } else {
      const removed: string[] = []
      const added: string[] = []
      while (i < flat.length && flat[i].type !== 'unchanged') {
        if (flat[i].type === 'removed') removed.push(flat[i].text)
        else added.push(flat[i].text)
        i += 1
      }
      segments.push({ kind: 'change', removed, added })
    }
  }
  return segments
}

function contextRow(line: string): DiffRow {
  return { left: { type: 'unchanged', text: line }, right: { type: 'unchanged', text: line } }
}

// Builds the hunks for one before/after pair of line arrays: every changed
// line, paired with its counterpart via `buildReplaceRows` where one exists,
// plus up to `contextSize` unchanged lines immediately before/after each
// change -- exactly the "git diff -U<n>" convention. Two change blocks
// separated by an unchanged gap no bigger than `2 * contextSize` are merged
// into a single hunk (the gap becomes context in the middle) rather than
// shown as two separate hunks with redundant, overlapping context. Any
// unchanged line further than `contextSize` away from a change is never
// included at all -- this is what keeps a hunk from ever growing into "the
// whole section."
export function buildHunks(before: string[], after: string[], contextSize = 1): DiffHunk[] {
  const segments = toSegments(diffLines(before, after))
  const hunks: DiffHunk[] = []
  let current: DiffRow[] | null = null

  for (let s = 0; s < segments.length; s++) {
    const seg = segments[s]
    if (seg.kind === 'change') {
      if (current === null) {
        current = []
        const prev = segments[s - 1]
        if (prev?.kind === 'unchanged') {
          for (const line of prev.lines.slice(-contextSize)) current.push(contextRow(line))
        }
      }
      const maxLen = Math.max(seg.removed.length, seg.added.length)
      for (let k = 0; k < maxLen; k++) {
        const oldLine = seg.removed[k]
        const newLine = seg.added[k]
        if (oldLine !== undefined && newLine !== undefined) {
          current.push(...buildReplaceRows(oldLine, newLine))
        } else if (oldLine !== undefined) {
          current.push({ left: { type: 'removed', text: oldLine }, right: null })
        } else if (newLine !== undefined) {
          current.push({ left: null, right: { type: 'added', text: newLine } })
        }
      }
    } else {
      const nextIsChange = s < segments.length - 1 && segments[s + 1].kind === 'change'
      if (current !== null && nextIsChange && seg.lines.length <= contextSize * 2) {
        // Small gap between two change blocks -- keep it as context inside
        // the same hunk instead of splitting into two.
        for (const line of seg.lines) current.push(contextRow(line))
      } else if (current !== null) {
        for (const line of seg.lines.slice(0, contextSize)) current.push(contextRow(line))
        hunks.push({ rows: current })
        current = null
      }
      // An unchanged run with no open hunk (nothing changed yet, or too far
      // from the previous change to matter) contributes nothing -- exactly
      // the "don't render the whole resume" requirement.
    }
  }
  if (current !== null) hunks.push({ rows: current })
  return hunks
}

// Builds one section-by-section, GitHub-style hunk diff between the resume
// text the candidate started with and a previewed (not-yet-committed)
// `final_resume_text`. Sections are matched by heading text -- suggestions
// only ever target *items* within a section, never a section's own heading
// line, so a section's heading is stable across every operation this engine
// supports (append/insert/update/replace/remove/add_emphasis); a preview
// section with no heading match in the original is treated as fully added.
export function buildSectionDiffs(
  originalText: string,
  previewText: string,
  contextSize = 1,
): DiffSection[] {
  const originalSections = splitResumeIntoSections(originalText)
  const previewSections = splitResumeIntoSections(previewText)
  const originalBodyByHeading = new Map(originalSections.map((s) => [s.heading, s.body]))

  return previewSections.map((section) => {
    const beforeBody = originalBodyByHeading.get(section.heading) ?? ''
    const beforeLines = beforeBody.length > 0 ? beforeBody.split('\n') : []
    const afterLines = section.body.length > 0 ? section.body.split('\n') : []
    return {
      sectionId: section.heading,
      sectionTitle: prettifyHeading(section.heading),
      hunks: buildHunks(beforeLines, afterLines, contextSize),
      isChanged: beforeBody.trim() !== section.body.trim(),
    }
  })
}

// Builds the hunks for a *single* suggestion's own current/suggested text --
// used by the per-card "Preview Change" comparator (`TailoringSuggestionCard`),
// driven directly by that one suggestion regardless of the current
// selection. `currentText` is `null` for `insert_before`/`insert_after`
// (no existing text to compare against -- a pure addition); `suggestedText`
// is always empty for `remove`. Both are handled by `buildReplaceRows`
// without needing the operation itself as an input -- the actual text
// already implies the right shape.
export function buildSuggestionDiffHunks(
  currentText: string | null,
  suggestedText: string,
): DiffHunk[] {
  const before = currentText ?? ''
  const after = suggestedText
  if (before === after) return []
  return [{ rows: buildReplaceRows(before, after) }]
}
