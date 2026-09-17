# Feedback de uso real

Primer uso del modo en vivo en una entrevista real (no en pruebas
sintéticas). Resultó ser una llamada con más de una persona del lado del
entrevistador, algo que el diseño original nunca contempló — se probó y
se verificó siempre asumiendo una sola voz en el audio capturado. Este
documento registra qué funcionó, qué falló, y por qué — ver `Backlog.md`
para el plan de solución correspondiente.

---

## Lo que sí funcionó

El traductor y las respuestas sugeridas, cuando el sistema recibía una
pregunta completa y limpia, funcionaron bien. Esto confirma que el
diseño de fondo (búsqueda semántica sobre el banco de respuestas +
modelo de lenguaje como respaldo + modo técnico para preguntas de
código) está bien calibrado en cuanto a calidad de contenido. El
problema no fue "la respuesta estaba mal" — fue que la respuesta buena
desaparecía de la pantalla antes de poder usarla, que es un problema
distinto y más específico: de segmentación de turnos y de interfaz, no
de calidad de generación.

Ejemplo de una respuesta técnica que funcionó bien (modo técnico,
disparado correctamente al detectar una pregunta de código): una consulta
SQL pedida para encontrar filas duplicadas en una tabla, respondida con
una consulta correcta usando `GROUP BY`/`HAVING`, una segunda variante
con subconsulta para traer los registros completos, y una nota sobre
mayúsculas/espacios en los valores a comparar — nivel de respuesta real,
no genérico.

---

## Lo que falló

### 1. El audio resultó tener más de una voz, y el diseño asume una sola

Todo el diseño del modo en vivo (captura del audio del sistema → un único
detector de turnos → cierre de turno cuando hay silencio) asume que la
única voz en el audio es "el entrevistador", singular. Con más de una
persona hablando por el mismo canal, el detector de turnos no tiene forma
de distinguir "la misma persona terminando su pregunta" de "otra persona
metiendo una idea encima" — para el sistema de transcripción es la misma
señal de audio, sin ningún concepto de quién habla. Esta es la causa raíz
de la que se desprenden los dos problemas siguientes.

### 2. Complementos inmediatos después de una pregunta fragmentaban el turno

El sistema cierra un turno en cuanto detecta un breve silencio. Eso
dispara todo el proceso (traducción + búsqueda + respuesta) para la
pregunta ya cerrada. Si alguien añade algo enseguida — o la misma persona
retoma tras una pausa natural — eso se procesa como un turno totalmente
nuevo e independiente, sin ninguna relación con el anterior. Dos
consecuencias:
- La respuesta nueva, generada sobre un fragmento suelto sin el contexto
  completo, suele ser peor o confusa.
- La interfaz solo mostraba el último turno (ver punto 4), así que la
  respuesta buena que sí se había generado para la pregunta original
  desaparecía de la pantalla, reemplazada por la del fragmento.

### 3. Muletillas y ruido disparaban turnos completos que también borraban la respuesta útil

En la sesión real más larga (~10 minutos), se registraron 33 turnos
procesados por el sistema completo. De esos, cerca de la mitad fueron de
4 palabras o menos — confirmaciones, muletillas o ruido mal transcrito
("yeah", "okay", "mhm", "no", y similares). Cada una de estas disparó el
proceso completo (traducción, búsqueda con score bajo, respuesta genérica
tipo "perdón, ¿puedes repetir la pregunta?") — no rompió nada
técnicamente, pero cada una sobrescribió la pantalla con contenido
irrelevante, tapando la respuesta anterior que sí era útil. Esa cantidad
de turnos en una conversación de 10 minutos es mucho más de lo que las
preguntas reales justificarían — es evidencia directa de sobre-disparo.

### 4. La vista principal solo mostraba el último turno

La interfaz en vivo mostraba únicamente el turno más reciente en cada
panel (transcripción, traducción, palabras clave, respuesta sugerida).
La vista de historial completo existía, pero en una pestaña separada —
poco práctico en medio de una entrevista real, donde no hay tiempo ni
atención disponible para cambiar de pestaña cada vez que el panel
principal se sobrescribe con ruido.

---

## Nota de alcance

Nada de esto es un problema de "la respuesta está mal" — es un problema
de segmentación de turnos y de qué se queda visible en pantalla bajo
audio real de más de una persona, una condición que nunca se probó en
las verificaciones previas (todas usaban una sola voz limpia). La calidad
del contenido generado se sostuvo bien incluso bajo esta condición real
no contemplada — lo que hay que arreglar es la robustez de cara al
desorden real, no el motor de respuestas en sí. Ver `Backlog.md` para el
plan concreto.
