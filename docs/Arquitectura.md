# Arquitectura y estructura del proyecto

Referencia técnica completa del proyecto: qué hace cada módulo, cómo se
conectan, y las decisiones de diseño detrás de cada parte. Para el
concepto general ver `Idea_Inicial.md`; para pendientes conocidos ver
`Backlog.md`.

---

## 1. Resumen

El proyecto tiene dos modos, que comparten la misma base de datos del
candidato y el mismo backend:

- **Practice Mode**: simulador de entrevista sin presión de tiempo real.
  El backend hace una pregunta (con voz sintética), graba y transcribe la
  respuesta hablada, y da retroalimentación objetiva (ritmo, muletillas)
  y de contenido (vía LLM, comparando contra una respuesta de referencia
  ya revisada).
- **Live Mode**: asistencia durante una entrevista real. Captura el audio
  del sistema (lo que se escucha por los parlantes/audífonos, no el
  micrófono), transcribe en tiempo real lo que pregunta el entrevistador,
  lo traduce, busca una respuesta relevante en un banco propio, y si no
  hay una buena coincidencia, genera una con un LLM — todo transmitido
  por WebSocket a la interfaz mientras ocurre.

Inferencia híbrida a propósito: el reconocimiento de voz (ASR) corre
**local, en GPU**, porque es la parte más sensible a la latencia y no
tiene sentido pagar por una API para eso. La generación de texto (LLM)
corre **por API** (Anthropic o cualquier endpoint compatible con OpenAI),
porque ahí la calidad del modelo importa más que unos cientos de
milisegundos, y correr un LLM competente en local no es viable con una
GPU de 4 GB.

---

## 2. Stack tecnológico

### Backend (`backend/`, Python 3.12, FastAPI)

| Pieza | Librería | Para qué |
|---|---|---|
| API HTTP + WebSocket | `fastapi`, `uvicorn` | servidor único para ambos modos |
| ASR en tiempo real | `RealtimeSTT` (sobre `faster-whisper`/CTranslate2) | streaming con detección de voz (VAD) integrada |
| ASR de archivo completo | `faster-whisper` directo | transcribir el audio ya grabado de Practice Mode |
| Captura de audio del sistema | `PyAudioWPatch` (WASAPI loopback) | escuchar lo que suena por los parlantes, no el micrófono |
| Traducción | `argostranslate` (CTranslate2 por debajo) | EN↔ES, en CPU, sin costo por llamada |
| Búsqueda semántica | `sentence-transformers` (`all-MiniLM-L6-v2`) | encontrar la respuesta más parecida en el banco |
| LLM | `anthropic` / `openai` (SDKs oficiales) | generación de respuestas y evaluación |
| Texto a voz | `edge-tts` | pronunciar las preguntas en Practice Mode |
| Detección de idioma | `langdetect` | verificar que la respuesta salió en el idioma esperado |
| Persistencia | `sqlite3` (stdlib) | historial de sesiones, sin servidor de BD aparte |
| Config | `pydantic-settings` | lee `.env`, valores tipados |

### Frontend (`frontend/`, React + TypeScript + Vite + Tailwind)

Sin librería de estado externa (Redux, etc.) — todo con `useState`/hooks
propios, justificado por el tamaño de la app. Un solo `WebSocket` para
Live Mode, `fetch` normal para todo lo demás vía el proxy de Vite.

---

## 3. Estructura de directorios

