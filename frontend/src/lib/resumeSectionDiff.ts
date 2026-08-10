// Frontend-only diffing for the Preview Changes stage (see
// TailoringPreviewPanel/TailoringSuggestionCard). Diffs a single
// suggestion's own `current_text` against its `suggested_text`/edited
// text -- both exact, backend-tracked values -- never the assembled
// original resume text against the assembled final resume text. An
// earlier version of this module tried to diff those two whole documents
// directly, matching sections by heading text; that turned out to be
// fragile in practice (a resume whose original text didn't line up with
// the backend's re-rendering -- e.g. line breaks lost during PDF/DOCX
// extraction -- made every section look "fully added," with no original
// content shown at all). Building the diff from suggestions instead
// sidesteps whole-document reconciliation entirely: nothing here is ever
// fabricated from a suggestion's `reason` or other metadata, and nothing
// depends on the surrounding document's formatting.

export type DiffLineType = 'unchanged' | 'added' | 'removed'

export interface DiffLine {
  type: DiffLineType
  text: string
}

// A standard LCS-based diff over an array of tokens (lines, in the
// original design; words, via `buildWordLevelReplaceCells` below) --
// small enough inputs (a resume line, or a word-tokenized sentence) that
// the O(n*m) dynamic-programming table is trivial, so there's no need for
// a more elaborate algorithm.
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
// a pure addition has no left cell).
// ---------------------------------------------------------------------------

// One token-sized slice of a modified line's text -- `changed: true` marks
// exactly the words that differ from the other side, `changed: false` marks
// shared context (e.g. a common prefix/suffix) within that same line. Only
// present on a `DiffCell` for the two-sided "genuine replacement" case (see
// `buildReplaceRows`); absent for unchanged/pure-addition/pure-removal
// cells, which have nothing partial to highlight -- the cell's `text` is
// either entirely context or entirely new/removed already.
export interface DiffSegment {
  text: string
  changed: boolean
}

export interface DiffCell {
  type: DiffLineType
  text: string
  segments?: DiffSegment[]
}

export interface DiffRow {
  left: DiffCell | null
  right: DiffCell | null
}

export interface DiffHunk {
  rows: DiffRow[]
}

function stripLeadingPunctuation(text: string): string {
  return text.replace(/^[,;:\s]+/, '')
}

// Splits text into words and whitespace runs as separate tokens (e.g.
// "Senior Software" -> ["Senior", " ", "Software"]), preserving exact
// spacing when segments are rejoined for display. Word-level, not
// character-level: GitHub's own inline diff highlighting works the same
// way -- it reads far more cleanly for prose than a character-by-character
// highlight would (e.g. "years" -> "year" would highlight only the "s"
// character-level, but reads better as the whole word changing).
function tokenizeWords(text: string): string[] {
  return text.match(/\S+|\s+/g) ?? []
}

// Word-level diff for one pair of lines that are known to differ but share
// no simple prefix relationship (see `buildReplaceRows` below) -- the same
// LCS algorithm as `diffLines`, just applied to word tokens instead of
// whole lines, so a minimal, order-preserving alignment of shared words
// falls out for free rather than needing a second algorithm. Returns the
// two sides' segments in original left-to-right order, with a token only
// ever marked `changed` on the side(s) it isn't shared with.
function buildWordLevelReplaceCells(oldText: string, newText: string): { left: DiffCell; right: DiffCell } {
  const tokenDiff = diffLines(tokenizeWords(oldText), tokenizeWords(newText))
  const leftSegments: DiffSegment[] = []
  const rightSegments: DiffSegment[] = []
  for (const token of tokenDiff) {
    if (token.type === 'unchanged') {
      leftSegments.push({ text: token.text, changed: false })
      rightSegments.push({ text: token.text, changed: false })
    } else if (token.type === 'removed') {
      leftSegments.push({ text: token.text, changed: true })
    } else {
      rightSegments.push({ text: token.text, changed: true })
    }
  }
  return {
    left: { type: 'removed', text: oldText, segments: leftSegments },
    right: { type: 'added', text: newText, segments: rightSegments },
  }
}

// The one place this module decides how to *pair* one "old" unit of text
// against one "new" unit of text -- used by `buildSuggestionDiffHunks` for
// a single suggestion's own current/suggested text. Never guesses beyond a
// literal substring relationship in the actual text:
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
//   `add_emphasis`): one row, the old text removed on the left and the new
//   text added on the right, aligned in the same row -- but word-diffed
//   (`buildWordLevelReplaceCells`) rather than opaque: shared words (e.g. an
//   unrelated word inserted mid-sentence, or one word swapped for another)
//   carry `segments` marking only the actually-different words as changed,
//   so a one-phrase edit inside a long sentence never reads as though the
//   whole sentence was rewritten.
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
  const { left, right } = buildWordLevelReplaceCells(oldText, newText)
  return [{ left, right }]
}

// Builds the hunks for a *single* suggestion's own current/suggested text --
// used both by the per-card "Preview Change" comparator
// (`TailoringSuggestionCard`, driven directly by that one suggestion
// regardless of the current selection) and by the combined "Preview
// Changes" panel (`TailoringPreviewPanel`, one call per included
// suggestion, grouped by section -- see that component's own docstring).
// `currentText` is `null` for `insert_before`/`insert_after` (no existing
// text to compare against -- a pure addition); `suggestedText` is always
// empty for `remove`. Both are handled by `buildReplaceRows` without
// needing the operation itself as an input -- the actual text already
// implies the right shape.
export function buildSuggestionDiffHunks(
  currentText: string | null,
  suggestedText: string,
): DiffHunk[] {
  const before = currentText ?? ''
  const after = suggestedText
  if (before === after) return []
  return [{ rows: buildReplaceRows(before, after) }]
}
