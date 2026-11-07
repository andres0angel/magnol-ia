# Guía de prueba de Magnol-IA

Dos rondas: primero el equipo verifica que el bot funciona (30 minutos por persona); después cada quien lo prueba con uno o dos adultos mayores. Al final, una persona descarga la bitácora (paso 9 del cuaderno) y entre todos la revisan.

## Antes de empezar

1. Una persona abre el cuaderno de Colab, ejecuta los pasos 1 a 5 y comparte en el grupo la lista de cédulas del paso 5 (cada quien tiene las suyas).
2. Si van a usar notas de voz, esa misma persona configura las claves (paso 2) y enciende el bot (paso 8). Los demás buscan el bot en Telegram y tocan *Iniciar*.
3. Quien no tenga Telegram puede probar por texto en el paso 7 de su propia copia del cuaderno.

## Ronda 1: el equipo verifica que funciona

Marque cada escenario. Si algo falla, anote **qué dijo exactamente** y qué respondió el bot: con eso se corrige.

| # | Escenario | Qué decir (texto o nota de voz) | Qué debería pasar | ✓ / ✗ y notas |
|---|---|---|---|---|
| 1 | Saludo e identificación | "Buenas" y luego su cédula, en números o en palabras | Pide la cédula, dice el nombre del paciente y pregunta si es correcto | |
| 2 | Agendar desde cero | Con la cédula *desde cero*: "necesito una cita con el médico" | Ofrece máximo dos opciones en días distintos, con hora y sede | |
| 3 | Pedir otro día | "Ninguna, mejor el martes por la tarde" | Busca de nuevo con esa preferencia | |
| 4 | Repetir | "¿Cómo? Repítame" | Repite lo último, igual | |
| 5 | Confirmar | "La segunda" y luego "sí" | Confirma fecha, hora, sede, dirección y profesional | |
| 6 | Consultar | Con la cédula *con cita*: "¿cuándo es mi cita?" | Dice la cita correcta | |
| 7 | Cambiar | "Me la puede cambiar para otro día" | Ofrece opciones y, al confirmar, libera el cupo anterior | |
| 8 | Cancelar | "Cancélemela" y luego "sí" | Pide confirmación, cancela y agradece | |
| 9 | Especialista con orden | Con la cédula *con orden*: "necesito la cita del especialista" o el nombre de la especialidad | Agenda en la unidad hospitalaria más cercana | |
| 10 | Especialista sin orden | "Quiero cita con el de los huesos" | Explica que se necesita orden y ofrece medicina general | |
| 11 | Especialidad que la red no tiene | "Necesito el cardiólogo" | Explica que la red no la presta y ofrece medicina general | |
| 12 | Cuidador | "Es para mi mamá", y la cédula de ella | Agenda para la paciente, no para quien escribe | |
| 13 | Urgencia | En cualquier momento: "me duele mucho el pecho" | Indica llamar al 123 de inmediato | |
| 14 | Pedir una persona | "Quiero hablar con alguien" | Explica cómo comunicarse con una persona | |
| 15 | Nota de voz | Cualquiera de las anteriores, hablando como un adulto mayor | Muestra lo que entendió y responde también con audio | |

## Ronda 2: prueba con adultos mayores

La idea es medir si una persona mayor logra sacar una cita **sola**, no si el equipo sabe usar el bot.

1. **Consentimiento.** Antes de empezar, lea esto: *"Estamos probando un asistente para pedir citas médicas. Es una demostración: los datos son inventados y no se va a pedir ninguna cita de verdad. Vamos a guardar lo que usted le diga al asistente, sin su nombre, solo para mejorarlo. ¿Está de acuerdo?"* Si dice que no, no se hace la prueba (Ley 1581 de 2012).
2. **Tarea.** Entréguele el celular con el bot abierto y una cédula de prueba escrita en un papel: *"Imagine que necesita una cita con el médico general para la próxima semana. Pídala como usted quiera, hablando o escribiendo."*
3. **Observe sin ayudar.** Solo intervenga si la persona lo pide o se queda bloqueada más de un minuto; anótelo como "necesitó ayuda".
4. **Anote** en la tabla de abajo. Al terminar, pregunte: *"¿Esto fue más fácil o más difícil que llamar a pedir la cita? ¿Por qué?"*

| Persona (sin nombre) | Edad | ¿Usa WhatsApp sola? | ¿Logró la cita? | ¿Necesitó ayuda? ¿En qué? | Minutos | ¿Habló o escribió? | Más fácil o más difícil que llamar, y por qué |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Al final: revisar la bitácora

1. Descargue la bitácora con el paso 9 del cuaderno y ábrala en Excel o Google Sheets.
2. En cada turno, llene `entendio_bien` (si/no) y, cuando no, `intencion_correcta` y `comentario`.
3. Las frases que el bot entendió mal se agregan a `datos/pruebas/frases_adultos_mayores.csv` con `split=real`. Así el 76 % de comprensión con frases nuevas se reemplaza por una cifra medida con personas reales.
4. Compare las métricas del paso 9 (tasa de éxito, turnos y minutos hasta agendar) con lo que contaron en las entrevistas sobre el call center.