```
Proyecto-Asistente/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI: todas las rutas HTTP + el WebSocket
│   │   ├── config.py            # Settings (pydantic-settings), lee .env
│   │   ├── metrics.py           # Timeline: medición de latencia por etapa
│   │   ├── cuda_dlls.py         # workaround de carga de DLLs CUDA en Windows
│   │   ├── audio/
│   │   │   ├── devices.py       # enumerar micrófono(s) y loopback WASAPI
│   │   │   └── capture.py       # captura de audio, resample, keepalive
│   │   ├── asr/
│   │   │   ├── transcriber.py   # wrapper de RealtimeSTT (streaming, Live Mode)
│   │   │   └── transcribe_file.py # faster-whisper directo (archivo completo, Practice Mode)
│   │   ├── translation/
│   │   │   └── translate.py     # wrapper de argostranslate (EN→ES y ES→EN)
│   │   ├── llm/
│   │   │   ├── base.py          # Protocol LLMClient + factory get_default_client()
│   │   │   ├── anthropic_client.py
│   │   │   └── openai_compat.py # OpenAI real o cualquier gateway compatible
│   │   ├── profile/
│   │   │   └── schema.py        # CandidateProfile (pydantic) — la fuente de verdad
│   │   ├── answers/
│   │   │   ├── generate.py      # script offline: preguntas -> banco de respuestas
│   │   │   ├── store.py         # construye el índice de embeddings
│   │   │   └── retrieve.py      # búsqueda semántica sobre el índice
│   │   ├── practice/
│   │   │   ├── session.py       # elegir siguiente pregunta
│   │   │   ├── evaluate.py      # métricas objetivas + evaluación por LLM
│   │   │   ├── tts.py           # sintetizar audio de la pregunta
│   │   │   └── db.py            # historial de sesiones de práctica (SQLite)
│   │   └── live/
│   │       ├── manager.py       # ciclo de vida de la sesión Live (hilos, WASAPI)
│   │       ├── pipeline.py      # qué pasa cuando cierra un turno del entrevistador
│   │       ├── events.py        # forma de los mensajes del WebSocket
│   │       └── db.py            # historial de sesiones Live (SQLite)
│   ├── data/
│   │   ├── profile.example.json     # plantilla en blanco (el real es profile.json, gitignored)
│   │   ├── questions.example.yaml   # banco de preguntas genérico
│   │   └── answers/
│   │       └── _SCHEMA.example.json # forma de una respuesta generada
│   ├── scripts/
│   │   └── check_env.py         # diagnóstico: audio, CUDA, benchmark de ASR
│   └── pyproject.toml
└── frontend/
    ├── vite.config.ts           # proxy /api -> backend, server.host para LAN
    └── src/
        ├── App.tsx              # shell + pestañas + PracticeView + ProgressView
        ├── api.ts                # cliente fetch tipado sobre la API del backend
        ├── useRecorder.ts        # grabar audio del navegador (Practice Mode)
        ├── useLiveSocket.ts      # conexión WebSocket + estado de Live Mode
        ├── LiveView.tsx          # paneles en vivo (transcripción/traducción/respuesta)
        ├── LiveHistoryView.tsx   # historial de sesiones Live pasadas
        └── AnswerContent.tsx     # render compartido de texto con bloques de código
```

---

## 4. Arquitectura general

### Practice Mode — flujo de un turno

```
Frontend                         Backend
--------                         -------
GET /api/practice/questions/next  → elige pregunta (session.py), adjunta
                                     la respuesta de referencia del banco
GET /api/practice/questions/{id}/audio
                                   → sintetiza con edge-tts (cacheado en disco)
(usuario graba con MediaRecorder
 del navegador → blob webm/opus)
POST /api/practice/sessions/{id}/turns
  (audio subido completo)         → guarda a disco temporalmente
                                   → faster-whisper transcribe el archivo completo
                                   → métricas objetivas (wpm, muletillas) sin LLM
                                   → si hay respuesta de referencia: LLM compara
                                     (gramática, vocabulario, keypoints, afirmaciones
                                     no respaldadas por el perfil)
                                   → guarda el turno en practice.db
                                   ← devuelve transcripción + métricas + feedback
```

No hay streaming aquí: el audio se sube completo de una vez, así que
transcribir con `faster-whisper` directo (sin la maquinaria de VAD de
RealtimeSTT) es suficiente y más simple.

### Live Mode — flujo de un turno

