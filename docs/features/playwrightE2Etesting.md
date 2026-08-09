# Browser E2E Golden Journey

Status

Planned

Purpose

This document defines the full browser-level end-to-end test for ResumePilotAI.

The goal is to validate the complete user journey in a real browser from upload to final download, without relying on manual testing.

# Scope

The golden journey should cover:

Resume upload

Job description upload

Resume analysis

Career conversation

Tailoring suggestions

Suggestion selection and deselection

GitHub-style preview

Apply Now

Re-analysis of the updated resume

Final preview

Download of the final resume

Why this matters

ResumePilotAI is a workflow product, not just a set of isolated screens.

Unit tests can confirm individual components and API contracts, but only a browser E2E test can prove that the whole user journey behaves correctly from the user's perspective.

Test goals

The browser test should confirm:

the upload flow works

analysis runs and renders

conversation can be completed

tailoring suggestions are generated

selection and deselection work

preview shows only the selected changes

Apply Now mutates the resume only when explicitly requested

the updated resume can be re-analyzed

the final preview is shown

downloads work at the end of the flow

Recommended scenarios

Golden path

Run the full journey once from start to finish.

Recovery scenarios

Also cover:

refresh during upload

refresh during analysis

refresh during conversation

refresh during tailoring review

stale session recovery

conversation 404 recovery

plan recovery after backend restart

no raw backend error leaking into the UI

Comparator scenarios

Verify the preview and comparator behavior:

changed hunks only

section tabs

read-only preview

side-by-side original/proposed view

selection-driven preview updates

Phased apply scenarios

Verify:

apply a subset of suggestions

applied suggestions become greyed out

continue editing from the updated state

preview the next phase

apply again

refresh and recover state

Download scenarios

Verify:

TXT download

PDF download

DOCX download

Markdown download if available

filenames are sanitized

exported content is readable

Suggested implementation style

Prefer Playwright with:

headed runs for debugging

trace on failure

screenshots on failure

real browser interactions

accessible locators

#Notes

This test should behave like a real user, not like a component test.

The browser test should prove that the current product flow is usable end to end.