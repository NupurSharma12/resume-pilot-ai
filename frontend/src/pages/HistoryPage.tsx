import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, ChevronLeft, ChevronRight, RotateCw, Search, Sparkles } from 'lucide-react'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import InterviewPreparationCard from '../components/InterviewPreparationCard'
import CheckpointList from '../components/CheckpointList'
import ContinuePreparationDialog from '../components/ContinuePreparationDialog'
import DeleteConfirmationDialog from '../components/DeleteConfirmationDialog'
import {
  deleteJobPreparation,
  generateInterviewPreparation,
  getJobPreparation,
  listJobPreparations,
} from '../lib/jobPreparationHistoryApi'
import { ApiError } from '../lib/api'
import { useResumeSession } from '../session/ResumeSessionContext'
import type {
  CheckpointStatus,
  JobPreparationDetail,
  JobPreparationSummary,
} from '../data/jobPreparationHistoryTypes'

// History shows 10 preparations per page -- see the History server-side
// pagination/search decision. Both search and paging now round-trip to
// the backend (`listJobPreparations` already supports `search`/`limit`/
// `offset` server-side -- see that endpoint's own docstring), rather
// than fetching one page and filtering it client-side.
const HISTORY_PAGE_SIZE = 10

// How long to wait after the user stops typing before firing a new
// search request -- short enough to feel responsive, long enough that a
// normal typing cadence doesn't fire one request per keystroke.
const SEARCH_DEBOUNCE_MS = 300

// A preparation is "complete" once its last checkpoint (re-analysis) is
// done -- everything upstream of it is necessarily done too, since each
// checkpoint's own workflow step depends on the previous one having
// already run. Complete preparations show "View Preparation" (read-only);
// anything else shows "Continue Preparation".
function isFullyComplete(checkpoints: CheckpointStatus): boolean {
  return checkpoints.post_apply_analysis_completed_at !== null
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Defensive readers over the detail response's raw JSONB payloads
// (typed as `Record<string, unknown> | null` -- see
// jobPreparationHistoryTypes.ts's docstring for why these aren't
// re-modeled as full domain types here): each payload's inner shape is
// already owned by its producing workflow (ResumeAnalysisResult,
// ConversationSessionState, ...), so History only ever reads the handful
// of fields it actually displays, tolerating anything unexpected by
// simply not rendering that field rather than crashing.
function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null
}
function asNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}
function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}
function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null
}

function InitialAnalysisSection({ analysisResult }: { analysisResult: Record<string, unknown> }) {
  const overallAssessment = asRecord(analysisResult.overall_assessment)
  const score = asNumber(overallAssessment?.overall_score)
  const summary = asString(overallAssessment?.summary)
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Initial Analysis</h3>
      {score !== null && <p className="mt-2 text-2xl font-bold text-gray-900">{score}%</p>}
      {summary && <p className="mt-1 text-sm text-gray-500">{summary}</p>}
    </div>
  )
}

function CareerConversationSection({
  careerConversation,
}: {
  careerConversation: Record<string, unknown>
}) {
  const history = asArray(careerConversation.history)
  const stopReason = asString(careerConversation.stop_reason)
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Career Conversation</h3>
      <p className="mt-2 text-sm text-gray-500">
        {history ? `${history.length} exchange${history.length === 1 ? '' : 's'} recorded.` : null}
      </p>
      {stopReason && <p className="mt-1 text-sm text-gray-500">{stopReason}</p>}
    </div>
  )
}

function TailoringPlanSection({ tailoringPlan }: { tailoringPlan: Record<string, unknown> }) {
  const generatedPlan = asRecord(tailoringPlan.generated_plan)
  const suggestions = asArray(generatedPlan?.suggestions)
  const selection = asRecord(tailoringPlan.selection)
  const selectedIds = asArray(selection?.selected_suggestion_ids)
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Tailoring Plan</h3>
      {suggestions && (
        <p className="mt-2 text-sm text-gray-500">
          {suggestions.length} suggestion{suggestions.length === 1 ? '' : 's'} generated
          {selectedIds ? `, ${selectedIds.length} selected` : ''}.
        </p>
      )}
    </div>
  )
}

function TailoredResumeSection({ appliedResumeText }: { appliedResumeText: string }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Tailored Resume</h3>
      <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-xl bg-gray-50 p-4 text-xs text-gray-700">
        {appliedResumeText}
      </pre>
    </div>
  )
}

