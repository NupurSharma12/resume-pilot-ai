# Resume session state: why it exists and how it works

## The bug this fixes

`resume`, `jobDescription`, `resumeAnalysis`, and `status` used to live only
in `DashboardLayout`'s `useState`. That survives SPA navigation between
`/`, `/resume`, `/career-conversation`, etc. — `DashboardLayout` sits above
all of them in the route tree, so React Router's `<Outlet>` swaps only the
child, never remounting the layout.

It does **not** survive a full page load: a browser refresh, a typed/
bookmarked URL, a browser back/forward that lands outside the SPA's
history, Vite's dev-only HMR fallback, or a mobile browser reloading a
backgrounded tab. Any of those create a brand new React tree, so
`DashboardLayout`'s `useState` calls re-initialize to `null`/`idle` — even
though the backend's Career Conversation session is untouched and healthy.
`CareerConversationPage` then correctly (by its own logic) falls back to
"Complete a resume analysis first," which reads to the user as being bounced
back to the initial upload screen, despite the backend never having lost
anything. This was confirmed live: see the investigation that preceded this
change (full-page navigation to `/career-conversation` reproduces the reset;
SPA link navigation does not).

## What's owned where

`ResumeSessionProvider` (`frontend/src/session/ResumeSessionContext.tsx`)
now owns every piece of state a page needs to survive a reload, not just the
original four fields this doc was first written for:

- `resume`, `jobDescription`, `resumeAnalysis`, `status`
- `hydrationStatus` (`'pending' | 'hydrated'`)
- `jobPreparationId` — the durable `JobPreparation` this session is
  recorded against on the backend (see
  `docs/persistent-backend-workflow-state.md`); threaded to Career
  Conversation and Tailoring generation so their own durable history
  attaches to the same preparation.
- Career Conversation: `activeCareerConversationSessionId`,
  `careerConversationStatus`
- Interactive Tailoring (`docs/features/interactive-tailored-resume.md`):
  `tailoringPlan`, `tailoringPlanStatus`, `tailoringSelections`,
  `tailoringCustomInstructions`, `tailoringEditedTexts`,
  `finalTailoredResume`, `tailoringValidationReport`,
  `tailoringAvailableExportFormats`, `tailoringSourceFormat`
- Post-Apply Analysis Loop (`docs/features/postapply-analysis-loop.md`):
  `postApplyAnalysis`, `postApplyComparison`, `postApplyAnalysisStatus`

Interview Preparation (`docs/features/interview-preparation-engine.md`)
deliberately owns none of its own state here: the active
`InterviewPreparationPage` reads/writes it straight from the backend, keyed
by `jobPreparationId`, exactly the way History does — see that doc's
"Implementation status" section.

