Post-Apply Analysis Loop

Status

Implemented

Purpose

This document defines the resume optimization loop that should happen after the user applies tailoring suggestions.

The goal is to re-analyze the updated resume against the same job description and show the user what improved, what regressed, and what still needs work.

Why this matters

ResumePilotAI should not stop after producing a tailored resume.

The product should answer:

Did the changes actually improve the match?

Which requirements are now better covered?

Which gaps still remain?

Did any important capability get weaker?

That is what makes the product feel like an optimization loop instead of a one-shot rewrite tool.

Target flow

Original Resume
    ↓
Initial Analysis
    ↓
Career Conversation
    ↓
Tailoring Suggestions
    ↓
Selected Changes
    ↓
Apply Now
    ↓
Updated Resume
    ↓
Re-Analysis
    ↓
Before / After Comparison
    ↓
Continue Editing or Download

Download is gated on re-analysis

This is enforced by the application, not just a suggested order of steps.

After Apply, the updated resume is shown immediately, but the Download panel does not render at all -- there is no disabled or ghost download button. It only appears once a re-analysis has actually completed for the current final resume and produced a before/after comparison.

While the re-analysis is running, the page shows a section-level "Re-analyzing your updated resume against the job description…" loading state, not just a relabeled button -- a real re-analysis can take well over a minute, and a button-label swap alone is not meaningful progress for a wait that long.

If a re-analysis fails, Download stays unavailable. The applied resume itself is unaffected, and the user can retry "Re-analyze & Compare" (relabeled "Re-analyze Again" once a comparison already exists).

If the user applies again -- including a later phase of Apply on top of an already-applied resume -- the existing comparison is discarded and Download is re-locked until the newly applied resume is re-analyzed. A stale comparison from a previous version of the resume is never allowed to keep Download unlocked.

The left panel's "Overall Match" score follows the same rule: it shows the original pre-tailoring score until a re-analysis completes, then shows the re-analyzed score (with a small "Updated after tailoring & re-analysis" note) instead. The original analysis itself is never overwritten -- it remains the fixed "before" baseline for the lifetime of the session, and the re-analyzed score is tracked and displayed separately.

Inputs

The post-apply analysis should use:

the updated resume after Apply

the same job description

the original analysis baseline

any evidence recovered through Career Conversation

Output

The re-analysis should produce a clear summary such as:

overall match before and after

requirement-by-requirement improvements

remaining missing areas

possible regressions

next recommended edits

UI expectations

The user should see:

a summary of improvement

a comparison against the previous analysis

stronger or weaker requirements

a clear “Continue Tailoring” path

Important principles

1. Compare against the previous analysis

Do not only show a new score in isolation.

The user needs to know what changed.

2. Show strengths and gaps

The output should not only celebrate improvement.

It should also clearly show what is still missing.

3. Detect regressions

If a change improved the summary but weakened technical depth, the user should be able to see that.

4. Support phased editing

This loop should work after each phase of Apply so the user can improve the resume incrementally.

Success criteria

The user should be able to say:

“This change improved my resume.”

“This suggestion helped.”

“I still need to work on these gaps.”

“I want to continue tailoring from here.”

Future extension

Later, this loop can feed into persistent resume version history and interview preparation.