// Deterministic stand-in for the real backend's POST
// /v1/tailoring-suggestions/{plan_id}/reanalyze (see mockApply.ts's
// identical rationale for /apply) -- a seeded `plan_id` was never
// actually created server-side, so a real reanalyze call against it
// would always 404. Intercepted client-side so the specs that exercise
// the Post-Apply Analysis Loop (see docs/features/postapply-analysis-
// loop.md) stay deterministic and never touch a real LLM provider.
import type { Page } from '@playwright/test'
import type { ReanalyzeResponse } from '../../src/data/postApplyTypes'

const API_BASE_URL = 'http://localhost:8000'

export async function mockReanalyzeEndpoint(
  page: Page,
  planId: string,
  response: ReanalyzeResponse,
  // Optional artificial delay (ms) before fulfilling -- lets a spec
  // deterministically assert the "meaningful progress" loading state
  // (see TailoredResumePage.tsx) actually renders before the response
  // resolves, without racing a real, variable-latency re-analysis call.
  delayMs = 0,
): Promise<void> {
  await page.route(
    `${API_BASE_URL}/v1/tailoring-suggestions/${planId}/reanalyze`,
    async (route) => {
      if (delayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, delayMs))
      }
      await route.fulfill({ json: response })
    },
  )
}

// Simulates a real re-analysis failure (gateway/provider failure, per
// this endpoint's own docs) -- the same shape the backend actually
// returns on an unhandled exception, and the same pattern downloads.spec.ts
// already uses for a failed export.
export async function mockReanalyzeFailure(
  page: Page,
  planId: string,
  detail = 'Re-analysis failed.',
  status = 500,
): Promise<void> {
  await page.route(
    `${API_BASE_URL}/v1/tailoring-suggestions/${planId}/reanalyze`,
    async (route) => {
      await route.fulfill({ status, json: { detail } })
    },
  )
}