```
1. El navegador abre un WebSocket a /api/live/stream y llama
   POST /api/live/sessions/start (con language=en|es).
2. app.live.manager.LiveSession.start():
   - elige modelo de ASR según el idioma (modelos .en son solo-inglés;
     en modo "es" se cargan los multilingües)
   - arranca 3 hilos:
     a) capture_loop:  PyAudioWPatch (loopback) -> resample a 16kHz mono -> feed_audio()
     b) final_loop:    espera a que RealtimeSTT cierre un turno (VAD) -> agenda el pipeline
     c) keepalive:     reproduce silencio digital para que WASAPI no deje de entregar audio
3. Al cerrar un turno (final_loop), se agenda app.live.pipeline.handle_interviewer_turn()
   en el event loop de asyncio (el resto corría en hilos normales).
4. pipeline.py, para ese turno:
   - en paralelo: traduce el texto + busca en el banco (retrieval semántico)
   - emite eventos "translation_es" y "keypoints" al WebSocket ya con esto
   - si "respuesta completa" está activado:
     - si la pregunta es técnica (regex) -> modelo LLM más grande + prompt técnico
     - si hay una coincidencia fuerte y revisada en el banco -> se usa esa respuesta directo (sin LLM)
     - si no -> LLM conversacional en streaming, con el perfil completo como contexto
     - emite "answer_start" / "answer_chunk" (por cada delta) / "answer_done"
   - guarda cada etapa en live.db conforme va llegando (no todo de una vez)
5. El frontend (useLiveSocket.ts) arma el estado de cada turno a partir
   de esos eventos y LiveView.tsx los pinta en tiempo real.
```

La captura de audio **nunca pasa por el navegador** en Live Mode — el
backend corre en la misma laptop que la videollamada y captura
directamente con `PyAudioWPatch`. El WebSocket solo transporta texto y
eventos, nunca audio.

---

## 5. Backend, módulo por módulo

### `config.py`
`Settings` (pydantic-settings) lee `backend/.env`. Todo lo parametrizable
vive aquí — proveedor de LLM, modelos de ASR (normal y variante
multilingüe para español), rutas de datos. Nada de leer `os.environ`
suelto en otros archivos.

### `cuda_dlls.py`
Windows-only. Los paquetes `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`
instalados vía pip dejan las DLLs dentro de `site-packages`, pero el
cargador de DLL de Windows no las encuentra ahí por defecto (a diferencia
de Linux, que usa RPATH). CTranslate2 además carga esas DLLs con una
llamada nativa que ignora `os.add_dll_directory`, así que hace falta
además prependear esas carpetas al `PATH` del proceso. Se llama una vez
al importar `app.asr`.

### `audio/devices.py`
Enumera dispositivos de entrada normales (micrófono) y dispositivos
**loopback WASAPI** (lo que suena por una salida de audio, capturable
como si fuera una entrada). `get_default_loopback()` es lo que permite
escuchar al entrevistador en una llamada de Zoom/Meet sin que nadie
comparta su micrófono.

### `audio/capture.py`
- `to_mono_16k_pcm16()`: downmix a mono + resample a 16kHz con
  `scipy.signal.resample_poly`. Necesario porque `RealtimeSTT.feed_audio()`
  con `bytes` crudos **ignora el sample rate declarado** y asume que ya
  vienen en 16kHz mono — sin esta conversión, el ASR "escucha" el audio a
  la velocidad y tono equivocados.
- `play_silence_keepalive()`: reproduce silencio digital en la salida por
  defecto mientras Live Mode está activo. Sin esto, WASAPI deja de
  entregar buffers al stream de loopback en cuanto nada suena en el
  sistema (`stream.read()` se bloquea indefinidamente), y un turno nunca
  llega a cerrar por silencio real.
- `stream_chunks()`: generador infinito (o hasta que se marque un
  `threading.Event`) de chunks PCM crudos — lo que alimenta
  `feed_audio()` en Live Mode.
- `record_to_wav()`: grabación simple usada por el script de diagnóstico.

### `asr/transcriber.py`
Wrapper sobre `RealtimeSTT.AudioToTextRecorder`, configurado para audio
externo (`use_microphone=False`, se le alimenta con `feed_audio()`). Dos
notas de configuración no obvias:
- **Nunca pasar `silero_use_onnx=True` explícito** — contraintuitivamente
  fuerza el backend "legacy" de RealtimeSTT, que pasa por `torch.hub.load`
  y pide confirmación interactiva (`input()`), lo cual truena con
  `EOFError` en un proceso de servidor. Dejar el parámetro sin pasar usa
  el backend "auto", que prueba primero el paquete pip `silero-vad`
  (offline, sin confirmación).
