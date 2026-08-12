import type { InterviewPreparationStage } from '../data/jobPreparationHistoryTypes'

// One label per InterviewPreparationStage (see that type's own docstring
// for the three-stage lifecycle) -- shared by History's card and the
// active Interview Preparation page, so the maturity copy can never drift
// between the two places it's shown.
const STAGE_LABELS: Record<InterviewPreparationStage, string> = {
  initial: 'Initial preparation',
  career_conversation_enriched: 'Updated from Career Conversation',
  tailoring_aligned: 'Aligned with your tailored resume',
}

export function interviewPreparationStageLabel(stage: InterviewPreparationStage): string {
  return STAGE_LABELS[stage]
}
