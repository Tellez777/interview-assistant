/** Renderiza texto que puede traer bloques de código en fences (```) —
 * los mensajes del modelo técnico los incluyen así (ver TECHNICAL_SYSTEM_PROMPT
 * en el backend). El resto del texto se muestra como párrafo normal,
 * preservando saltos de línea. Mientras la respuesta sigue en streaming y
 * un fence todavía no cierra, esa parte simplemente se ve como texto
 * plano hasta que cierre — no rompe nada, solo tarda en formatearse.
 *
 * Compartido entre LiveView (en vivo) y LiveHistoryView (historial). */
export function AnswerContent({ text }: { text: string }) {
  const fenceRegex = /```(\w*)\n?([\s\S]*?)```/g
  const nodes: React.ReactNode[] = []
  let lastIndex = 0
  let key = 0
  let match: RegExpExecArray | null
  while ((match = fenceRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(
        <p key={key++} className="whitespace-pre-wrap text-slate-200">
          {text.slice(lastIndex, match.index)}
        </p>,
      )
    }
    nodes.push(
      <pre key={key++} className="my-2 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-emerald-300">
        <code>{match[2].replace(/\n$/, '')}</code>
      </pre>,
    )
    lastIndex = fenceRegex.lastIndex
  }
  if (lastIndex < text.length) {
    nodes.push(
      <p key={key++} className="whitespace-pre-wrap text-slate-200">
        {text.slice(lastIndex)}
      </p>,
    )
  }
  return <div className="space-y-1">{nodes}</div>
}
