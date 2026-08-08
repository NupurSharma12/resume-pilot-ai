// Pure presentation logic for the Stage 2 suggestion-review redesign.
//
// None of this is backend behavior -- the backend API contract
// (SuggestionResponse / GenerateSuggestionsResponse, see
// data/tailoringSuggestionsTypes.ts) is unchanged. Everything here derives
// a friendlier *presentation* from data the API already returns, because
// the API deliberately never sends: a human-readable section heading
// (only `target_section_id`, an internal id), an "impact" rating (only
// `confidence` + `validation_status`), or evidence *content* (only
// `evidence_sources`, human-readable labels -- see
// `SuggestionResponse`'s own docstring: "Deliberately does NOT expose the
// Evidence Store"). Every function below is explicit about which of these
// it's reconstructing heuristically, so nothing here is presented as more
// precise than it actually is.

import type {
  SuggestionOperation,
  SuggestionValidationStatus,
  TailoringSuggestion,
} from '../data/tailoringSuggestionsTypes'

// ---------------------------------------------------------------------------
// Human language for operations
// ---------------------------------------------------------------------------

// The backend's operation enum (`app.models.tailoring_suggestions.
// SuggestionOperation`) is an implementation detail of *how* the Rewrite
// Engine executes a change, not something a candidate needs to parse.
// This is the one, single mapping to plain language every part of the
// UI uses -- the card's action word, its badge, and its concise summary
// sentence all read from this so they can never say different things
// about the same suggestion.
export const OPERATION_ACTION_LABELS: Record<SuggestionOperation, string> = {
  append: 'Add',
  insert_before: 'Add',
  insert_after: 'Add',
  update: 'Update',
  replace: 'Update',
  remove: 'Remove',
  add_emphasis: 'Strengthen',
}

// ---------------------------------------------------------------------------
// Human-readable section names
// ---------------------------------------------------------------------------

// The backend never sends a section *heading* -- only `target_section_id`
// (an internal id like "section-1"). It does, however, already send
// evidence_sources labels for resume-item evidence in the exact shape
// `EvidenceStoreBuilder` builds them: `"Resume: {heading}"` (see
// app.evidence.evidence_store_builder._resume_item_items). Any suggestion
// that cites its own target item's resume evidence carries its section's
// real heading for free, already in the response -- this just extracts
// it, per section id, from wherever it appears across the whole plan, so
// even a suggestion whose own evidence is conversation-only can still
// show a real heading if another suggestion targeting the same section
// happened to also cite resume evidence.
const RESUME_EVIDENCE_LABEL = /^Resume: (.+)$/

function prettifyHeading(rawHeading: string): string {
  const trimmed = rawHeading.trim()
  if (!trimmed) return trimmed
  const isShoutCase = trimmed === trimmed.toUpperCase() && /[A-Z]/.test(trimmed)
  if (!isShoutCase) return trimmed
  return trimmed
    .toLowerCase()
    .split(' ')
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ')
}

export function buildSectionNameMap(suggestions: TailoringSuggestion[]): Map<string, string> {
  const map = new Map<string, string>()
  for (const suggestion of suggestions) {
    if (map.has(suggestion.target_section_id)) continue
    for (const source of suggestion.evidence_sources) {
      const match = RESUME_EVIDENCE_LABEL.exec(source)
      if (match && match[1] !== 'Header') {
        map.set(suggestion.target_section_id, prettifyHeading(match[1]))
        break
      }
    }
  }
  return map
}

// Stable across a render pass (not derived from the id string itself,
// e.g. never parses "section-N") -- every unique target_section_id in the
// plan, in first-seen order, gets "Resume Section 1", "Resume Section 2",
// etc. Only used for the rare section with no resume-evidence-citing
// suggestion anywhere in the plan (see `buildSectionNameMap`) -- never a
// literal internal id like "section-0" reaches the UI either way.
export function buildSectionFallbackOrdinals(suggestions: TailoringSuggestion[]): Map<string, number> {
  const map = new Map<string, number>()
  let nextOrdinal = 1
  for (const suggestion of suggestions) {
    if (!map.has(suggestion.target_section_id)) {
      map.set(suggestion.target_section_id, nextOrdinal)
      nextOrdinal += 1
    }
  }
  return map
}

export function getReadableSectionName(
  suggestion: TailoringSuggestion,
  sectionNames: Map<string, string>,
  sectionFallbackOrdinals: Map<string, number>,
): string {
  const known = sectionNames.get(suggestion.target_section_id)
  if (known) return known
  const ordinal = sectionFallbackOrdinals.get(suggestion.target_section_id) ?? 1
  return `Resume Section ${ordinal}`
}

