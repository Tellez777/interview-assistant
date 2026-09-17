# Idea inicial

## El problema

Alguien se prepara para entrevistas de trabajo en un idioma en el que no
tiene fluidez nativa. Conoce bien su propia experiencia técnica, pero en
el momento de la entrevista, hablando en tiempo real y bajo presión, le
cuesta articularla con la misma claridad con la que la tiene en la
cabeza. El objetivo no es que alguien más responda por él — es reducir
la fricción de traducir "lo que sé" a "lo que puedo decir en el momento",
y tener un espacio para practicar antes de que cuente de verdad.

## La propuesta original

Un asistente con dos modos:

1. **Modo práctica**: simula una entrevista completa. Hace preguntas
   típicas por categoría (introducción, stack técnico, proyectos,
   comportamiento, etc.), escucha la respuesta hablada, la transcribe y
   da retroalimentación — tanto objetiva (ritmo de habla, duración,
   muletillas) como de contenido (qué puntos clave mencionó, qué omitió,
   si algo suena poco natural).
2. **Modo en vivo**: durante la entrevista real, escucha al entrevistador
   en tiempo real, transcribe lo que pregunta, lo traduce, y muestra
   palabras clave y una posible respuesta sugerida — sin que el candidato
   tenga que estar escribiendo ni buscando nada mientras habla.

La premisa de fondo: la mayor parte del valor no está en la latencia
milimétrica del modo en vivo, está en tener un **banco de respuestas
propio, revisado y aprobado de antemano**, construido a partir de la
experiencia real de la persona. El modo en vivo, en el mejor de los
casos, es sobre todo recuperación rápida de ese banco — no generación
improvisada sobre la marcha.

## Qué hace falta para que funcione de verdad

Un diseño ingenuo de esta idea tiende a subestimar justo la parte más
difícil: **de dónde sale el audio, y cómo se sabe que alguien terminó de
hablar**. Es fácil imaginar "transcribir en tiempo real y traducir" como
si fuera un problema resuelto; en la práctica, ahí es donde vive casi
toda la dificultad real:

- Capturar el audio del sistema (la llamada), no solo el micrófono —
  porque quien hay que escuchar es al entrevistador, no al candidato.
- Detectar de forma confiable cuándo una pregunta terminó y no fue solo
  una pausa natural, sin cortar preguntas largas ni tardar tanto que se
  sienta desconectado del ritmo real de una conversación.
- Aceptar que "transcripción en tiempo real" real no es instantánea:
  hay una ventana entre que alguien termina de hablar y que el sistema
  puede confirmar que terminó.
- Tolerar condiciones de audio imperfectas: ruido, muletillas de quien
  escucha ("mhm", "okay"), más de una persona hablando por el mismo
  canal.

Optimizar la latencia de la parte de generación de respuesta (qué tan
rápido responde el modelo de lenguaje) es relativamente fácil comparado
con resolver bien la segmentación de turnos sobre audio real y
desordenado. Un diseño que invierte el esfuerzo al revés — mucho cuidado
en la velocidad de respuesta, poco en la detección de turnos — tiende a
verse bien en una demo controlada y a fallar en el primer uso real.

## Prioridad de construcción

Dado lo anterior, tiene sentido construir en este orden:

1. **Banco de respuestas propio**, generado y luego revisado a mano por
   la persona, a partir de un perfil estructurado de su experiencia real
   (para que el sistema nunca invente algo que no pasó).
2. **Modo práctica**, porque no tiene presión de tiempo real y permite
   validar todo lo demás (transcripción, evaluación, banco de
   respuestas) sin depender de resolver primero el problema difícil de
   captura de audio en vivo.
3. **Modo en vivo**, al final, una vez que la detección de turnos sobre
   audio real esté genuinamente probada — no solo en pruebas sintéticas
   con una sola voz limpia, sino en condiciones parecidas a las de una
   llamada real.

Ver `Backlog.md` para el estado de esa última parte y lo que falta
resolver.
