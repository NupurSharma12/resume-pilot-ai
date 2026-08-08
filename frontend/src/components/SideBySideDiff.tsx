import type { DiffCell, DiffHunk } from '../lib/resumeSectionDiff'

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
        {cell.text}
      </div>
    )
  }
  if (cell.type === 'removed') {
    return (
      <div className="bg-rose-50 px-3 py-1 text-rose-700">
        <span className="mr-1.5 select-none text-rose-500">-</span>
        {cell.text}
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
