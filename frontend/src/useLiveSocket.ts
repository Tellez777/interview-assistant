import { useCallback, useEffect, useRef, useState } from 'react'

// Espeja los eventos de backend/app/live/events.py. Solo hay canal
// "interviewer" — el de "candidate" (micrófono) se probó y se descartó:
// sin audífonos, el micrófono capta acústicamente el audio de las bocinas
// y termina transcribiendo una mezcla ilegible (ver plan, M4).
interface LiveEvent {
  type: string
  turn_id?: string
  text?: string
  delta?: string
  mode?: 'cached' | 'llm' | 'technical'
  keypoints?: string[]
  source_id?: string | null
  score?: number
  marks_ms?: Record<string, number>
  message?: string
}

interface Turn {
  turnId: string
  finalEn: string
  translationEs: string
  keypoints: string[]
  keypointsSource: string | null
  keypointsScore: number
  answerMode: 'cached' | 'llm' | 'technical' | null
  answerText: string
  answerDone: boolean
  marksMs: Record<string, number> | null
}

function emptyTurn(turnId: string, finalEn: string): Turn {
  return {
    turnId,
    finalEn,
    translationEs: '',
    keypoints: [],
    keypointsSource: null,
    keypointsScore: 0,
    answerMode: null,
    answerText: '',
    answerDone: false,
    marksMs: null,
  }
}

/** Conecta al WebSocket de Live Mode y mantiene el estado de los paneles.
 * La captura de audio ocurre en el backend (loopback del sistema), no
 * aquí — este hook solo recibe texto y eventos (ver plan, M4). */
export function useLiveSocket() {
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState<string>('Desconectado')
  const [interviewerPartial, setInterviewerPartial] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/api/live/stream`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)

    ws.onmessage = (raw) => {
      const event = JSON.parse(raw.data) as LiveEvent

      switch (event.type) {
        case 'status':
          setStatus(event.message ?? '')
          break

        case 'partial_en':
          setInterviewerPartial(event.text ?? '')
          break

        case 'final_en':
          setInterviewerPartial('')
          setTurns((prev) => [...prev, emptyTurn(event.turn_id!, event.text ?? '')])
          break

        case 'translation_es':
          setTurns((prev) =>
            prev.map((t) => (t.turnId === event.turn_id ? { ...t, translationEs: event.text ?? '' } : t)),
          )
          break

        case 'keypoints':
          setTurns((prev) =>
            prev.map((t) =>
              t.turnId === event.turn_id
                ? {
                    ...t,
                    keypoints: event.keypoints ?? [],
                    keypointsSource: event.source_id ?? null,
                    keypointsScore: event.score ?? 0,
                  }
                : t,
            ),
          )
          break

        case 'answer_start':
          setTurns((prev) =>
            prev.map((t) => (t.turnId === event.turn_id ? { ...t, answerMode: event.mode ?? null, answerText: '' } : t)),
          )
          break

        case 'answer_chunk':
          setTurns((prev) =>
            prev.map((t) =>
              t.turnId === event.turn_id ? { ...t, answerText: t.answerText + (event.delta ?? '') } : t,
            ),
          )
          break

        case 'answer_done':
          setTurns((prev) => prev.map((t) => (t.turnId === event.turn_id ? { ...t, answerDone: true } : t)))
          break

        case 'metrics':
          setTurns((prev) =>
            prev.map((t) => (t.turnId === event.turn_id ? { ...t, marksMs: event.marks_ms ?? null } : t)),
          )
          break

        case 'error':
          setStatus(`Error: ${event.message}`)
          break
      }
    }

    return () => ws.close()
  }, [])

  const start = useCallback(async (language: 'en' | 'es' = 'en') => {
    // El backend es idempotente: si ya había una sesión activa, la
    // reinicia limpia en vez de rechazar — nunca debería devolver 409.
    const res = await fetch(`/api/live/sessions/start?language=${language}`, { method: 'POST' })
    if (!res.ok) {
      throw new Error(`No se pudo iniciar Live Mode (${res.status}): ${await res.text()}`)
    }
  }, [])

  const stop = useCallback(async () => {
    await fetch('/api/live/sessions/stop', { method: 'POST' })
  }, [])

  const setFullAnswer = useCallback(async (enabled: boolean) => {
    await fetch(`/api/live/sessions/full-answer?enabled=${enabled}`, { method: 'POST' })
  }, [])

  return {
    connected,
    status,
    interviewerPartial,
    turns,
    start,
    stop,
    setFullAnswer,
  }
}
