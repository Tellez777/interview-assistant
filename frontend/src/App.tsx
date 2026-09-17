import { useEffect, useState } from 'react'
import { api, type LlmFeedback, type ObjectiveMetrics, type ProgressTurn, type Question } from './api'
import LiveHistoryView from './LiveHistoryView'
import LiveView from './LiveView'
import { useRecorder } from './useRecorder'

type Tab = 'practice' | 'progress' | 'live' | 'live-history'

export default function App() {
  const [tab, setTab] = useState<Tab>('practice')

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Asistente de Entrevistas</h1>
        <nav className="flex gap-2">
          <TabButton active={tab === 'practice'} onClick={() => setTab('practice')}>
            Práctica
          </TabButton>
          <TabButton active={tab === 'progress'} onClick={() => setTab('progress')}>
            Progreso
          </TabButton>
          <TabButton active={tab === 'live'} onClick={() => setTab('live')}>
            Live
          </TabButton>
          <TabButton active={tab === 'live-history'} onClick={() => setTab('live-history')}>
            Historial Live
          </TabButton>
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === 'practice' && <PracticeView />}
        {tab === 'progress' && <ProgressView />}
        {tab === 'live' && <LiveView />}
        {tab === 'live-history' && <LiveHistoryView />}
      </main>
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
        active ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-100'
      }`}
    >
      {children}
    </button>
  )
}

function PracticeView() {
  const [categories, setCategories] = useState<string[]>([])
  const [category, setCategory] = useState<string>('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [question, setQuestion] = useState<Question | null>(null)
  const [seenIds, setSeenIds] = useState<string[]>([])
  const [showReference, setShowReference] = useState(false)
  const [result, setResult] = useState<
    { transcript: string; objective: ObjectiveMetrics; llm_feedback: LlmFeedback | null } | null
  >(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const recorder = useRecorder()

  useEffect(() => {
    api.categories().then(setCategories).catch(() => setCategories([]))
  }, [])

  async function startSession() {
    const { session_id } = await api.createSession()
    setSessionId(session_id)
    setSeenIds([])
    await loadNextQuestion([])
  }

  async function loadNextQuestion(exclude: string[]) {
    setResult(null)
    setShowReference(false)
    recorder.reset()
    const q = await api.nextQuestion(category || null, exclude)
    setQuestion(q)
    setSeenIds([...exclude, q.id])
  }

  async function handleSubmit() {
    if (!sessionId || !question || !recorder.audioBlob) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await api.submitTurn(sessionId, question.id, recorder.audioBlob)
      setResult(res)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Error al enviar la respuesta')
    } finally {
      setSubmitting(false)
    }
  }

  if (!sessionId) {
    return (
      <div className="space-y-4">
        <p className="text-slate-400">
          Elige una categoría (o deja "Todas") y empieza una sesión. Vas a escuchar la pregunta, responder en voz
          alta, y ver retroalimentación de gramática, vocabulario y qué puntos clave mencionaste.
        </p>
        <div className="flex gap-3">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
          >
            <option value="">Todas las categorías</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            onClick={startSession}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500"
          >
            Comenzar sesión
          </button>
        </div>
      </div>
    )
  }

  if (!question) return <p className="text-slate-400">Cargando pregunta...</p>

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <span className="text-xs uppercase tracking-wide text-indigo-400">{question.category}</span>
        <p className="mt-2 text-lg">{question.question_en}</p>
        <audio className="mt-3 w-full" controls src={api.questionAudioUrl(question.id)} />
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-5 space-y-3">
        <h2 className="text-sm font-medium text-slate-300">Tu respuesta</h2>

        {recorder.error && <p className="text-sm text-red-400">{recorder.error}</p>}

        <div className="flex gap-3">
          {recorder.status !== 'recording' ? (
            <button
              onClick={recorder.start}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium hover:bg-red-500"
            >
              ● Grabar
            </button>
          ) : (
            <button
              onClick={recorder.stop}
              className="rounded-md bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600"
            >
              ■ Detener
            </button>
          )}

          {recorder.audioBlob && !result && (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-50"
            >
              {submitting ? 'Evaluando...' : 'Enviar respuesta'}
            </button>
          )}

          {recorder.audioBlob && (
            <button
              onClick={recorder.reset}
              className="rounded-md px-4 py-2 text-sm text-slate-400 hover:text-slate-100"
            >
              Regrabar
            </button>
          )}
        </div>

        {recorder.audioBlob && (
          <audio className="w-full" controls src={URL.createObjectURL(recorder.audioBlob)} />
        )}
        {submitError && <p className="text-sm text-red-400">{submitError}</p>}
      </div>

      {result && <ResultPanel result={result} />}

      {question.reference && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-5">
          <button
            onClick={() => setShowReference((v) => !v)}
            className="text-sm font-medium text-indigo-400 hover:text-indigo-300"
          >
            {showReference ? 'Ocultar' : 'Ver'} respuesta sugerida
            {!question.reference.reviewed && ' (⚠ sin revisar)'}
          </button>
          {showReference && (
            <div className="mt-3 space-y-2 text-sm">
              <p>{question.reference.answer_en}</p>
              <ul className="list-disc pl-5 text-slate-400">
                {question.reference.keypoints.map((k, i) => (
                  <li key={i}>{k}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => loadNextQuestion(seenIds)}
        className="rounded-md border border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-800"
      >
        Siguiente pregunta →
      </button>
    </div>
  )
}

function ResultPanel({
  result,
}: {
  result: { transcript: string; objective: ObjectiveMetrics; llm_feedback: LlmFeedback | null }
}) {
  const { transcript, objective, llm_feedback } = result
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-5 space-y-4">
      <div>
        <h3 className="text-sm font-medium text-slate-300">Transcripción</h3>
        <p className="mt-1 text-slate-200">{transcript}</p>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <Stat label="Palabras/min" value={objective.words_per_minute.toFixed(0)} />
        <Stat label="Duración" value={`${objective.duration_seconds.toFixed(1)}s`} />
        <Stat label="Muletillas" value={String(objective.filler_count)} />
      </div>

      {llm_feedback?.error && <p className="text-sm text-amber-400">Evaluación por IA no disponible: {llm_feedback.error}</p>}

      {llm_feedback && !llm_feedback.error && (
        <div className="space-y-3 text-sm">
          {!!llm_feedback.grammar_corrections?.length && (
            <div>
              <h4 className="font-medium text-slate-300">Correcciones de gramática</h4>
              <ul className="mt-1 space-y-1">
                {llm_feedback.grammar_corrections.map((c, i) => (
                  <li key={i} className="text-slate-400">
                    <span className="line-through">{c.original}</span> → <span className="text-emerald-400">{c.suggested}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {llm_feedback.vocabulary_notes && (
            <p className="text-slate-400">
              <span className="font-medium text-slate-300">Vocabulario: </span>
              {llm_feedback.vocabulary_notes}
            </p>
          )}

          {!!llm_feedback.keypoints_missed?.length && (
            <p className="text-slate-400">
              <span className="font-medium text-slate-300">Puntos que no mencionaste: </span>
              {llm_feedback.keypoints_missed.join(', ')}
            </p>
          )}

          {!!llm_feedback.unsupported_claims?.length && (
            <p className="text-amber-400">
              ⚠ Posibles afirmaciones no respaldadas por tu perfil: {llm_feedback.unsupported_claims.join(', ')}
            </p>
          )}

          {llm_feedback.overall_note && <p className="italic text-slate-300">{llm_feedback.overall_note}</p>}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-800 py-3">
      <div className="text-xl font-semibold">{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  )
}

function ProgressView() {
  const [turns, setTurns] = useState<ProgressTurn[]>([])
  const [weakest, setWeakest] = useState<{ category: string; avg_wpm: number; attempts: number }[]>([])

  useEffect(() => {
    api.progress().then(setTurns).catch(() => setTurns([]))
    api.weakestCategories().then(setWeakest).catch(() => setWeakest([]))
  }, [])

  if (!turns.length) {
    return <p className="text-slate-400">Todavía no hay sesiones registradas. Practica una ronda primero.</p>
  }

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm font-medium text-slate-300">Categorías con menor fluidez (WPM promedio)</h2>
        <div className="space-y-2">
          {weakest.map((w) => (
            <div key={w.category} className="flex items-center justify-between rounded-md bg-slate-900 px-4 py-2 text-sm">
              <span>{w.category}</span>
              <span className="text-slate-400">
                {w.avg_wpm.toFixed(0)} wpm · {w.attempts} intento(s)
              </span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-slate-300">Historial reciente</h2>
        <div className="space-y-2">
          {turns.map((t) => (
            <div key={t.id} className="rounded-md bg-slate-900 p-4 text-sm">
              <div className="flex justify-between text-slate-400">
                <span>{t.category}</span>
                <span>{new Date(t.created_at * 1000).toLocaleString()}</span>
              </div>
              <p className="mt-1">{t.transcript}</p>
              <div className="mt-2 text-xs text-slate-500">
                {t.words_per_minute?.toFixed(0)} wpm · {t.filler_count} muletillas
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
