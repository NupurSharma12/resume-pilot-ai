import type { DiffCell, DiffHunk, DiffSegment } from '../lib/resumeSectionDiff'

// Renders a modified cell's `segments` -- unchanged words plain, changed
// words wrapped in `<mark>` with a stronger highlight than the cell's own
// background -- so within a "genuine replacement" row, only the words that
// actually differ stand out, GitHub-inline-diff-style. Only used when
// `segments` is present (see `DiffCell`'s docstring); an unchanged/pure-
// addition/pure-removal cell has nothing partial to highlight and renders
// its plain `text` instead (see `DiffCellView` below).
function DiffSegments({
  segments,
  markClassName,
}: {
  segments: DiffSegment[]
  markClassName: string
}) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.changed ? (
          <mark key={index} className={markClassName}>
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  )
}

// One cell of one diff row -- `null` means "nothing on this side" (a pure
// addition has no left cell, a pure removal has no right cell), rendered as
// an empty, unobtrusive placeholder rather than left blank/misaligned.
function DiffCellView({ cell }: { cell: DiffCell | null }) {
  if (!cell) {
    return <div className="bg-gray-50/60 px-3 py-1" aria-hidden="true" />
  }
  if (cell.type === 'added') {
    return (
      <div className="bg-emerald-50 px-3 py-1 text-emerald-800">
        <span className="mr-1.5 select-none text-emerald-500">+</span>
        {cell.segments ? (
          <DiffSegments
            segments={cell.segments}
            markClassName="rounded-sm bg-emerald-200 font-semibold text-emerald-900"
          />
        ) : (
          cell.text
        )}
      </div>
    )
  }
  if (cell.type === 'removed') {
    return (
      <div className="bg-rose-50 px-3 py-1 text-rose-700">
        <span className="mr-1.5 select-none text-rose-500">-</span>
        {cell.segments ? (
          <DiffSegments
            segments={cell.segments}
            markClassName="rounded-sm bg-rose-200 font-semibold text-rose-900 line-through decoration-rose-500"
          />
        ) : (
          cell.text
        )}
      </div>
    )
  }
  return (
    <div className="bg-white px-3 py-1 text-gray-600">
      <span className="mr-1.5 select-none text-gray-300">·</span>
      {cell.text}
    </div>
  )
}

interface SideBySideDiffProps {
  hunks: DiffHunk[]
  emptyMessage?: string
}

// A read-only, code-review-style side-by-side comparator: two equal-width
// columns (Original / Proposed), only the changed hunks (plus a little
// surrounding context -- see `buildHunks`), never the whole resume/section.
// Shared by the per-suggestion "Preview Change" panel (one suggestion's own
// current vs. suggested text) and the combined multi-suggestion "Preview
// Changes" panel (a whole section's hunks) -- both hand this component the
// exact same `DiffHunk[]` shape, so the visual language never diverges
// between "preview one" and "preview everything selected."
export default function SideBySideDiff({ hunks, emptyMessage }: SideBySideDiffProps) {
  if (hunks.length === 0) {
    return <p className="text-sm text-gray-500">{emptyMessage ?? 'No changes to preview.'}</p>
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 font-mono text-[13px] leading-5">
      <div className="grid grid-cols-2 divide-x divide-gray-200 border-b border-gray-200 bg-gray-50 font-sans text-[11px] font-semibold tracking-wide text-gray-500 uppercase">
        <div className="px-3 py-1.5">Original</div>
        <div className="px-3 py-1.5">Proposed</div>
      </div>
      {hunks.map((hunk, hunkIndex) => (
        <div
          key={hunkIndex}
          className={hunkIndex > 0 ? 'border-t border-dashed border-gray-200' : undefined}
        >
          {hunk.rows.map((row, rowIndex) => (
            <div key={rowIndex} className="grid grid-cols-2 divide-x divide-gray-200">
              <DiffCellView cell={row.left} />
              <DiffCellView cell={row.right} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
