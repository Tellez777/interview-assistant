import { useCallback, useRef, useState } from 'react'

export type RecorderStatus = 'idle' | 'recording' | 'stopped'

/** Graba la respuesta hablada del usuario como un blob completo (no
 * streaming): se sube de una vez al backend, que la transcribe con
 * faster-whisper directo (ver backend/app/asr/transcribe_file.py). */
export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>('idle')
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [error, setError] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)

  const start = useCallback(async () => {
    setError(null)
    setAudioBlob(null)
    chunksRef.current = []
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        setAudioBlob(new Blob(chunksRef.current, { type: 'audio/webm' }))
        streamRef.current?.getTracks().forEach((t) => t.stop())
      }
      recorder.start()
      mediaRecorderRef.current = recorder
      setStatus('recording')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo acceder al micrófono')
    }
  }, [])

  const stop = useCallback(() => {
    mediaRecorderRef.current?.stop()
    setStatus('stopped')
  }, [])

  const reset = useCallback(() => {
    setStatus('idle')
    setAudioBlob(null)
    setError(null)
  }, [])

  return { status, audioBlob, error, start, stop, reset }
}