// ---------------------------------------------------------------------------
// Impact
// ---------------------------------------------------------------------------

export type ImpactLevel = 'high' | 'medium' | 'low'

const SUPPORTED_STATUSES = new Set<SuggestionValidationStatus>([
  'supported_by_original_resume',
  'supported_by_conversation',
  'supported_by_both',
])

// There is no "impact" field in the API -- this derives a 3-level rating
// from what the backend *does* send: `confidence` (the model's own
// 0-100 self-reported confidence) and `validation_status` (whether the
// text is actually evidence-backed). A suggestion whose evidence doesn't
// hold up is always "low," regardless of how confident the model claims
// to be -- confidence alone is never enough to call something high
// impact if it isn't grounded.
export function getImpactLevel(suggestion: TailoringSuggestion): ImpactLevel {
  if (!SUPPORTED_STATUSES.has(suggestion.validation_status)) return 'low'
  if (suggestion.confidence >= 80) return 'high'
  if (suggestion.confidence >= 50) return 'medium'
  return 'low'
}

export const IMPACT_LABELS: Record<ImpactLevel, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

// Filled-star count out of 5, matching the product spec's exact pattern
// (5 for High, 4 for Medium, 2 for Low -- not a linear 5/3/1 scale).
export const IMPACT_STAR_COUNT: Record<ImpactLevel, number> = {
  high: 5,
  medium: 4,
  low: 2,
}

// ---------------------------------------------------------------------------
// Estimated ATS improvement (plan-level summary, explicitly an estimate)
// ---------------------------------------------------------------------------

const IMPACT_POINTS: Record<ImpactLevel, number> = { high: 3, medium: 2, low: 1 }

// A deterministic, transparent-but-approximate score for the summary
// header only -- never claimed as a measured/guaranteed number anywhere
// in the UI copy (see TailoringPlanSummaryHeader's "(estimate)" label).
// Computed from the *recommended* set specifically (selected_by_default),
// not whatever the user has currently checked, so the number in the
// header stays stable while suggestions are being reviewed below it.
export function estimateAtsImprovementPercent(suggestions: TailoringSuggestion[]): number {
  const recommended = suggestions.filter((s) => s.selected_by_default)
  const points = recommended.reduce((sum, s) => sum + IMPACT_POINTS[getImpactLevel(s)], 0)
  return Math.min(points * 2, 35)
}

// ---------------------------------------------------------------------------
// Append delta: "only the new text being appended," not the full result
// ---------------------------------------------------------------------------

// `suggested_text` for an `append` operation is always the item's FULL
// resulting text (existing text + addition), per the backend's own
// contract (validated server-side: `suggested_text` must contain
// `current_text` as a substring -- see app.evidence.suggestion_validator).
// This recovers just the added portion for display, since showing the
// full paragraph again defeats the "only show what's new" requirement.
// Falls back to the full suggested text (rather than guessing) if
// `current_text` genuinely isn't a substring, which should be unreachable
// given the backend's own validation but is handled defensively rather
// than assumed.
export function computeAppendedDelta(currentText: string, suggestedText: string): string {
  const index = suggestedText.indexOf(currentText)
  if (index === -1) return suggestedText
  const before = suggestedText.slice(0, index)
  const after = suggestedText.slice(index + currentText.length)
  const joined = `${before} ${after}`.trim()
  const cleaned = joined.replace(/^[,;:\s]+/, '').trim()
  return cleaned || suggestedText
}

// ---------------------------------------------------------------------------
// One-line, scannable summary -- the card's headline content
// ---------------------------------------------------------------------------

export function truncateText(text: string, maxLength = 80): string {
  const trimmed = text.trim()
  if (trimmed.length <= maxLength) return trimmed
  return `${trimmed.slice(0, maxLength).trimEnd()}…`
}

// The single line a candidate reads to decide "do I want this change?"
// without opening anything -- e.g. "Add React, TypeScript and Node.js."
// Deliberately not the full generated text (that's what "Preview Change"
// is for): this is a teaser, built from the same fields the full text
// comes from, truncated to stay scannable across a list of 15 suggestions.
//
// `overrideSuggestedText` is the user-edited text, when there is one --
// without it, the summary would keep describing the model's original
// wording even after a candidate customized it, silently disagreeing
// with the "Edited" badge and the Preview Change panel right below it.
export function summarizeSuggestionChange(
  suggestion: TailoringSuggestion,
  overrideSuggestedText?: string,
): string {
  const verb = OPERATION_ACTION_LABELS[suggestion.operation]
  if (suggestion.operation === 'remove') {
    return `Remove: ${truncateText(suggestion.current_text ?? '')}`
  }
  const suggestedText = overrideSuggestedText ?? suggestion.suggested_text
  const content =
    suggestion.operation === 'append' && suggestion.current_text !== null
      ? computeAppendedDelta(suggestion.current_text, suggestedText)
      : suggestedText
  return `${verb} ${truncateText(content)}`
}

