import { useState } from 'react'
import { AnswerContent } from './AnswerContent'
import { useLiveSocket } from './useLiveSocket'

export default function LiveView() {
  const { connected, status, interviewerPartial, turns, start, stop, setFullAnswer } = useLiveSocket()

  const [running, setRunning] = useState(false)
  const [fullAnswerEnabled, setFullAnswerEnabled] = useState(false)
  const [showMetrics, setShowMetrics] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [language, setLanguage] = useState<'en' | 'es'>('en')
  const [activeLanguage, setActiveLanguage] = useState<'en' | 'es'>('en')

  async function handleStart() {
    setStartError(null)
    try {
      await start(language)
      setActiveLanguage(language)
      setRunning(true)
    } catch (err) {
      setRunning(false)
      setStartError(err instanceof Error ? err.message : 'No se pudo iniciar Live Mode')
    }
  }

  async function handleStop() {
    await stop()
    setRunning(false)
  }

  async function handleToggleFullAnswer(checked: boolean) {
    setFullAnswerEnabled(checked)
    await setFullAnswer(checked)
  }

  const lastTurn = turns[turns.length - 1]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div>
          <div className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
            <span className="text-slate-300">{connected ? 'Conectado' : 'Sin conexión'}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">{status}</p>
        </div>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            Idioma:
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as 'en' | 'es')}
              disabled={running}
              className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm text-slate-200 disabled:opacity-50"
            >
              <option value="en">Inglés</option>
              <option value="es">Español</option>
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={fullAnswerEnabled}
              onChange={(e) => handleToggleFullAnswer(e.target.checked)}
              className="h-4 w-4"
            />
            Respuesta completa (⚠ apagado = más seguro)
          </label>

          {!running ? (
            <button
              onClick={handleStart}
              disabled={!connected}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
            >
              ● Iniciar Live Mode
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium hover:bg-red-500"
            >
              ■ Detener
            </button>
          )}
        </div>
      </div>

      {startError && <p className="text-sm text-red-400">{startError}</p>}

      {!running && !startError && (
        <p className="text-sm text-slate-500">
          Al iniciar, el backend captura el audio del sistema (loopback) directamente — no hace falta compartir el
          micrófono del navegador. Colócate esta pestaña junto a tu videollamada.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Panel title={activeLanguage === 'es' ? '🎙 Entrevistador (ES)' : '🎙 Entrevistador (EN)'}>
          <p className="text-slate-200">
            {lastTurn?.finalEn}
            <span className="text-slate-500"> {interviewerPartial}</span>
          </p>
        </Panel>

        <Panel title={activeLanguage === 'es' ? '🇺🇸 Traducción (inglés)' : '🇲🇽 Traducción'}>
          <p className="text-slate-200">{lastTurn?.translationEs}</p>
        </Panel>
      </div>

      <Panel title="💡 Palabras clave">
        {lastTurn?.keypoints.length ? (
          <div>
            <ul className="list-disc space-y-1 pl-5 text-slate-200">
              {lastTurn.keypoints.map((k, i) => (
                <li key={i}>{k}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-500">
              del banco: {lastTurn.keypointsSource ?? '—'} (score {lastTurn.keypointsScore.toFixed(2)})
            </p>
          </div>
        ) : (
          <p className="text-slate-500">—</p>
        )}
      </Panel>

      {fullAnswerEnabled && (
        <Panel title={lastTurn?.answerMode === 'technical' ? '💻 Respuesta técnica' : '📝 Respuesta sugerida'}>
          {lastTurn?.answerMode ? (
            <div>
              <span className="mb-2 inline-block rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                {lastTurn.answerMode === 'cached'
                  ? 'del banco revisado'
                  : lastTurn.answerMode === 'technical'
                    ? 'modelo técnico (pregunta de código detectada)'
                    : 'generada ahora'}
              </span>
              <AnswerContent text={lastTurn.answerText} />
            </div>
          ) : (
            <p className="text-slate-500">—</p>
          )}
        </Panel>
      )}

      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <button
          onClick={() => setShowMetrics((v) => !v)}
          className="text-sm font-medium text-indigo-400 hover:text-indigo-300"
        >
          {showMetrics ? 'Ocultar' : 'Ver'} métricas de latencia
        </button>
        {showMetrics && (
          <div className="mt-3 space-y-2 text-xs text-slate-400">
            {turns
              .slice()
              .reverse()
              .map((t) =>
                t.marksMs ? (
                  <div key={t.turnId} className="flex gap-4">
                    {Object.entries(t.marksMs).map(([label, ms]) => (
                      <span key={label}>
                        {label}: {ms.toFixed(0)}ms
                      </span>
                    ))}
                  </div>
                ) : null,
              )}
          </div>
        )}
      </div>
    </div>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h3 className="mb-2 text-xs uppercase tracking-wide text-indigo-400">{title}</h3>
      {children}
    </div>
  )
}
