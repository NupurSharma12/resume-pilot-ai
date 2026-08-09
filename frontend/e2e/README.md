# Browser E2E suite (Playwright)

A real-browser layer on top of the vitest unit suite (`src/**/*.test.tsx`) —
drives the actual running frontend + backend over HTTP/DOM, the way a real
user would, rather than importing React components directly.

## Running

```bash
npm run test:e2e            # headless, all specs
npm run test:e2e:headed     # watch it run
npm run test:e2e:ui         # Playwright's interactive UI mode
npm run test:e2e:report     # open the last HTML report
npx playwright test comparator.spec.ts   # a single spec file
```

Both dev servers (frontend :5173, backend :8000) are reused if already
running locally (`playwright.config.ts`'s `webServer.reuseExistingServer`);
otherwise Playwright starts them itself.

## Deterministic vs. live

| Spec | Nature | Why |
|---|---|---|
| `comparator.spec.ts` | Deterministic | Seeded session + (for the combined panel) a mocked `/apply` response |
| `selection-phased-apply.spec.ts` | Deterministic | Same |
| `refresh-recovery.spec.ts` | Deterministic | Same, plus real 404s against fixture ids the backend never created |
| `golden-path.spec.ts` | **Live** | Real upload → analysis → conversation → generation → apply → download, against whatever LLM provider chain `.env` configures |
| `downloads.spec.ts` | **Live** | Same real flow, then downloads every format with content/signature checks |

**Why the split:** the backend already has a fully wired mock LLM provider
(`RESUMEPILOT_PRIMARY_PROVIDER=mock`, see `gateways/llm/factory.py`), but it
only produces *type-valid* placeholders (empty strings, zero scores) —
the Tailoring workflow's own contract validation requires suggestions to
cite real evidence/item ids, so an empty-string id always fails it. `mock`
mode can't carry a plan through generation. Instead:

- The 3 deterministic specs seed `sessionStorage` directly (see
  `fixtures/session.ts`) with the exact shape `resumeSessionStorage.ts`
  itself reads and validates — the same thing a real prior session would
  have left behind, not a bypass of any product code — and use
  `page.route()` (see `helpers/mockApply.ts`) where a network response is
  needed. Zero backend code involved.
- `golden-path.spec.ts` / `downloads.spec.ts` are genuinely live and will
  make real LLM calls (cost, latency, ~1–4 minutes each). They need a
  working provider chain in the repo's `.env` (`gemini`/`openrouter` keys,
  or `mock` — though `mock` will fail past the "generate suggestions" step
  for the reason above).

## Debugging

- `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`,
  `video: 'retain-on-failure'` are on by default (see `playwright.config.ts`).
- `npx playwright show-trace test-results/<test>/trace.zip` opens a full
  timeline (DOM snapshots, network, console) for a failed run.
- Career-conversation turns are bounded by the backend's own
  `MAX_CONVERSATION_TURNS` (8), so the live helper's loop can never hang
  indefinitely even if the model keeps asking for more detail.

## Known flakiness

The live specs depend on a real LLM provider and can occasionally fail
with "Could not reach the &lt;x&gt; service" at any step (career
conversation, generation) — this is the frontend's generic
`fetch()`-level failure message, observed here during real network
instability and/or back-to-back live runs in quick succession (possible
provider-side rate limiting). Retrying in isolation resolves it. This is
provider/network flakiness, not an application bug.
