import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, RotateCw, Search, Sparkles } from 'lucide-react'
import TopHeader from '../components/TopHeader'
import Button from '../components/Button'
import InterviewPreparationCard from '../components/InterviewPreparationCard'
import CheckpointList from '../components/CheckpointList'
import ContinuePreparationDialog from '../components/ContinuePreparationDialog'
import {
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

// History shows only the 10 most recent preparations -- see the History
// Resumability design review: "prefer existing APIs and data," no
// pagination. `listJobPreparations` already supports a `limit` query
// param server-side (see the backend endpoint's own docstring); this is
// the one place the frontend opts into a smaller page than its default.
const HISTORY_LIST_LIMIT = 10

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

export default function HistoryPage() {
  const navigate = useNavigate()
  const { rehydrateFromHistory } = useResumeSession()

  const [items, setItems] = useState<JobPreparationSummary[]>([])
  const [listStatus, setListStatus] = useState<ListStatus>('loading')
  const [listError, setListError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

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

  async function loadList() {
    setListStatus('loading')
    try {
      const result = await listJobPreparations({ limit: HISTORY_LIST_LIMIT })
      setItems(result)
      setListStatus('success')
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
      setListStatus('error')
    }
  }

  useEffect(() => {
    loadList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Client-side only -- see the design review's "History search should
  // remain deliberately simple" requirement: no server-side full-text
  // search, just a substring match over the (at most 10) already-fetched
  // rows' visible fields.
  const filteredItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return items
    return items.filter((item) =>
      [item.job_title, item.company, item.resume_name].some((field) =>
        field?.toLowerCase().includes(query),
      ),
    )
  }, [items, searchQuery])

  function handleConfirmContinue() {
    if (!continueTarget) return
    const target = continueTarget
    setContinueStatus('loading')
    setContinueError('')
    getJobPreparation(target.id)
      .then((jobPreparationDetail) => {
        const nextRoute = rehydrateFromHistory(jobPreparationDetail)
        setContinueStatus('idle')
        setContinueTarget(null)
        navigate(nextRoute)
      })
      .catch((err: unknown) => {
        setContinueError(err instanceof ApiError ? err.message : 'An unexpected error occurred.')
        setContinueStatus('error')
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
            <Button variant="outline" icon={<RotateCw size={16} />} onClick={loadList}>
              Try Again
            </Button>
          </div>
        )}

        {listStatus === 'success' && items.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
            Analysis history is coming soon.
          </div>
        )}

        {listStatus === 'success' && items.length > 0 && filteredItems.length === 0 && (
          <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-10 text-center text-sm text-gray-500">
            No preparations match "{searchQuery}".
          </div>
        )}

        {listStatus === 'success' &&
          filteredItems.map((item) => {
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
                </div>
              </div>
            )
          })}
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
    </>
  )
}
