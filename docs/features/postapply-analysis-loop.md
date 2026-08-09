Post-Apply Analysis Loop

Status

Planned

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