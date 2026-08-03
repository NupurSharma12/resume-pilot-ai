// Mirrors the FastAPI backend's Career Conversation response shape
// field-for-field (src/app/api/v1/models/career_conversation.py),
// snake_case included — same convention as `ResumeAnalysisResult` in
// types.ts, so a real API response body needs no reshaping.

export type EstimatedImpact = 'high' | 'medium' | 'low'

export type ConversationSessionStatus = 'in_progress' | 'complete'

export interface ConversationQuestion {
  topic: string
  question: string
  evidence_goal: string
  estimated_impact: EstimatedImpact
}

export interface ConversationExchange {
  topic: string
  question: string
  answer: string
}

export interface ConversationSessionState {
  session_id: string
  status: ConversationSessionStatus
  history: ConversationExchange[]
  current_question: ConversationQuestion | null
  stop_reason: string | null
}