`DashboardLayout` still owns, locally, exactly two things that have no
business surviving a reload: `errorMessage` (an in-flight error's text) and
`isInputCollapsed` (whether a panel is expanded). Losing those on reload is
correct behavior, not a gap.

Pages keep reading everything through `useOutletContext<DashboardOutletContext>()`
exactly as before — `DashboardLayout` composes that context from
`useResumeSession()` plus its own local state, so no page-facing API changed.

## What's persisted, and where

`sessionStorageResumeSessionStorage` (`frontend/src/session/resumeSessionStorage.ts`)
writes one namespaced key, `resumepilot.resumeSession.v1`, to
`window.sessionStorage`. The payload is a versioned envelope
(`PersistedResumeSession`, `frontend/src/session/resumeSessionTypes.ts`) —
abbreviated below; see `RESUME_SESSION_VERSION` in that module for the
exact, current shape and the running history of why each bump happened:

```json
{
  "version": 5,
  "resume": { "text": "...", "fileName": "resume.pdf" },
  "jobDescription": { "text": "...", "fileName": null },
  "resumeAnalysis": { "...": "the full analysis result" },
  "status": "success",
  "activeCareerConversationSessionId": "a1b2c3...",
  "careerConversationStatus": "complete",
  "tailoringPlan": { "...": "the generated suggestion plan, or null" },
  "finalTailoredResume": { "...": "or null" },
  "postApplyComparison": { "...": "or null" },
  "jobPreparationId": "d4e5f6..."
}
```

Every field above is versioned as one unit — a session persisted by a prior
build that's missing a field this version expects fails
`isSupportedPersistedSession` and is discarded wholesale (treated as no
session at all), never partially rehydrated into a shape this version
doesn't expect.

Deliberately **not** persisted: `status: 'loading'` (an in-flight request
can't still be in flight after a reload — normalized to `'idle'` before
writing, see `normalizeStatus`), `errorMessage`, `isInputCollapsed`, any
`AbortController`, and no API keys/prompts/provider config (none of that
ever lived in this state to begin with).

`sessionStorage` (not `localStorage`) is intentional: it's tab-scoped, so a
brand-new tab correctly starts with an empty session instead of inheriting
whatever the user was doing elsewhere.

### Why `sessionStorage` is tactical, not the source of truth

The backend's `ConversationSessionStore` is an in-memory `dict`, explicitly
documented as a Sprint-1 scope boundary — no persistence, no eviction,
lost on restart (`src/app/sessions/conversation_session.py`). `sessionStorage`
on the frontend is the same kind of stopgap: it survives a reload, but not
a backend restart, and not a second device. The moment there's a real
backend-persisted "Analysis Session" (keyed by an id in the URL, fetched by
id instead of rehydrated from browser storage), only
`ResumeSessionStorage`'s implementation needs to change — the interface
(`load` / `save` / `clear`) was kept deliberately small and
framework-independent so `ResumeSessionProvider`, `DashboardLayout`, and
every page can stay exactly as they are.

## Hydration

`ResumeSessionProvider` distinguishes three states, not two:

- **pending** — hasn't looked at storage yet.
- **hydrated with data** — looked, found a valid persisted session.
- **hydrated with no data** — looked, found nothing (or something malformed,
  which is treated the same as nothing — see below).

Only `hydrationStatus === 'pending'` is special: nothing renders the
"complete a resume analysis first" empty state, and nothing (Career
Conversation restore included) fires an API call, until hydration resolves.
Getting this wrong two different ways would each reintroduce a version of
the original bug:

- Rendering the empty state while still pending would flash the wrong
  screen on every reload, even when a completed analysis is about to be
  restored a moment later.
- Persisting state changes *before* hydration finishes would let the
  initial `null`/`idle` values overwrite whatever was already in storage,
  before `storage.load()` got a chance to apply it. The provider's "save"
  effect is gated on `hydrationStatus === 'hydrated'` specifically to
  prevent this.

Malformed, stale-version, or otherwise unsupported stored data is handled
the same way as no data: `resumeSessionStorage.load()` validates the
envelope (version match, a recognized `status`, correctly-typed
`activeCareerConversationSessionId`) and clears the key rather than
returning something the app would have to guess about — the app falls back
to hydrated-with-no-data instead of crashing.

## Restoring an in-progress Career Conversation

The backend already exposed a pure-read endpoint for this —
`GET /v1/career-conversation/{session_id}` (see
`src/app/api/v1/endpoints/career_conversation.py`) — so no new backend
endpoint was needed; the frontend just hadn't called it yet
(`getCareerConversation` in `frontend/src/lib/careerConversationApi.ts`).

`CareerConversationPage`'s `initSession` (replacing the old `startSession`):

1. If `activeCareerConversationSessionId` is set, `GET` that session and
   render it as-is. Never `POST` a new one in this case — that would
   duplicate the first question and silently orphan the user's existing
   answers.
2. If the `GET` 404s (the backend restarted; sessions are in-memory only),
   clear the stale id and show the existing error UI with a retry action,
   rather than silently starting a replacement conversation on the user's
   behalf. The analysis context (`resume`/`jobDescription`/`resumeAnalysis`)
   is untouched, so retrying starts a fresh conversation against the same
   context.
3. If there's no `activeCareerConversationSessionId` at all, `POST` a new
   session as before, and record the returned `session_id` so a later
   reload can restore it.

This runs exactly once per page load — gated by both `hydrationStatus` and
a `hasInitializedRef` guard, the same one-shot pattern already used
elsewhere in this codebase to survive React 18 StrictMode's dev-only double
effect invocation without firing a duplicate request.

## A new analysis resets downstream state

**The bug**: `POST /v1/analyze` always creates a brand-new, unrelated
`JobPreparation` on the backend (see `start_job_preparation`'s own
docstring — "every unrelated new uploaded resume is a new Resume" is a
product rule, not an implementation detail). But `DashboardPage.handleAnalyze`
used to only set `resumeAnalysis`/`jobPreparationId`/`status` on a
successful analysis — every other field this session owns (Career
Conversation id/status, tailoring plan/selections, final tailored resume,
post-apply comparison) was left exactly as it was from whatever the
*previous* analysis had left behind. Sidebar's `CandidateSummaryCard`
reads `postApplyComparison?.score_after ?? resumeAnalysis.overall_assessment.overall_score`
— so a candidate who analyzed one resume/job, applied and re-analyzed it,
then later analyzed a completely different resume/job in the same tab
would see the Sidebar keep showing the *first* job's post-apply score,
not the new analysis's own score, until they happened to apply and
re-analyze the new one too. Confirmed live via a screenshot: History
correctly showed a freshly analyzed 85%-match preparation, while the
Sidebar simultaneously showed 28% "Updated after tailoring & re-analysis"
— the leftover result of a completely different, earlier preparation.

**The fix**: `ResumeSessionContext` exposes `resetForNewAnalysis()`, which
clears every field scoped to "the previous preparation" — Career
Conversation, tailoring, and post-apply state — without touching
`resume`/`jobDescription`/`resumeAnalysis`/`status`/`jobPreparationId`
themselves (those five are what `handleAnalyze` sets to the *new*
analysis's own values immediately afterward). `DashboardPage.handleAnalyze`
calls it right after a successful `analyzeResume()`, before recording the
new result. This is the same "a fresh X invalidates the old Y" pattern
`TailoredResumePage.generate()` already applies to the post-apply subset
whenever a *new tailoring plan* is generated — `resetForNewAnalysis`
applies it one layer up, at the point a *new preparation* begins.

## Tradeoffs

- **Tab-scoped, not cross-device.** A user switching devices, or opening a
  second tab, starts fresh. Acceptable for a Sprint-scoped feature backed
  by an in-memory session store on the backend anyway.
- **Lost on backend restart regardless of frontend persistence.** If the
  backend restarts, `activeCareerConversationSessionId` still points at a
  session that no longer exists — handled gracefully (see above), but the
  conversation itself is genuinely gone, not recoverable from the frontend
  alone. Fixing that requires the backend-persisted session store already
  called out as future work in `conversation_session.py`.
- **One storage key, whole-session granularity.** Simpler than per-field
  keys, at the cost of rewriting the full envelope on every change — fine
  at this data size (a resume, a JD, one analysis result, a few IDs), would
  need reconsidering if the persisted shape grows much larger.