function ReanalysisSection({ postApplyAnalysis }: { postApplyAnalysis: Record<string, unknown> }) {
  const comparison = asRecord(postApplyAnalysis.comparison)
  const scoreBefore = asNumber(comparison?.score_before)
  const scoreAfter = asNumber(comparison?.score_after)
  const status = asString(comparison?.status)
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6">
      <h3 className="font-semibold text-gray-900">Re-analysis</h3>
      {scoreBefore !== null && scoreAfter !== null && (
        <p className="mt-2 text-sm text-gray-700">
          {scoreBefore}% <span className="text-gray-400">→</span> {scoreAfter}%
          {status && <span className="ml-2 text-gray-500">({status})</span>}
        </p>
      )}
    </div>
  )
}

type ListStatus = 'loading' | 'success' | 'error'
type DetailStatus = 'loading' | 'success' | 'error'
type GenerationStatus = 'idle' | 'generating' | 'error'
type ContinueStatus = 'idle' | 'loading' | 'error'
type DeleteStatus = 'idle' | 'loading' | 'error'

export default function HistoryPage() {
  const navigate = useNavigate()
  const { rehydrateFromHistory } = useResumeSession()

  const [items, setItems] = useState<JobPreparationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [listStatus, setListStatus] = useState<ListStatus>('loading')
  const [listError, setListError] = useState('')

  // `searchQuery` is what the input reflects as the user types;
  // `debouncedSearchQuery` (updated `SEARCH_DEBOUNCE_MS` after typing
  // stops) is what's actually sent to the backend -- see the effect
  // below. Kept as two separate values, rather than debouncing the
  // fetch call itself, so the input never feels laggy even though the
  // request it triggers does.
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('')

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<JobPreparationDetail | null>(null)
  const [detailStatus, setDetailStatus] = useState<DetailStatus>('loading')
  const [detailError, setDetailError] = useState('')

  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>('idle')
  const [generationError, setGenerationError] = useState('')

  // The item currently shown in the Continue confirmation dialog, or null
  // if it's closed. Deliberately holds the already-fetched `Summary` (its
  // `checkpoints` are enough for the confirmation, see the design review)
  // rather than eagerly fetching the full `Detail` just to open the
  // dialog -- the full detail is only fetched once the user actually
  // confirms, in `handleConfirmContinue`.
  const [continueTarget, setContinueTarget] = useState<JobPreparationSummary | null>(null)
  const [continueStatus, setContinueStatus] = useState<ContinueStatus>('idle')
  const [continueError, setContinueError] = useState('')

  // Same "hold the already-fetched Summary, not a fresh fetch" shape as
  // continueTarget above.
  const [deleteTarget, setDeleteTarget] = useState<JobPreparationSummary | null>(null)
  const [deleteStatus, setDeleteStatus] = useState<DeleteStatus>('idle')
  const [deleteError, setDeleteError] = useState('')

  async function loadList(requestOffset: number, search: string) {
    setListStatus('loading')
    try {
      const result = await listJobPreparations({
        limit: HISTORY_PAGE_SIZE,
        offset: requestOffset,
        ...(search ? { search } : {}),
      })
      setItems(result.items)
      setTotal(result.total)
      setListStatus('success')
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setListStatus('error')
    }
  }

  // Debounces `searchQuery` into `debouncedSearchQuery` -- see that
  // state's own comment for why these are two separate values.
  useEffect(() => {
    const timeoutId = setTimeout(() => setDebouncedSearchQuery(searchQuery), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timeoutId)
  }, [searchQuery])

  // A new search always restarts pagination at the first page -- a
  // previous page offset almost certainly doesn't apply to a new,
  // narrower (or wider) result set.
  useEffect(() => {
    setOffset(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearchQuery])

  useEffect(() => {
    loadList(offset, debouncedSearchQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, debouncedSearchQuery])

  const hasNextPage = offset + items.length < total
  const hasPreviousPage = offset > 0
  const firstShownIndex = total === 0 ? 0 : offset + 1
  const lastShownIndex = offset + items.length

  function handleConfirmContinue() {
    if (!continueTarget) return
    const target = continueTarget
    setContinueStatus('loading')
    setContinueError('')
    getJobPreparation(target.id)
      .then((jobPreparationDetail) => {
        const outcome = rehydrateFromHistory(jobPreparationDetail)
        if (!outcome.ok) {
          // Fails gracefully: the dialog stays open with the reason
          // instead of navigating into a session that would crash
          // elsewhere -- see rehydrateFromJobPreparation's own docstring.
          setContinueError(outcome.error)
          setContinueStatus('error')
          return
        }
        setContinueStatus('idle')
        setContinueTarget(null)
        navigate(outcome.nextRoute)
      })
      .catch((err: unknown) => {
        setContinueError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
        setContinueStatus('error')
      })
  }

  function handleConfirmDelete() {
    if (!deleteTarget) return
    const target = deleteTarget
    setDeleteStatus('loading')
    setDeleteError('')
    deleteJobPreparation(target.id)
      .then(() => {
        // No full reload -- just drop it from the already-loaded list,
        // the same "update in place" approach `handleGenerateInterviewPreparation`
        // below already uses for its own successful mutation. `total` is
        // decremented alongside it so pagination metadata (Prev/Next,
        // "X-Y of Z") stays consistent with what's actually still there,
        // without a second round-trip just to re-fetch the count.
        setItems((current) => current.filter((item) => item.id !== target.id))
        setTotal((current) => Math.max(0, current - 1))
        setDeleteStatus('idle')
        setDeleteTarget(null)
      })
      .catch((err: unknown) => {
        // A 404 means the desired end state ("not in History") already
        // holds -- e.g. deleted from another tab in the meantime. Treat
        // it the same as a successful delete rather than showing a
        // confusing error for something the user was already trying to
        // achieve.
        if (err instanceof ApiError && err.cause === 'not_found') {
          setItems((current) => current.filter((item) => item.id !== target.id))
          setTotal((current) => Math.max(0, current - 1))
          setDeleteStatus('idle')
          setDeleteTarget(null)
          return
        }
        setDeleteError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
        setDeleteStatus('error')
      })
  }

  async function openPreparation(id: string) {
    setSelectedId(id)
    setDetail(null)
    setDetailStatus('loading')
    setDetailError('')
    setGenerationStatus('idle')
    setGenerationError('')
    try {
      const result = await getJobPreparation(id)
      setDetail(result)
      setDetailStatus('success')
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setDetailStatus('error')
    }
  }

  function backToList() {
    setSelectedId(null)
    setDetail(null)
  }

  async function handleGenerateInterviewPreparation() {
    if (!selectedId) return
    setGenerationStatus('generating')
    setGenerationError('')
    try {
      const result = await generateInterviewPreparation(selectedId)
      setDetail((current) => (current ? { ...current, interview_preparation: result } : current))
      setGenerationStatus('idle')
    } catch (err) {
      setGenerationError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setGenerationStatus('error')
    }
  }

  if (selectedId !== null) {
    return (
      <>
        <TopHeader title="History" subtitle="Job preparation details" />
        <div className="mx-auto max-w-3xl space-y-6 p-8">
          <Button variant="outline" icon={<ArrowLeft size={16} />} onClick={backToList}>
            Back to History
          </Button>

          {detailStatus === 'loading' && (
            <div className="rounded-2xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500">
              Loading…
            </div>
          )}

          {detailStatus === 'error' && (
            <div className="flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
                <AlertTriangle size={22} />
              </div>
              <p className="text-sm text-gray-500">{detailError}</p>
              <Button
                variant="outline"
                icon={<RotateCw size={16} />}
                onClick={() => openPreparation(selectedId)}
              >
                Try Again
              </Button>
            </div>
          )}

          {detailStatus === 'success' && detail && (
            <>
              <div className="rounded-2xl border border-gray-200 bg-white p-6">
                <h2 className="font-semibold text-gray-900">{detail.job_title}</h2>
                <p className="mt-1 text-sm text-gray-500">
                  {detail.company ? `${detail.company} · ` : ''}
                  {detail.resume_name}
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  Last updated {formatDate(detail.updated_at)}
                </p>
                <div className="mt-4">
                  <CheckpointList checkpoints={detail.checkpoints} />
                </div>
              </div>

              {detail.analysis_result && (
                <InitialAnalysisSection analysisResult={detail.analysis_result} />
              )}
              {detail.career_conversation && (
                <CareerConversationSection careerConversation={detail.career_conversation} />
              )}
              {detail.tailoring_plan && (
                <TailoringPlanSection tailoringPlan={detail.tailoring_plan} />
              )}
              {detail.applied_resume_text && (
                <TailoredResumeSection appliedResumeText={detail.applied_resume_text} />
              )}
              {detail.post_apply_analysis && (
                <ReanalysisSection postApplyAnalysis={detail.post_apply_analysis} />
              )}

              {detail.interview_preparation ? (
                <InterviewPreparationCard interviewPreparation={detail.interview_preparation} />
              ) : (
                <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-6 text-center">
                  <p className="text-sm text-gray-500">No interview preparation guide yet.</p>
                  {generationStatus === 'error' && (
                    <p className="mt-2 text-sm text-rose-500">{generationError}</p>
                  )}
                  <div className="mt-4">
                    <Button
                      variant="solid"
                      icon={<Sparkles size={16} />}
                      disabled={generationStatus === 'generating'}
                      onClick={handleGenerateInterviewPreparation}
                    >
                      {generationStatus === 'generating'
                        ? 'Generating…'
                        : generationStatus === 'error'
                          ? 'Try Again'
                          : 'Generate Interview Preparation'}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </>
    )
  }

  return (
    <>
      <TopHeader title="History" subtitle="Past resume + job preparations" />
      <div className="mx-auto max-w-3xl space-y-4 p-8">
        {listStatus === 'success' && items.length > 0 && (
          <div className="relative">
            <Search
              size={16}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-gray-400"
              aria-hidden="true"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search by job title, company, or resume…"
              aria-label="Search job preparations"
              className="w-full rounded-full border border-gray-200 bg-white py-2.5 pl-10 pr-4 text-sm text-gray-800 placeholder:text-gray-400 focus:border-indigo-400 focus:outline-none"
            />
          </div>
        )}

        {listStatus === 'loading' && (
          <div className="rounded-2xl border border-gray-200 bg-white p-10 text-center text-sm text-gray-500">
            Loading…
          </div>
        )}

        {listStatus === 'error' && (
          <div className="flex flex-col items-center gap-4 rounded-2xl border border-gray-200 bg-white px-8 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500">
              <AlertTriangle size={22} />
            </div>
            <p className="text-sm text-gray-500">{listError}</p>
            <Button
              variant="outline"
              icon={<RotateCw size={16} />}
              onClick={() => loadList(offset, debouncedSearchQuery)}
            >
              Try Again
            </Button>
          </div>
        )}

        {listStatus === 'success' && items.length === 0 && !debouncedSearchQuery && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
            Analysis history is coming soon.
          </div>
        )}

        {listStatus === 'success' && items.length === 0 && debouncedSearchQuery && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
            No preparations match "{debouncedSearchQuery}".
          </div>
        )}

        {listStatus === 'success' &&
          items.map((item) => {
            const complete = isFullyComplete(item.checkpoints)
            return (
              <div key={item.id} className="rounded-2xl border border-gray-200 bg-white p-6">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold text-gray-900">{item.job_title}</h3>
                    <p className="mt-0.5 text-sm text-gray-500">
                      {item.resume_name}
                      {item.company ? ` · ${item.company}` : ''}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-gray-400">
                    Last updated {formatDate(item.updated_at)}
                  </span>
                </div>
                <div className="mt-4">
                  <CheckpointList checkpoints={item.checkpoints} />
                </div>
                <div className="mt-4 flex justify-end gap-3">
                  <Button variant="outline" onClick={() => openPreparation(item.id)}>
                    View Preparation
                  </Button>
                  {!complete && (
                    <Button
                      variant="solid"
                      onClick={() => {
                        setContinueError('')
                        setContinueStatus('idle')
                        setContinueTarget(item)
                      }}
                    >
                      Continue Preparation
                    </Button>
                  )}
                  <Button
                    variant="danger"
                    onClick={() => {
                      setDeleteError('')
                      setDeleteStatus('idle')
                      setDeleteTarget(item)
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            )
          })}

        {listStatus === 'success' && total > 0 && (
          <div className="flex items-center justify-between gap-4 pt-2">
            <p className="text-xs text-gray-400">
              Showing {firstShownIndex}-{lastShownIndex} of {total}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                icon={<ChevronLeft size={16} />}
                disabled={!hasPreviousPage}
                onClick={() => setOffset((current) => Math.max(0, current - HISTORY_PAGE_SIZE))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                icon={<ChevronRight size={16} />}
                disabled={!hasNextPage}
                onClick={() => setOffset((current) => current + HISTORY_PAGE_SIZE)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {continueTarget && (
        <ContinuePreparationDialog
          jobTitle={continueTarget.job_title}
          company={continueTarget.company}
          checkpoints={continueTarget.checkpoints}
          isLoading={continueStatus === 'loading'}
          error={continueError}
          onCancel={() => setContinueTarget(null)}
          onConfirm={handleConfirmContinue}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmationDialog
          jobTitle={deleteTarget.job_title}
          company={deleteTarget.company}
          isLoading={deleteStatus === 'loading'}
          error={deleteError}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleConfirmDelete}
        />
      )}
    </>
  )
}
