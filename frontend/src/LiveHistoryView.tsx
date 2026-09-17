import { useEffect, useState } from 'react'
import { AnswerContent } from './AnswerContent'
import { api, type LiveSessionSummary, type LiveTurnRecord } from './api'

export default function LiveHistoryView() {
  const [sessions, setSessions] = useState<LiveSessionSummary[]>([])
  const [selectedSession, setSelectedSession] = useState<string | null>(null)
  const [turns, setTurns] = useState<LiveTurnRecord[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.liveSessions().then(setSessions).catch(() => setSessions([]))
  }, [])

  useEffect(() => {
    setLoading(true)
    api
      .liveTurns(selectedSession)
      .then(setTurns)
      .catch(() => setTurns([]))
      .finally(() => setLoading(false))
  }, [selectedSession])

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">
        Cada turno del entrevistador en Live Mode queda guardado aquí — transcripción, traducción, keypoints y la
        respuesta sugerida — para poder revisar después qué tan bien funcionó, no solo confiar en la memoria.
      </p>

      <div>
        <h2 className="mb-2 text-sm font-medium text-slate-300">Sesiones</h2>
        <div className="flex flex-wrap gap-2">
          <SessionChip
            active={selectedSession === null}
            onClick={() => setSelectedSession(null)}
            label="Todas"
          />
          {sessions.map((s) => (
            <SessionChip
              key={s.id}
              active={selectedSession === s.id}
              onClick={() => setSelectedSession(s.id)}
              label={`${new Date(s.started_at * 1000).toLocaleString()} · ${s.turn_count} turno(s) · ${
                s.language === 'es' ? 'ES' : 'EN'
              }`}
            />
          ))}
        </div>
      </div>

      {loading && <p className="text-sm text-slate-500">Cargando...</p>}

      {!loading && turns.length === 0 && (
        <p className="text-sm text-slate-500">Sin turnos registrados todavía. Usa Live Mode primero.</p>
      )}

      <div className="space-y-4">
        {turns
          .slice()
          .reverse()
          .map((t) => (
            <TurnCard key={t.id} turn={t} />
          ))}
      </div>
    </div>
  )
}

function SessionChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs ${
        active ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'
      }`}
    >
      {label}
    </button>
  )
}

function TurnCard({ turn }: { turn: LiveTurnRecord }) {
  const languageWarning = turn.answer_language_ok === 0
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{new Date(turn.created_at * 1000).toLocaleString()}</span>
        {turn.error && <span className="text-red-400">⚠ {turn.error}</span>}
      </div>

      <div>
        <div className="text-xs uppercase tracking-wide text-indigo-400">Entrevistador (EN)</div>
        <p className="text-slate-200">{turn.question_en}</p>
      </div>

      {turn.translation_es && (
        <div>
          <div className="text-xs uppercase tracking-wide text-indigo-400">Traducción</div>
          <p className="text-slate-300">{turn.translation_es}</p>
        </div>
      )}

      {!!turn.keypoints?.length && (
        <div>
          <div className="text-xs uppercase tracking-wide text-indigo-400">Keypoints</div>
          <ul className="list-disc pl-5 text-slate-300">
            {turn.keypoints.map((k, i) => (
              <li key={i}>{k}</li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-slate-500">
            banco: {turn.keypoints_source_id ?? '—'} (score {turn.keypoints_score?.toFixed(2) ?? '—'})
          </p>
        </div>
      )}

      {turn.answer_text && (
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-indigo-400">
            {turn.answer_mode === 'technical' ? 'Respuesta técnica' : 'Respuesta sugerida'}
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] normal-case text-slate-400">
              {turn.answer_mode === 'cached'
                ? 'del banco'
                : turn.answer_mode === 'technical'
                  ? 'modelo técnico'
                  : 'generada'}
            </span>
            {languageWarning && (
              <span className="rounded bg-red-900/60 px-1.5 py-0.5 text-[10px] normal-case text-red-300">
                ⚠ salió en "{turn.answer_language}", no en inglés
              </span>
            )}
          </div>
          <AnswerContent text={turn.answer_text} />
        </div>
      )}

      {turn.marks_ms && (
        <div className="flex gap-4 text-xs text-slate-500">
          {Object.entries(turn.marks_ms).map(([label, ms]) => (
            <span key={label}>
              {label}: {ms.toFixed(0)}ms
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
