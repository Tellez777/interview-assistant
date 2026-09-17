# Backlog

Pendientes conocidos del proyecto, en orden de prioridad. Ver
`Feedback_Uso_Real.md` para el contexto de dónde salió cada uno.

## Prioridad alta, bajo esfuerzo

**A. Filtrar turnos no sustanciales antes de correr el pipeline
completo.**
Antes de traducir/buscar en el banco/generar una respuesta: si el texto
transcrito de un turno tiene menos de ~5 palabras, o coincide con una
lista de muletillas/confirmaciones comunes ("yeah", "okay", "mhm",
"uh-huh", "no", "thank you", "bye", y sus equivalentes en español), no
correr el pipeline completo para ese turno. Mostrar igual el texto crudo
en el panel de transcripción (para no perder contexto de qué se dijo),
pero sin tocar la traducción, los keypoints ni la respuesta sugerida que
ya estaban en pantalla — deben quedarse como estaban hasta la siguiente
pregunta real. En una sesión real de prueba, casi la mitad de los turnos
procesados por el pipeline completo eran de este tipo — cada uno
sobrescribía en pantalla una respuesta buena anterior con contenido
irrelevante.

**B. Vista principal tipo hilo/conversación, no "último turno único".**
Actualmente la vista en vivo solo muestra el turno más reciente en cada
panel (transcripción / traducción / keypoints / respuesta), así que
cualquier turno nuevo — incluso uno sin contenido útil — reemplaza lo que
había antes. Cambiar a una lista de turnos que se acumula durante la
sesión (auto-scroll al más nuevo), sin borrar nunca los anteriores.
Combinado con (A), evita perder de vista una respuesta útil por un
fragmento suelto o una interjección.

## Prioridad media

**C. Fusionar turnos consecutivos cercanos como continuación, en vez de
tratarlos como pregunta nueva.**
La detección de fin de turno se basa en un umbral de silencio. Si un
nuevo turno llega dentro de una ventana corta después del anterior (por
probar: 3–4 segundos), en vez de procesarlo como independiente, concatenar
el texto nuevo al de la pregunta anterior y volver a correr la búsqueda +
respuesta sobre el texto combinado. Esto cubre el caso de que alguien
complemente o aclare su propia pregunta justo después de hacerla, sin
fragmentar la respuesta en dos generaciones desconectadas entre sí.

## Prioridad baja / mayor esfuerzo

**D. Diarización de hablantes.**
El diseño actual asume una sola voz en el audio capturado del sistema. Si
hay más de una persona hablando por el mismo canal (por ejemplo, un panel
con más de un entrevistador), no hay forma de distinguir "la misma
persona retomando su pregunta" de "otra persona interrumpiendo o
completando la idea" — para el sistema de transcripción es la misma
señal de audio, sin ningún concepto de quién habla. La solución robusta
es distinguir hablantes por voz (embeddings de speaker, o algo más ligero
por tono/pitch) y tratar cada uno como un canal lógico separado. Es la
solución más completa al problema de fondo, pero también la de mayor
esfuerzo de implementación y la que más riesgo de latencia añade —
dejarla para el final, después de validar que (A)+(B)+(C) ya cubren la
mayoría de los casos prácticos.

## Otros pendientes menores

- Validar con una sesión real y prolongada que la lógica de
  "no repetir la misma historia/ejemplo dos veces seguidas" realmente
  reduce la repetición percibida — hasta ahora solo se verificó que no
  rompe nada, no que cumpla su objetivo.
- Revisar si el umbral de similitud para usar una respuesta cacheada del
  banco (en vez de generarla con el modelo de lenguaje) sigue siendo
  razonable con más preguntas reales de prueba.
