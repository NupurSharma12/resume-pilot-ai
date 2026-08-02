// A slim, global-style progress indicator (à la GitHub/YouTube's top-of-page
// loading bar) for when we have no real percentage to report — Gemini
// doesn't stream partial progress, so faking a determinate percentage would
// be dishonest. An indeterminate sweep still reads as "actively working."
export default function IndeterminateBar() {
  return (
    <div className="h-1 w-full overflow-hidden bg-indigo-100" role="progressbar" aria-label="Analyzing">
      <div className="h-full w-1/3 animate-indeterminate-sweep rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
    </div>
  )
}