- `post_speech_silence_duration` en 1.1s: valores más bajos (probado con
  0.6s) cortan preguntas largas en varios turnos ante cualquier pausa
  natural del habla.
- Acepta `model`/`realtime_model` como overrides explícitos — Live Mode
  en español carga los modelos multilingües (`small`/`tiny`) en vez de
  los especializados en inglés (`small.en`/`tiny.en`, que no pueden
  transcribir ningún otro idioma).

### `asr/transcribe_file.py`
`faster-whisper` directo, sin la maquinaria de streaming/VAD — para
Practice Mode, donde el audio ya llegó completo. Si el device configurado
(p. ej. `cuda`) falla al cargar, cae a CPU automáticamente en vez de
tumbar el endpoint.

### `translation/translate.py`
Wrapper sobre `argostranslate`. Soporta ambas direcciones (`en→es` para
Live Mode en inglés, `es→en` para Live Mode en español, donde se necesita
traducir la pregunta antes de poder buscarla en el banco). Cada dirección
instala su paquete de idioma una sola vez (cacheado localmente por
argostranslate) e idempotente en cada arranque del servidor.

### `profile/schema.py`
`CandidateProfile` (pydantic): experiencia, proyectos, historias en
formato STAR, y — igual de importante — `gaps[]`, brechas conocidas
frente a una vacante, cada una con su propia "respuesta puente" honesta
ya redactada. Esto es lo que evita que el LLM invente experiencia que no
existe: en vez de dejarlo improvisar sobre un hueco, se le da
explícitamente qué decir ahí. `as_context_block()` serializa todo a texto
plano para inyectarlo en los prompts.

### `answers/generate.py`
Script offline (se corre a mano, no en caliente): por cada pregunta de
`questions.yaml`, le pide al LLM una respuesta fundamentada únicamente en
el perfil, y la guarda como un **borrador** en `data/answers/<id>.json`
con `"reviewed": false`. El banco no se usa en producción hasta que cada
entrada se revisa y se corrige a mano — es el guion real de la persona,
no algo que el modelo deba decidir solo.

### `answers/store.py`
Construye el índice de búsqueda: embeddings de cada pregunta (con
`sentence-transformers`, CPU, ~80MB de modelo) guardados en
`embeddings.npy` + metadata en `index.json`. Se reconstruye cada vez que
cambia el banco.

### `answers/retrieve.py`
Búsqueda semántica: dado un texto, devuelve las entradas más parecidas
por similitud coseno (embeddings ya normalizados, así que es un producto
punto). Del orden de milisegundos una vez el modelo está cargado en
memoria — esto es lo que reemplaza al "detector de intención" +
"prefetch" de un diseño más ingenuo: en vez de clasificar la pregunta en
una categoría fija de antemano, se busca directo por parecido.

### `llm/base.py`
`Protocol LLMClient` con `chat()` (respuesta completa) y `stream_chat()`
(streaming, usado en Live Mode). `get_default_client(model=None)`
instancia el proveedor configurado en `Settings.llm_provider`
(`anthropic` u `openai_compat`); `model` permite override puntual — lo
usa Live Mode para mandar las preguntas técnicas a un modelo más grande
que el conversacional rápido.

### `llm/anthropic_client.py` / `llm/openai_compat.py`
Implementaciones concretas. `openai_compat` sirve tanto para la API real
de OpenAI como para cualquier gateway compatible (Groq, un proxy propio,
etc.) — si no se da `base_url`, usa la URL real de OpenAI. Detalle no
obvio del streaming: los eventos vienen con el texto en `event.delta`,
no en `event.content` (un error fácil de cometer que falla en silencio
si nadie inspecciona el tipo de evento).

