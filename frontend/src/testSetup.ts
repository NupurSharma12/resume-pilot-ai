import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// `test.globals` is off (see vitest.config.ts), so @testing-library/react's
// own auto-cleanup (which only activates when it detects a *global*
// `afterEach`) never kicks in -- without this, every test's rendered DOM
// piles up in `document.body`, and later tests' queries (getByTestId, etc.)
// start matching stale elements from earlier tests.
afterEach(() => {
  cleanup()
})

// jsdom doesn't implement scrollIntoView; several components call it on
// mount/update (see CareerConversationPage, DashboardPage), which would
// otherwise throw and fail unrelated tests.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
