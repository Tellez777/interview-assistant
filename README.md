# Asistente de Entrevistas

Herramienta de práctica y asistencia en tiempo real para entrevistas de
trabajo. Dos modos:

- **Practice Mode**: simula una entrevista completa — hace preguntas por
  categoría, las pronuncia con voz sintética, graba y transcribe tu
  respuesta hablada, y da retroalimentación objetiva (ritmo, muletillas)
  y de contenido (vía LLM, comparando contra una respuesta de referencia
  que tú mismo revisaste de antemano).
- **Live Mode**: durante una entrevista real, escucha el audio del
  sistema (lo que dice el entrevistador por la videollamada, no tu
  micrófono), lo transcribe y traduce en tiempo real, busca una respuesta
  relevante en tu propio banco de respuestas, y si no hay una buena
  coincidencia, genera una con un LLM — todo mostrado en vivo mientras
  ocurre.

Ver `docs/Idea_Inicial.md` para el concepto detrás del proyecto,
`docs/Arquitectura.md` para la referencia técnica completa (módulo por
módulo), y `docs/Backlog.md` para los pendientes conocidos.

## Requisitos

- **Windows** — Live Mode depende de captura de audio WASAPI loopback
  (`PyAudioWPatch`), que es específico de Windows. Practice Mode no tiene
  esa dependencia y podría adaptarse a otros sistemas con algo de trabajo.
- **Python 3.12** (no 3.13 — algunas dependencias de ASR todavía no
  tienen wheels estables para esa versión).
- **Node.js 18+** para el frontend.
- **GPU NVIDIA con soporte CUDA, recomendado** — el reconocimiento de voz
  corre local con `faster-whisper`. Con 4 GB de VRAM alcanza de sobra
  para los modelos por defecto (`small`/`small.en` + `tiny`/`tiny.en`).
  Sin GPU, cae a CPU automáticamente — funciona, pero notablemente más
  lento.
- **Una API key de LLM** — Anthropic o cualquier endpoint compatible con
  la API de OpenAI (OpenAI real, un gateway propio, Groq, etc.).

## Instalación

### 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
python -m pip install silero-vad
```

**Importante en Windows:** lo anterior instala una build de PyTorch
CPU-only por defecto, lo cual rompe la selección de GPU en Live Mode
(`RealtimeSTT` decide el device vía `torch.cuda.is_available()` y lo
ignora si `torch` no ve la GPU). Después de instalar, reemplázalo por el
build con soporte CUDA:

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cu126 --force-reinstall --no-deps
python -c "import torch; print(torch.cuda.is_available())"  # debe imprimir True
```

Ajusta el índice de PyTorch (`cu126`, etc.) según tu versión de CUDA.

Copia el archivo de configuración y complétalo con tu API key:

```powershell
copy .env.example .env
```

### 2. Frontend

```powershell
cd frontend
npm install
```

### 3. Tus propios datos

El repositorio no incluye datos personales — quedan fuera de git a
propósito (ver `.gitignore`). Copia las plantillas en blanco y llénalas
con tu propia información:

```powershell
cd backend/data
copy profile.example.json profile.json
copy questions.example.yaml questions.yaml
```

`profile.json` es la fuente de verdad de tu experiencia (educación,
proyectos, historias en formato STAR, y brechas conocidas frente a la
vacante con su respuesta puente honesta) — el LLM nunca inventa
experiencia más allá de lo que pongas ahí. `questions.yaml` es el banco
de preguntas que se usan tanto para Practice Mode como para generar el
banco de respuestas.

Con tu perfil y tus preguntas listos, genera el banco de respuestas:

```powershell
cd backend
.venv\Scripts\python -m app.answers.generate
```

Esto genera un **borrador** por cada pregunta en `backend/data/answers/`.
Revísalo y corrígelo a mano antes de usarlo — es tu guion real, no algo
que deba quedar sin revisar. Marca `"reviewed": true` en cada entrada que
ya diste por buena, y luego construye el índice de búsqueda:

```powershell
.venv\Scripts\python -m app.answers.store
```

### 4. Verificar el audio (antes de usar Live Mode)

```powershell
cd backend
.venv\Scripts\python scripts\check_env.py
```

Reproduce audio y verifica en los archivos generados en `backend/scratch/`
que el loopback capturó el audio del sistema y no tu voz. Esto confirma
que la captura de audio funciona antes de depender de ella en una
entrevista real.

## Cómo correrlo

```powershell
# Terminal 1
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm run dev
```

Abre http://localhost:5173 — el proxy de Vite reenvía `/api` al backend
en el puerto 8000, sin necesidad de configurar CORS a mano.

Para acceder desde otro dispositivo en la misma red (por ejemplo, para
ver el historial de Live Mode desde el teléfono), levanta el backend con
`--host 0.0.0.0` y el frontend expondrá automáticamente una URL de red
local además de `localhost`.

### Usando Live Mode

En la pestaña "Live": elige el idioma (inglés o español — controla el
modelo de reconocimiento de voz, la dirección de traducción y el idioma
de la respuesta sugerida) y da clic en "Iniciar Live Mode". El backend
empieza a capturar el audio del sistema directamente — no hace falta
compartir el micrófono del navegador. Coloca la pestaña junto a tu
videollamada.

El toggle "Respuesta completa" está apagado por defecto a propósito: ver
una respuesta completa sugerida en vivo y leerla textualmente es un
riesgo real de que se note en la entrevista. El valor principal está en
la traducción y las palabras clave; la respuesta completa es una ayuda
adicional, no el modo recomendado por defecto.

## Configuración

Variables principales de `backend/.env` (ver `.env.example` para la
lista completa):

| Variable | Qué controla |
|---|---|
| `LLM_PROVIDER` | `anthropic` o `openai_compat` |
| `ANTHROPIC_API_KEY` | si el proveedor es Anthropic |
| `OPENAI_COMPAT_BASE_URL` / `_API_KEY` / `_MODEL` | si el proveedor es OpenAI o un gateway compatible |
| `ASR_DEVICE` / `ASR_COMPUTE_TYPE` | `cuda`/`cpu`, precisión de faster-whisper |
| `APP_HOST` / `APP_PORT` | binding del servidor (`0.0.0.0` para acceso desde la red local) |

Ver `docs/Arquitectura.md` para la referencia completa de configuración
y de cada módulo del proyecto.

## Estructura del proyecto

```
backend/    FastAPI + ASR local (RealtimeSTT/faster-whisper) + LLM por API
frontend/   React + Vite + TypeScript + Tailwind
docs/       Documentación técnica y de diseño
```

Ver `docs/Arquitectura.md` para el detalle módulo por módulo, diagramas
de flujo de datos, y las decisiones de diseño detrás de cada parte.