// ---------------------------------------------------------------------------
// Evidence grouping: label-only (no snippet content is sent by the API)
// ---------------------------------------------------------------------------

export type EvidenceCategory = 'resume' | 'conversation' | 'analysis'

export interface EvidenceGroup {
  category: EvidenceCategory
  label: string
  sources: string[]
}

const EVIDENCE_GROUP_ORDER: { category: EvidenceCategory; label: string; test: (s: string) => boolean }[] = [
  { category: 'resume', label: 'Resume', test: (s) => s.startsWith('Resume:') || s.startsWith('Original Resume') },
  { category: 'conversation', label: 'Career Conversation', test: (s) => s.startsWith('Conversation Turn') },
  {
    category: 'analysis',
    label: 'Resume Analysis',
    test: (s) =>
      s.startsWith('Analysis') || s.startsWith('Resume Analysis') || s.startsWith('Matched Skills') ||
      s.startsWith('Resume Project'),
  },
]

// Groups the suggestion's `evidence_sources` labels by source category,
// for the expandable "Evidence" section. This groups *labels* only --
// e.g. "Conversation Turn 2," not the actual question/answer text --
// because the API never sends evidence content to the frontend (the
// Evidence Store is deliberately internal-only; see
// GenerateSuggestionsResponse's docstring). Expanding a group surfaces
// every label in it, which is the most specific detail available without
// a backend change.
export function groupEvidenceSources(sources: string[]): EvidenceGroup[] {
  const groups: EvidenceGroup[] = []
  for (const { category, label, test } of EVIDENCE_GROUP_ORDER) {
    const matched = sources.filter(test)
    if (matched.length > 0) groups.push({ category, label, sources: matched })
  }
  return groups
}

// ---------------------------------------------------------------------------
// Grouping by section (requirement: suggestions grouped by section, but
// still individually selectable) and mutual-exclusion summaries
// ---------------------------------------------------------------------------

export interface SuggestionSectionGroup {
  sectionId: string
  sectionName: string
  suggestions: TailoringSuggestion[]
}

// Buckets a plan's suggestions by `target_section_id`, preserving each
// suggestion's original plan order both within a group and across groups
// (a group's position is its first suggestion's position) -- grouping is
// purely a visual clustering for the review list, never a reordering the
// backend would disagree with.
export function groupSuggestionsBySection(
  suggestions: TailoringSuggestion[],
  sectionNames: Map<string, string>,
  sectionFallbackOrdinals: Map<string, number>,
): SuggestionSectionGroup[] {
  const order: string[] = []
  const bySection = new Map<string, TailoringSuggestion[]>()
  for (const suggestion of suggestions) {
    const sectionId = suggestion.target_section_id
    if (!bySection.has(sectionId)) {
      bySection.set(sectionId, [])
      order.push(sectionId)
    }
    bySection.get(sectionId)?.push(suggestion)
  }
  return order.map((sectionId) => {
    const groupSuggestions = bySection.get(sectionId) ?? []
    return {
      sectionId,
      sectionName: getReadableSectionName(groupSuggestions[0], sectionNames, sectionFallbackOrdinals),
      suggestions: groupSuggestions,
    }
  })
}

// For a suggestion with a non-empty `conflicts_with`, a short human-language
// description of each suggestion it's mutually exclusive with -- e.g.
// "Update Full-stack engineer with React and Python experience." -- built
// from the exact same one-line summary the conflicting card itself shows,
// so a candidate reading "conflicts with: ..." recognizes the other card
// instantly rather than being shown a raw suggestion id.
export function buildConflictSummaries(suggestions: TailoringSuggestion[]): Map<string, string[]> {
  const byId = new Map(suggestions.map((s) => [s.suggestion_id, s]))
  const map = new Map<string, string[]>()
  for (const suggestion of suggestions) {
    if (suggestion.conflicts_with.length === 0) continue
    const summaries = suggestion.conflicts_with
      .map((id) => byId.get(id))
      .filter((s): s is TailoringSuggestion => s !== undefined)
      .map((s) => summarizeSuggestionChange(s))
    map.set(suggestion.suggestion_id, summaries)
  }
  return map
}
