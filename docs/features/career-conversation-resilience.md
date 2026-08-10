# Career Conversation Resilience

Investigation and fixes for three remaining resilience gaps in Career
Conversation: an internal-failure session-corruption bug (500), 409
handling that surfaced as a hard error instead of a recoverable
synchronization event, and a Dashboard CTA "flash" back to the wrong
state on every reload.

---

## 1. The 500: root cause and fix

### Root cause

`CareerConversationWorkflow.submit_answer` (`src/app/workflows/career_conversation_workflow.py`)
used to do this, in order:

```python
session.record_answer(answer)  # mutates session immediately
if session.turn_count >= MAX_CONVERSATION_TURNS:
    session.complete(...)
    return session
await self._advance(session)  # the LLM call -- can fail
return session
```

`record_answer` is not reversible bookkeeping — it moves
`current_question` (plus the answer) into `history` and sets
`current_question = None`, *in place*, on the same mutable
`ConversationSession` object the process-lifetime `ConversationSessionStore`
holds a reference to. If `_advance` then raised for any reason —

- a `pydantic.ValidationError` (the LLM's structured output didn't match
  `ConversationTurnDecision`'s schema),
- a `ConversationTurnInconsistentError` (a structurally valid decision
  that still violates the should_stop/question invariant — e.g.
  `should_stop=false` with a null `question`),
- a `GatewayChainExhaustedError` (every configured LLM provider failed),

— the session was left with the answer already consumed and *no*
replacement question, and never marked complete either: `status:
"in_progress"`, `current_question: null`. That state has no way out
through the API. Every future answer attempt hits
`submit_career_conversation_answer`'s own guard (`current_question is
None`) and returns `409`, forever, for a session that was never actually
finished — the conversation is bricked, and the candidate's last answer
is gone.

The endpoint's `except Exception: raise` (unchanged, and correct — see
§2) does propagate this as an HTTP `500`, but the real bug is what the
500 leaves behind, not the status code itself.

### Fix

`submit_answer` now only mutates `session` *after* the next turn's
decision has already been requested and validated successfully. The
prompt for that request is built from a **prospective** history —
`session.history` plus one synthetic exchange representing the
not-yet-recorded answer — precisely so the LLM call can happen before
anything is committed:

```python
async def submit_answer(self, session, answer):
    if session.current_question is None:
        raise ValueError("No open question to answer.")
    if session.turn_count + 1 >= MAX_CONVERSATION_TURNS:
        session.record_answer(answer)  # no I/O below this branch --
        session.complete(reason=...)  # nothing here can fail
        return session

    decision = await self._request_decision(session, pending_answer=answer)
    # Only reached once the LLM call has already succeeded.
    session.record_answer(answer)
    self._apply_decision(session, decision)
    return session
```

`_request_decision` never touches `session`. If it raises, `session` is
returned to the caller (via the exception) exactly as it was passed in —
same `current_question`, same `history`, same `status`. A failed request
is now indistinguishable, from the session's point of view, from a
request that was never made.

### Design decision: still a 500, deliberately

Goal 1 asked for "recoverable errors instead of breaking the
experience." The fix that actually delivers that is entirely about *what
the session looks like afterward*, not about inventing a new HTTP status
code for this case. `analyze.py` and `tailor_resume.py` both already
follow the same convention — log, re-raise unchanged, let FastAPI's
default handler produce a `500` — and `career_conversation.py` keeps
doing the same thing here. Once the session can no longer be corrupted
by this failure, the existing "recoverable" mechanism the frontend
already had is sufficient: `CareerConversationPage`'s error state doesn't
clear the typed answer on failure, and "Try Again" resubmits it — which,
against a session that never lost its open question, now genuinely
succeeds instead of hitting a 409 wall.

### Tradeoff

The extra "prospective history" construction in `_request_decision`
means a rejected turn's prompt-building work (formatting history, calling
the prompt builder) happens twice if the caller retries — cheap
(string formatting, no I/O) compared to the LLM call itself, so not worth
optimizing away.

---

## 2. 409 Conflict: every scenario, and frontend auto-recovery

### Every scenario producing a 409

Exhaustively confirmed via `grep -rn "HTTPException" src/app/api/v1/endpoints/`
— there are exactly two, both in
`submit_career_conversation_answer` (`career_conversation.py`), and no
409s anywhere else in the API:

1. **Fast-path**: `session.status == COMPLETE`, checked before the lock
   is even acquired (avoids lock contention and a wasted LLM call for the
   common case of retrying against a session everyone already knows is
   done).
2. **In-lock recheck**: `session.status == COMPLETE or session.current_question is None`,
   checked again *inside* `session.lock`. This is the one that matters
   for correctness — two concurrent requests can both pass check #1
   before either finishes, then queue on the lock; without this recheck,
   the second to acquire the lock would call the workflow against a
   session the first one just finished mutating (e.g. `current_question`
   now `None` because the first request's turn just completed it).

Both were already correctly implemented and already had regression tests
(`test_answer_after_completion_returns_409`,
`test_concurrent_answers_for_same_question_return_409_not_500`) before
this investigation — no backend changes were needed for enumeration or
correctness. What was missing was the **frontend's** response to seeing
a 409 at all.

### Frontend: 409 is a synchronization event, not a failure

`submitCareerConversationAnswer` (`frontend/src/lib/careerConversationApi.ts`)
now classifies a 409 with `cause: 'conflict'` on the thrown `ApiError`,
mirroring the existing `cause: 'not_found'` pattern already used for a
404 on `getCareerConversation`.

`CareerConversationPage.handleSubmitAnswer` catches that specifically:

```ts
if (err instanceof ApiError && err.cause === 'conflict') {
  try {
    const latest = await getCareerConversation(session.session_id)
    setSession(latest)
    setCareerConversationStatus(latest.status)
    setAnswer('')
    setApiStatus('ready')
    return
  } catch {
    // refetch itself failed -- fall through to the normal error path
  }
}
```

A 409 here *by construction* means the session is fine — every scenario
above is "this specific answer doesn't apply anymore," never "something
broke." So instead of showing `ConversationErrorState` (which the user
would have to notice and dismiss), the page refetches the session's
authoritative current state via the same pure-read `GET` endpoint already
used for reload-safety, and resumes from there — showing whatever
question (or completion) is actually current. Only if the refetch
*itself* fails does it fall back to the normal error state, since at that
point there's nothing left to recover with automatically.

### Design decision: reuse `GET`, don't invent a merge/replay mechanism

The alternative would be trying to reconcile the stale in-memory `session`
with whatever caused the conflict (e.g. guessing whether the answer
"still applies" to a new question). `GET /v1/career-conversation/{id}` is
already the documented, safe, side-effect-free source of truth for "what
does this session actually look like right now" — reusing it here instead
of building new reconciliation logic keeps this fix small and consistent
with how reload-recovery already works everywhere else in this feature.

---

## 3. Missing CTA after refresh: root cause and fix

### Root cause

`ResumeSessionProvider`'s hydration is asynchronous — a `useEffect` that
reads and parses `sessionStorage` after the first render, not before it.
Every page that reads session state sees `null`/`idle`/empty values for
one render before hydration resolves. `CareerConversationPage` and
`TailoredResumePage` already guarded against this individually (an
explicit `hydrationStatus !== 'hydrated'` check before rendering anything
that depends on the restored data). `DashboardLayout` — which every other
route (`/`, `/resume`, `/job-description`, `/history`, `/settings`) renders
through — had no such guard at all:

```tsx
// before
export default function DashboardLayout() {
  const { resumeAnalysis, resume, jobDescription, status, ... } = useResumeSession()
  // no hydrationStatus check
  return (
    <div>
      <Sidebar resumeAnalysis={resumeAnalysis} />
      <main><Outlet context={{ resumeAnalysis, resume, jobDescription, status, ... }} /></main>
    </div>
  )
}
```

Immediately after a full reload, `resumeAnalysis` is `null` and `status`
is `idle` for that first render, so `DashboardPage`'s `hasResult = status
=== 'success' && resumeAnalysis !== null` is `false` — the Dashboard
paints its empty upload screen, with **no** `CareerConversationBanner`
and **no** `TailoredResumeBanner` at all (both are conditionally
rendered), and the Sidebar shows no candidate summary and a disabled
"Tailored Resume" link — before flipping, one render later, to the
correct, already-persisted state. That flip is the "missing CTA after
refresh": every Dashboard CTA is briefly, genuinely absent, not just
displaying a wrong label.

### Fix

`DashboardLayout` now gates its entire render on `hydrationStatus`,
centrally, once:

```tsx
if (hydrationStatus !== 'hydrated') {
  return <FullPageLoadingState /> // "Restoring your session…"
}
return (
  <div>
    <Sidebar resumeAnalysis={resumeAnalysis} />
    <main><Outlet context={{ ... }} /></main>
  </div>
)
```

### Design decision: fix it once, centrally — not per-page

`CareerConversationPage`/`TailoredResumePage`'s existing gates are the
established pattern for this codebase, and the "quick fix" would have
been to copy that same guard into `DashboardPage`, `ResumePage`, and
`JobDescriptionPage` individually. That was rejected: it's the same bug
repeated three more times, not a fix for the bug's actual source, and
every future route added under `DashboardLayout` would need to remember
to add it too. `DashboardLayout` is the single place that already owns
composing `ResumeSessionProvider`'s data into what every child page
reads (directly via `useResumeSession()`, or indirectly via its Outlet
context) — gating there closes the gap for every current and future
child page at once. `CareerConversationPage`/`TailoredResumePage`'s own
gates were deliberately left in place rather than removed: harmless
defense in depth, and what keeps them correct if ever rendered outside
this layout (as several of their own tests already do, by design).

This also directly satisfies "verify all Dashboard actions (Resume
Analysis, Career Conversation, Tailored Resume) are restored correctly
after reload" — all three now hydrate from the exact same gate, at the
exact same moment, so there's no window where one is restored and
another isn't.

### Tradeoff

Every route under `DashboardLayout` now shows a brief "Restoring your
session…" full-page state on first load and on every hard reload, even
for a user with no prior session at all (hydration still has to resolve
to *discover* there's nothing to restore). In practice this is a single
synchronous `sessionStorage.getItem` + `JSON.parse`, effectively
imperceptible — but it is a real, if tiny, cost paid on every load in
exchange for never showing incorrect state.

---

## Files changed

**Backend**
- `src/app/workflows/career_conversation_workflow.py` — restructured
  `submit_answer`/`start_conversation` around `_request_decision`
  (non-mutating) / `_apply_decision` (mutating, only called after success)
- `tests/test_career_conversation_workflow.py` — `FakeGateway` extended to
  raise a queued exception instead of only returning decisions; 4 new
  regression tests
- `tests/test_career_conversation_api.py` — 1 new end-to-end test through
  the real HTTP layer

**Frontend**
- `frontend/src/lib/careerConversationApi.ts` — `submitCareerConversationAnswer`
  classifies a 409 with `cause: 'conflict'`
- `frontend/src/pages/CareerConversationPage.tsx` — `handleSubmitAnswer`
  auto-recovers on `cause: 'conflict'` via `getCareerConversation`
- `frontend/src/pages/CareerConversationPage.test.tsx` — 4 new tests
- `frontend/src/layouts/DashboardLayout.tsx` — hydration-gated render
- `frontend/src/layouts/DashboardLayout.test.tsx` — new file, 4 tests

No backend workflow/API endpoints were added, removed, or renamed; no
change to `ConversationSession`'s public methods; no change to the
Evidence-Based Tailoring Engine. Frontend/backend state separation is
unchanged: the backend still has no idea the frontend persists anything,
and the frontend still treats every backend response as the source of
truth, never assuming its cached copy is correct without a `GET` to
confirm it (goal 2's recovery path *is* exactly that confirmation step).

## Verification performed

- Backend: `pytest` — **131/131 passed** (18 new/changed across the two
  test files above); `ruff check .` / `ruff format --check .` clean.
- Frontend: `vitest run` — **62/62 passed** (12 new); `tsc -b` clean;
  `npm run lint` clean (one pre-existing, unrelated warning); `npm run
  build` clean.
- Live, against the real running dev servers (not the test harness):
  - A standalone script drove the real FastAPI app (real workflow, real
    session store, only the LLM call faked) through: turn 1 succeeds,
    turn 2's LLM call fails → `500` → a `GET` immediately after shows the
    session byte-for-byte unchanged (same open question, empty history,
    still `in_progress`) → resubmitting the same answer succeeds
    normally with exactly one recorded exchange.
  - A Playwright run against the real frontend + real backend: completed
    a full Career Conversation via the UI, then fired a raw `fetch()` at
    the real running backend to answer the now-complete session directly
    — confirmed a live `409` (not `500`), and confirmed the rejected
    answer never entered history. Then reloaded on the Dashboard and
    confirmed Resume Analysis results, the Sidebar's "Tailored Resume"
    link, and the Dashboard banner's CTA label were all correctly
    restored in the same render pass; revisiting the Tailored Resume page
    via the sidebar afterward showed the cached result immediately with
    no regeneration request fired.

## Remaining observations

- The frontend's 409 auto-recovery is unit-tested with real `ApiError`
  objects flowing through the real `handleSubmitAnswer` code path, and
  the backend's 409 production is both unit- and live-tested — but a
  true two-client concurrent race was not reproduced through the actual
  browser UI end-to-end in this pass. An earlier attempt at this (firing
  two real concurrent answers against a real LLM) turned out to be
  non-deterministic for reasons unrelated to the fix: a real model's
  `should_stop` decision determines whether two racing "continue"-style
  answers collide into a 409 at all, or simply land as two valid
  sequential turns. The deterministic backend test
  (`test_concurrent_answers_for_same_question_return_409_not_500`, driven
  by a scripted fake gateway) remains the reliable reproduction for that
  specific interleaving.
- `DashboardLayout`'s hydration gate adds a brief full-page loading state
  on every load, including for first-time visitors with nothing to
  restore — see the tradeoff note in §3.
