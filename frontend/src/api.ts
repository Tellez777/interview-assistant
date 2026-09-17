// Cliente delgado sobre la API del backend (ver backend/app/main.py).
// El proxy de Vite (vite.config.ts) reenvía /api al backend en :8000.

export interface QuestionReference {
  answer_en: string
  keypoints: string[]
  reviewed: boolean
}

export interface Question {
  id: string
  category: string
  question_en: string
  hint?: string
  reference: QuestionReference | null
}

export interface ObjectiveMetrics {
  word_count: number
  duration_seconds: number
  words_per_minute: number
  filler_count: number
  filler_breakdown: Record<string, number>
}

export interface LlmFeedback {
  grammar_corrections?: { original: string; suggested: string }[]
  vocabulary_notes?: string
  keypoints_mentioned?: string[]
  keypoints_missed?: string[]
  unsupported_claims?: string[]
  overall_note?: string
  error?: string
}

export interface TurnResult {
  turn_id: string
  transcript: string
  objective: ObjectiveMetrics
  llm_feedback: LlmFeedback | null
}

export interface ProgressTurn {
  id: string
  session_id: string
  question_id: string
  category: string
  created_at: number
  transcript: string
  words_per_minute: number | null
  duration_seconds: number | null
  pause_count: number | null
  filler_count: number | null
  llm_feedback: LlmFeedback | null
}

export interface LiveSessionSummary {
  id: string
  started_at: number
  stopped_at: number | null
  turn_count: number
  language: 'en' | 'es' | null
}

export interface LiveTurnRecord {
  id: string
  session_id: string
  created_at: number
  question_en: string
  translation_es: string | null
  keypoints: string[] | null
  keypoints_source_id: string | null
  keypoints_score: number | null
  answer_mode: 'cached' | 'llm' | 'technical' | null
  answer_text: string | null
  answer_language: string | null
  answer_language_ok: number | null
  marks_ms: Record<string, number> | null
  error: string | null
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  categories: () => fetch('/api/categories').then((r) => json<string[]>(r)),

  createSession: () =>
    fetch('/api/practice/sessions', { method: 'POST' }).then((r) => json<{ session_id: string }>(r)),

  nextQuestion: (category: string | null, excludeIds: string[]) => {
    const params = new URLSearchParams()
    if (category) params.set('category', category)
    if (excludeIds.length) params.set('exclude', excludeIds.join(','))
    return fetch(`/api/practice/questions/next?${params}`).then((r) => json<Question>(r))
  },

  questionAudioUrl: (questionId: string) => `/api/practice/questions/${questionId}/audio`,

  submitTurn: (sessionId: string, questionId: string, audioBlob: Blob) => {
    const form = new FormData()
    form.append('question_id', questionId)
    form.append('audio', audioBlob, 'answer.webm')
    return fetch(`/api/practice/sessions/${sessionId}/turns`, { method: 'POST', body: form }).then((r) =>
      json<TurnResult>(r),
    )
  },

  progress: () => fetch('/api/practice/progress').then((r) => json<ProgressTurn[]>(r)),

  weakestCategories: () =>
    fetch('/api/practice/progress/weakest').then((r) =>
      json<{ category: string; avg_wpm: number; attempts: number }[]>(r),
    ),

  liveSessions: () => fetch('/api/live/sessions').then((r) => json<LiveSessionSummary[]>(r)),

  liveTurns: (sessionId: string | null) => {
    const params = new URLSearchParams()
    if (sessionId) params.set('session_id', sessionId)
    return fetch(`/api/live/turns?${params}`).then((r) => json<LiveTurnRecord[]>(r))
  },
}