### `practice/session.py`
Selección de la siguiente pregunta: filtra por categoría si se pidió,
excluye las ya vistas en la sesión (permite repetir si ya se agotaron
todas). Deliberadamente simple — la categoría la elige la persona en la
UI, no hace falta detectarla.

### `practice/evaluate.py`
Dos capas de evaluación:
1. **Objetiva, sin LLM**: palabras por minuto (de la transcripción y la
   duración del audio), conteo de muletillas por regex sobre una lista
   fija (`um`, `uh`, `like`, `you know`, etc.).
2. **Por LLM**: compara la respuesta hablada contra la respuesta de
   referencia del banco — correcciones de gramática, notas de
   vocabulario, qué puntos clave se mencionaron y cuáles no, y una alerta
   si se afirmó algo que no está respaldado por el perfil.

### `practice/tts.py`
`edge-tts` (voz neural gratuita, sin API key) para pronunciar cada
pregunta. El audio se cachea en disco por pregunta la primera vez que se
pide.

### `practice/db.py` / `live/db.py`
SQLite plano (stdlib), mismo patrón en ambos: un `contextmanager` para la
conexión, `init_db()` idempotente, tablas de sesiones y de turnos.
`live/db.py` guarda cada turno **en dos pasos** (al cerrar la
transcripción, y de nuevo según van llegando traducción/keypoints/
respuesta) para que un turno cancelado a medio camino quede con lo que sí
alcanzó a completarse, en vez de perderse por completo.

### `live/manager.py`
`LiveSession`: una sola sesión global (no hace falta multi-tenant, solo
hay una entrevista a la vez en la máquina). `start()` es idempotente — si
ya había una sesión corriendo, la detiene y levanta una limpia en vez de
rechazar con un error, para poder repetir pruebas manuales sin reiniciar
el servidor. `stop()` incluye una red de seguridad que mata a mano los
procesos worker de RealtimeSTT si `recorder.shutdown()` no lo hizo — se
detectó fuga de VRAM real (con `nvidia-smi`) tras varios ciclos de
arranque/apagado sin esto.

### `live/pipeline.py`
La lógica de "qué hacer con un turno ya cerrado del entrevistador" — ver
la sección de flujo arriba. Puntos de diseño no obvios:
- **Retrieval primero, LLM como respaldo**: si hay una coincidencia
  fuerte (umbral de similitud) y esa entrada del banco ya fue revisada,
  se usa directo, sin llamar al LLM — más rápido y más fiel a lo que la
  persona ya aprobó.
- **Modo técnico**: una heurística por regex detecta preguntas de código
  ("write a SQL query", "how would you implement...") y las manda a un
  modelo distinto (configurable, típicamente uno más grande) con un
  prompt que sí permite bloques de código y profundidad técnica real —
  nunca se responde una pregunta técnica con una entrada cacheada del
  banco conversacional.
- **Anti-repetición**: se le pasa al LLM qué respuestas/historias se
  usaron recientemente en la misma sesión, con la instrucción de variar
  si hay otra opción igual de válida.
- **Bilingüe (EN/ES)**: todo el pipeline toma un parámetro de idioma.
  En modo español, la pregunta (ya transcrita en español) se traduce a
  inglés una vez, y ese resultado sirve dos veces: como texto mostrado en
  el panel de traducción, y como query para buscar en el banco (que sigue
  indexado en inglés). Sacrifica el paralelismo traducción+búsqueda que
  sí existe en modo inglés (ahí no hace falta, la pregunta ya está en el
  idioma del índice).
- **Manejo de errores no silencioso**: toda la función está envuelta en
  un `try/except` que loguea el traceback completo y emite un evento de
  error al frontend. Se agregó después de un bug real donde una excepción
  dentro de una corrutina agendada con `asyncio.run_coroutine_threadsafe`
  desaparecía sin dejar rastro (nadie llamaba `.result()` sobre el
  `Future`).

### `live/events.py`
Los mensajes del WebSocket son dicts simples (no pydantic — son de un
solo uso, no se validan ni persisten tal cual). Tipos: `status`,
`partial_en`, `final_en`, `translation_es`, `keypoints`, `answer_start`,
`answer_chunk`, `answer_done`, `metrics`, `error`.

