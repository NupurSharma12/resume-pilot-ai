// Deterministic stand-in for the real backend's POST
// /v1/tailoring-suggestions/{plan_id}/apply, used only by the specs that
// seed a fixture plan (see fixtures/session.ts) rather than generating a
// real one -- a seeded `plan_id` was never actually created server-side,
// so a real apply call against it would always 404. Intercepting the
// request client-side (Playwright's standard `page.route`) keeps this
// entirely in the browser layer: no backend code is touched, and the
// real endpoint contract (request/response shape) is respected exactly,
// just answered locally instead of over the network.
import type { Page } from '@playwright/test'
import type {
  ApplySuggestionsResponse,
  TailoringSuggestion,
} from '../../src/data/tailoringSuggestionsTypes'
import { fixtureSuggestions, fixtureTailoringPlan } from '../fixtures/session'

const API_BASE_URL = 'http://localhost:8000'

// Applies whichever ids the frontend actually selected, using each
// suggestion's own `suggested_text` -- an honest (if simplified) stand-in
// for the backend's real composition logic (see app.tailoring.applier),
// good enough to prove the frontend wires the response through correctly
// without re-implementing suggestion application in TypeScript.
function buildApplyResponse(selectedSuggestionIds: string[]): ApplySuggestionsResponse {
  const applied = fixtureSuggestions.filter((s: TailoringSuggestion) =>
    selectedSuggestionIds.includes(s.suggestion_id),
  )
  const has = (id: string) => applied.some((s: TailoringSuggestion) => s.suggestion_id === id)
  const summary = applied.length > 0 ? `Applied ${applied.length} change(s).` : 'No changes applied.'
  return {
    applied_suggestion_ids: selectedSuggestionIds,
    final_resume_text: [
      'SUMMARY',
      'Backend engineer with 5 years of experience.',
      '',
      'SKILLS',
      has('suggestion-0') ? 'Python, TypeScript' : 'Python',
      has('suggestion-1') ? 'Django, Flask' : 'Django',
      '',
      'EXPERIENCE',
      'Built internal tools using Python and Django.',
      ...(has('suggestion-2') ? ['Led a cross-team migration involving 4 engineers.'] : []),
      `(${summary})`,
    ].join('\n'),
    final_validation: { is_valid: true, messages: [] },
  }
}

export async function mockApplyEndpoint(page: Page, planId: string): Promise<void> {
  await page.route(`${API_BASE_URL}/v1/tailoring-suggestions/${planId}/apply`, async (route) => {
    const body = route.request().postDataJSON() as { selected_suggestion_ids: string[] }
    await route.fulfill({ json: buildApplyResponse(body.selected_suggestion_ids) })
  })
}

// Same as `mockApplyEndpoint`, but matches *any* plan id -- needed once a
// stale-plan recovery has regenerated a plan under a new id (see
// `mockGenerateEndpoint`) and the frontend retries apply against it
// automatically, without the test knowing that id in advance.
export async function mockApplyEndpointForAnyPlan(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/v1/tailoring-suggestions/*/apply`, async (route) => {
    const body = route.request().postDataJSON() as { selected_suggestion_ids: string[] }
    await route.fulfill({ json: buildApplyResponse(body.selected_suggestion_ids) })
  })
}

// A single, stateful handler for the whole "apply against a stale plan,
// then recover" round trip -- deliberately one `page.route` registration
// (not two competing ones) so there's no ambiguity about which handler
// Playwright matches first: the *first* apply call against `staleId`
// 404s (simulating the backend having forgotten it -- see
// docs/features/interactive-tailored-resume.md's "Trust boundary"),
// every other call (any other plan id, or a second call against
// `staleId` itself) succeeds normally.
export async function mockStalePlanThenRecover(page: Page, staleId: string): Promise<void> {
  let staleIdHasFailedOnce = false
  await page.route(`${API_BASE_URL}/v1/tailoring-suggestions/*/apply`, async (route) => {
    const url = new URL(route.request().url())
    const requestedPlanId = url.pathname.split('/').at(-2)
    if (requestedPlanId === staleId && !staleIdHasFailedOnce) {
      staleIdHasFailedOnce = true
      await route.fulfill({
        status: 404,
        json: { detail: 'Tailoring suggestion plan not found.' },
      })
      return
    }
    const body = route.request().postDataJSON() as { selected_suggestion_ids: string[] }
    await route.fulfill({ json: buildApplyResponse(body.selected_suggestion_ids) })
  })
}

// Stands in for POST /v1/tailoring-suggestions itself (plan generation) --
// used together with `mockStalePlanThenRecover` to make the *whole*
// stale-plan recovery round trip deterministic (regenerate, remap
// selections, retry apply), rather than only the apply leg of it.
export async function mockGenerateEndpoint(page: Page): Promise<void> {
  await page.route(`${API_BASE_URL}/v1/tailoring-suggestions`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    await route.fulfill({
      json: { ...fixtureTailoringPlan, plan_id: 'e2e-regenerated-plan-1' },
    })
  })
}

// Stands in for GET /v1/career-conversation/{id} -- recovery
// (TailoredResumePage's `recoverFromStalePlan`) re-fetches the Career
// Conversation transcript *before* regenerating a plan, since the
// transcript itself isn't held in session storage (only its session id
// is). A seeded fixture session id was never created server-side, so
// without this the real backend genuinely 404s here too -- a real
// boundary this suite found (see e2e/README.md's "flaky/gap" notes),
// not a bug in the app.
export async function mockCareerConversationGet(page: Page, sessionId: string): Promise<void> {
  await page.route(`${API_BASE_URL}/v1/career-conversation/${sessionId}`, async (route) => {
    await route.fulfill({
      json: {
        session_id: sessionId,
        status: 'complete',
        history: [
          {
            topic: 'Leadership',
            question: 'Tell me about a time you led a project.',
            answer: 'I led a cross-team migration involving 4 engineers.',
            assistant_response: null,
          },
        ],
        current_question: null,
        stop_reason: 'Enough evidence recovered.',
      },
    })
  })
}