### `main.py`
Todas las rutas HTTP + el único endpoint WebSocket.

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/health` | chequeo simple |
| GET | `/api/profile` | perfil completo |
| GET | `/api/categories` | categorías de preguntas disponibles |
| POST | `/api/practice/sessions` | nueva sesión de práctica |
| GET | `/api/practice/questions/next` | siguiente pregunta (+ referencia) |
| GET | `/api/practice/questions/{id}/audio` | TTS de la pregunta (cacheado) |
| POST | `/api/practice/sessions/{id}/turns` | sube audio, transcribe, evalúa |
| GET | `/api/practice/progress` | historial |
| GET | `/api/practice/progress/weakest` | categorías con menor fluidez |
| POST | `/api/live/sessions/start` | arranca Live Mode (`language=en\|es`) |
| POST | `/api/live/sessions/stop` | detiene Live Mode |
| POST | `/api/live/sessions/full-answer` | prende/apaga la respuesta completa |
| GET | `/api/live/sessions/status` | estado actual |
| WS | `/api/live/stream` | eventos en vivo |
| GET | `/api/live/sessions` | historial de sesiones Live |
| GET | `/api/live/turns` | historial de turnos Live |

### `metrics.py`
`Timeline`: registra hitos con timestamp relativo dentro de un turno
(fin de habla, primera traducción, primer token de respuesta, etc.) y
calcula tanto el tiempo acumulado como el delta entre etapas. La métrica
que importa no es el tiempo total, es cuánto tarda en aparecer la primera
información útil.

---

## 6. Frontend, módulo por módulo

### `api.ts`
Cliente delgado sobre la API — interfaces TypeScript que espejan los
modelos del backend, y funciones `fetch` tipadas. Sin librería de HTTP
externa.

### `useRecorder.ts`
Graba con `MediaRecorder` del navegador (Practice Mode): pide permiso de
micrófono, acumula chunks, arma un blob `webm` al detener. Sube el blob
completo — no hay streaming del lado del navegador.

### `useLiveSocket.ts`
Abre el `WebSocket` a `/api/live/stream` y arma el estado de cada turno a
partir de los eventos que van llegando (parcial → final → traducción →
keypoints → respuesta en streaming por deltas → métricas). `start()`
manda el idioma elegido como query param; el backend es idempotente, así
que nunca debería devolver un error de "ya hay una sesión activa".

### `AnswerContent.tsx`
Componente compartido entre `LiveView` y `LiveHistoryView`: parsea texto
que puede traer bloques de código en fences triple-backtick (el modo
técnico los incluye así) y renderiza cada bloque en monospace, el resto
como párrafos normales. Tolera un fence todavía sin cerrar mientras la
respuesta sigue en streaming.

### `App.tsx`
El shell de la app: header + navegación por pestañas (`practice`,
`progress`, `live`, `live-history`) y dos vistas definidas ahí mismo:
- `PracticeView`: el ciclo completo de una sesión de práctica — elegir
  categoría, escuchar la pregunta, grabar, enviar, ver resultado
  (transcripción, métricas objetivas, feedback del LLM), ver la respuesta
  de referencia opcionalmente.
- `ProgressView`: categorías con menor fluidez promedio + historial
  reciente de turnos.

### `LiveView.tsx`
Los paneles en vivo: transcripción del entrevistador, traducción,
palabras clave, y (detrás de un toggle apagado por defecto) la respuesta
sugerida completa — con su etiqueta cambiando entre "Respuesta sugerida"
y "Respuesta técnica" según el modo detectado. Incluye el selector de
idioma (inglés/español) que se bloquea una vez la sesión está corriendo,
y un panel colapsable de métricas de latencia por turno.

### `LiveHistoryView.tsx`
Lista de sesiones Live pasadas (chips, filtrable) y sus turnos completos
— transcripción, traducción, keypoints, respuesta, con una marca visible
si la respuesta salió en un idioma distinto al esperado.

---

## 7. Decisiones de arquitectura clave

- **Retrieval antes que generación.** Un banco de respuestas propio,
  revisado a mano, consultado por embeddings, es más rápido y más fiel
  que generar todo con un LLM en el momento. El LLM es el respaldo para
  lo que el banco no cubre, no el camino principal.
- **ASR local, LLM por API.** La latencia importa mucho más en la
  transcripción (tiene que sentirse en tiempo real) que en la generación
  de texto (unos segundos son aceptables si la calidad es buena). Correr
  el ASR en la GPU local es viable con 4GB de VRAM; correr un LLM
  competente local no lo es.
- **Sin detector de intención ni prefetch especulativo.** El perfil
  completo cabe en el prompt y la búsqueda semántica resuelve en
  milisegundos — clasificar la pregunta en una categoría fija de
  antemano no ahorra nada medible y agrega una pieza más que puede
  fallar.
- **Una sola sesión Live global.** Solo hay una entrevista a la vez en la
  máquina — un registro de sesiones concurrentes sería complejidad sin
  uso real.
- **Captura de audio 100% en el backend.** El WebSocket transporta texto,
  nunca audio — evita la complejidad y la latencia de subir audio en
  streaming desde el navegador.
- **"Respuesta completa" apagada por defecto.** Ver una respuesta
  completa sugerida en vivo y leerla textualmente es lo que más empresas
  consideran motivo de descarte si se nota — el valor real está en la
  traducción y las palabras clave; la respuesta completa es una ayuda
  adicional, no el modo por defecto.

---

## 8. Limitaciones conocidas

- **Asume una sola voz en el audio capturado.** Si hay más de una persona
  hablando por el mismo canal de audio (p. ej. un panel de
  entrevistadores), el sistema no tiene forma de distinguir quién habla
  — ver `Feedback_Uso_Real.md` y `Backlog.md` para el detalle y el plan
  de solución.
- **Los modelos `.en` de Whisper no son multilingües** — son pesos
  distintos, no una bandera de idioma. Cambiar de idioma en Live Mode
  implica cargar un modelo distinto, no solo pasar otro parámetro.
- **Ventana de Windows/OneDrive.** Si el proyecto vive dentro de una
  carpeta sincronizada con OneDrive, instalar paquetes grandes (PyTorch)
  es mucho más lento porque cada archivo pasa por el filtro de
  sincronización.
- **`torch` CPU-only por defecto rompe la selección de GPU.**
  `RealtimeSTT` decide el device vía `torch.cuda.is_available()`,
  ignorando el `device="cuda"` explícito si el build de `torch`
  instalado no tiene soporte CUDA — que es lo que trae `pip install` por
  defecto en Windows. Hay que reinstalar el build con CUDA a mano después
  de cualquier `pip install -e .` limpio.

---

## 9. Configuración

Variables relevantes de `backend/.env` (ver `.env.example`):

| Variable | Qué controla |
|---|---|
| `LLM_PROVIDER` | `anthropic` o `openai_compat` |
| `ANTHROPIC_API_KEY` | si el proveedor es Anthropic |
| `OPENAI_COMPAT_BASE_URL` / `_API_KEY` / `_MODEL` | si el proveedor es OpenAI o un gateway compatible |
| `OPENAI_COMPAT_TECHNICAL_MODEL` | modelo más grande para preguntas técnicas en Live Mode (vacío = usa el mismo de siempre) |
| `ASR_DEVICE` / `ASR_COMPUTE_TYPE` | `cuda`/`cpu`, precisión de faster-whisper |
| `ASR_MODEL` / `ASR_REALTIME_MODEL` | modelos en inglés (`small.en`/`tiny.en` por defecto) |
| `ASR_MODEL_ES` / `ASR_REALTIME_MODEL_ES` | variantes multilingües para Live Mode en español |
| `APP_HOST` / `APP_PORT` | binding del servidor (`0.0.0.0` para acceso desde la red local) |
| `DATA_DIR` | dónde viven perfil, banco de respuestas y las bases SQLite |

Ver `README.md` para los pasos de arranque.
