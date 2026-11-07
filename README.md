# Magnol-IA · MVP

[![Pruebas](https://github.com/USUARIO/REPO/actions/workflows/pruebas.yml/badge.svg)](https://github.com/USUARIO/REPO/actions/workflows/pruebas.yml)
[![Abrir en Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/USUARIO/REPO/blob/main/Magnol-IA_Colab.ipynb)

Asistente de voz para que **adultos mayores saquen, consulten, cambien y cancelen citas médicas mandando notas de voz**, como le hablarían a una persona. Grupo 13, Creación de Empresas de Base Tecnológica.

**Costo de operación del MVP: $0.** Telegram, la voz a texto (Whisper en Groq), el texto a voz con voz colombiana (edge-tts) y el LLM tienen planes gratuitos. Todo funciona además **sin ninguna clave**, en modo solo reglas.

## Cómo probarlo

| Camino | Para quién | Qué hay que hacer |
|---|---|---|
| **Colab** (recomendado) | Cualquiera, sin instalar nada | Toque el botón *Abrir en Colab* de arriba y ejecute las celdas en orden. Permite conversar por texto con respuesta en audio. |
| **Un bot para todo el equipo** | Probar notas de voz entre varias personas | Una persona enciende el bot desde Colab (paso 8); las demás le escriben o le mandan notas de voz desde Telegram, cada una con **sus propias cédulas** (paso 5). |
| **En su computador** | Quien quiera modificar el código | `git clone https://github.com/USUARIO/REPO.git` y siga la [sección 5](#5-instalación-en-su-computador-unos-10-minutos). |

Qué probar y cómo hacerlo con adultos mayores: [`docs/GUIA_PRUEBAS.md`](docs/GUIA_PRUEBAS.md).

```
Usuario (nota de voz): "Buenas, necesito una cita con el de la presión"
Magnol-IA:  Hola, soy Magnol-IA, la asistente de citas médicas de la IPS piloto. […] Dígame el
            número de cédula de la persona que necesita la cita.
Usuario:    "treinta y dos millones cuatrocientos cincuenta y seis mil setecientos ochenta y nueve"
Magnol-IA:  Encontré a Rosa Elena Cardona Muñoz. ¿Es correcto?                       [Sí] [No]
Usuario:    "sí señora"
Magnol-IA:  Mucho gusto, doña Rosa. Encontré dos citas disponibles de medicina general. La primera:
            hoy jueves 12 de noviembre, a las 11 y 40 de la mañana, en la Unidad Hospitalaria de
            Manrique. La segunda: el martes 17 de noviembre, a las 7 de la mañana, en el mismo lugar.
            ¿Cuál prefiere, la primera o la segunda?          [La primera] [La segunda] [Otro día]
Usuario:    "ninguna, mejor la otra semana por la mañana"
Magnol-IA:  Encontré dos citas disponibles de medicina general. La primera: el miércoles 18 de
            noviembre, a las 8 de la mañana […] La segunda: el jueves 19 de noviembre, a las 7 de la
            mañana, en el mismo lugar. ¿Cuál prefiere?
Usuario:    "la segunda" → "sí"
Magnol-IA:  Listo, doña Rosa. Su cita quedó agendada: medicina general, el jueves 19 de noviembre,
            a las 7 de la mañana, en la Unidad Hospitalaria de Manrique, Calle 66 E número 42 - 51,
            con el doctor […]. Recuerde llegar 20 minutos antes con su cédula.
```
Cada respuesta llega como texto y también como nota de voz, con voz colombiana y un poco más lenta. (Conversación real del simulador, con fecha simulada 12-nov-2026.)

---

## 1. Por qué está construido así (conexión con los entregables)

| Hallazgo del curso | Decisión en el MVP |
|---|---|
| Problema priorizado (E4): **acceso oportuno a citas** de adultos mayores afiliados a EPS | El alcance es exactamente ese: agendar, consultar, cambiar y cancelar. Nada más. |
| Hipótesis descartada (E3): los canales **puramente digitales** (app o web) no lo resuelven solos | No hay app ni formularios. Se habla con notas de voz en una mensajería que ya usan. |
| Hipótesis ajustada (E3): el problema **sobrecarga a los cuidadores** | Un hijo o hija puede pedir la cita "para mi mamá" dando la cédula de ella. |
| Canvas: **paga la IPS**; el adulto mayor es el usuario | La agenda es una simulación de la de Metrosalud. En producción, esa pieza se reemplaza por la integración con el software de citas de la IPS cliente. |
| Hipótesis del canal telefónico como cuello de botella | Cada cancelación libera el cupo al instante ("así ese espacio le sirve a otra persona") y la bitácora mide turnos y minutos hasta agendar. |

**¿Por qué Telegram y no WhatsApp?** Desde el **1 de octubre de 2026** Meta cobra cada respuesta que envía un negocio dentro de la ventana de 24 horas ("mensajes de servicio") y deja de entregarlas si la cuenta no tiene un método de pago registrado. Telegram es gratis y acepta notas de voz igual. El adaptador de WhatsApp **ya está hecho y probado** con mensajes simulados (`magnolia/canales/whatsapp.py`): usa el mismo núcleo. En un piloto real, ese costo lo asume la IPS, que es el cliente que paga.

---

## 2. La data: qué es real y qué es simulado

El sistema no entrena un modelo propio: el reconocimiento de voz y el LLM ya vienen entrenados. Lo que hacía falta era una **agenda de IPS creíble** contra la cual agendar. El MVP simula la de la **E.S.E. Metrosalud**, la red pública de Medellín, con todos los datos reales disponibles:

| Capa | Contenido | Origen |
|---|---|---|
| **Real** | 51 sedes de Metrosalud con código REPS, dirección y teléfono | REPS de Minsalud, datos.gov.co (corte 12-mar-2026) |
| **Real** | **Comuna, barrio y coordenadas** de cada sede; con ellas se calcula la unidad hospitalaria más cercana a cada centro de salud | MEData (Alcaldía de Medellín) y OpenStreetMap |
| **Real** | **Horario de atención** de cada sede: la agenda solo ofrece citas cuando la sede está abierta | Gobernación de Antioquia (REPS), datos.gov.co |
| **Real (calibración)** | **Días de espera de la propia Metrosalud** (2023), consultorios y unidades odontológicas, citas incumplidas | Informe de empalme de Metrosalud (oct-2023) |
| **Real (calibración)** | Edad y sexo de los pacientes (pirámide DANE 2026 de Medellín, 60+) y su EPS y régimen (75 % Savia Salud subsidiado, 10 % contributivo, 15 % población pobre no asegurada) | DANE; informe de empalme de Metrosalud |
| **Sintético** | 1.503 adultos mayores, unos 240 médicos y odontólogos, ~220.000 cupos (40 días hábiles sin festivos), órdenes de remisión y citas existentes | `scripts/generar_datos.py` (Faker es_CO, reproducible con semilla) |
| **Prueba** | 173 frases etiquetadas, dichas como las diría un adulto mayor paisa ("se me cayó la plancha", "dale pues", "ni de riesgos") | `datos/pruebas/frases_adultos_mayores.csv` |

Los datos clínicos reales no se usan porque son reservados por ley. Fuentes, supuestos y hallazgos al detalle en [`datos/reales/FUENTES.md`](datos/reales/FUENTES.md).

**Calibración.** Las agendas se generan para que el primer cupo libre aparezca a los días de espera reales:

| Especialidad | Objetivo (días hábiles) | Simulado | Referencia real |
|---|---|---|---|
| Medicina general | 2 | 1,8 | Metrosalud 2023: 3 días calendario (la norma es ≤ 3) |
| Odontología | 2 | 2,1 | Metrosalud 2023: 3,3 días calendario |
| Ginecología | 10 | 10,2 | Metrosalud 2023: 14,5 días calendario (la norma es ≤ 10) |
| Medicina interna | 25 | 24,4 | Metrosalud no lo publica. Norma ≤ 15; IETS: 40 a 60 días para especialista |

**Lo que dice la data real sobre el negocio.** Metrosalud ya tiene chatbot de WhatsApp, línea y portal web, y envía recordatorios automáticos (325.189 en el primer semestre de 2025). Aun así, su asistente virtual asignó unas 2.000 citas al mes, frente a más de 320.000 citas de medicina general al año. En primer nivel la red cumple la norma de días de espera, así que el problema está más en **lograr comunicarse** que en la falta de cupos. El diferencial de Magnol-IA es la **voz y el diseño para adultos mayores**, no el chat ni los recordatorios.

---

## 3. Cómo funciona

```
 Nota de voz ──► Voz a texto ──► Comprensión híbrida ──► Gestor de diálogo ──► Agenda de la IPS
 (Telegram /     (Whisper vía     1) reglas (gratis,       (estados, máx. 2        (SQLite simulada;
  WhatsApp)       Groq, o local)     sin internet)          opciones, confirma,      en producción:
                                   2) LLM solo si las       repite, urgencias,       API del software
 Texto + nota ◄── Texto a voz ◄──     reglas dudan           cuidadores)             de la IPS)
 de voz           (edge-tts es-CO)
```

- **El LLM solo interpreta; nunca redacta.** Devuelve un JSON (intención, especialidad, fecha…) que se valida contra el catálogo. Lo que se le dice al paciente sale de plantillas revisadas, así que no puede inventar horarios ni dar consejos médicos.
- **Diseño para adultos mayores:** frases cortas, trato de "don/doña", máximo dos opciones en días distintos, confirmación con sí o no antes de agendar, cambiar o cancelar, "¿me repite?" en cualquier momento y botones grandes como alternativa a la voz. Si la persona dice "la cita del especialista" sin recordar cuál, el bot usa la orden vigente que tenga.
- **Seguridad:** ante síntomas graves ("me duele el pecho", "me desmayé"), en cualquier punto de la conversación, indica llamar al 123. Si alguien dice que quiere hacerse daño, recibe un mensaje específico.
- **Reglas del sistema de salud:** los especialistas exigen una orden vigente (si no la hay, ofrece medicina general); distingue lo que la red presta pero no se agenda por este canal (ortopedia, urología) de lo que la red no presta (cardiología, dermatología…); avisa si el día pedido es festivo; no duplica citas de la misma especialidad (ofrece cambiar la existente); las reservas son atómicas (si otra persona tomó el cupo un segundo antes, ofrece otro).

---

## 4. Resultados de las pruebas

**69 pruebas automáticas** (`pytest`), que también corren en GitHub en cada cambio: flujos completos, cancelaciones que liberan el cupo, reprogramación atómica, órdenes, urgencias, cuidadores, festivos, reservas simultáneas, webhook de WhatsApp (verificación, firma HMAC, mensajes repetidos), conversión a nota de voz OGG/Opus, el LLM y la voz a texto contra una API simulada (incluido qué pasa si se cae o se agota la cuota) y que la agenda respete los datos reales (horarios, UH más cercana, reparto de EPS y edades).

**Comprensión (solo reglas, sin LLM):**

| Conjunto | Frases | Intención correcta | Frase 100 % correcta |
|---|---|---|---|
| Desarrollo | 64 | 100 % | 96,9 % |
| Prueba | 63 | 100 % | 96,8 % |
| **Frases nuevas escritas después de congelar las reglas** | 46 | **76,1 %** | 71,7 % |

> ⚠️ **Hay que leer esto con honestidad.** El 100 % es optimista: la misma persona escribió las frases y las reglas. El número realista es el **76 %** con frases nunca vistas. De los 11 errores, **8 fueron casos en que las reglas mismas dijeron "no sé"**, que son justo los que el modo híbrido envía al LLM. Esas fallas se corrigieron después, así que ese conjunto ya no es ciego. **La métrica de verdad saldrá de probar con adultos mayores reales** (ver la sección 7).

---

## 5. Instalación en su computador (unos 10 minutos)

1. **Python 3.11 o superior:** descárguelo de https://www.python.org/downloads/ y, en el instalador, marque *Add python.exe to PATH*.
2. **ffmpeg** (para las notas de voz): en Windows ejecute `winget install --id Gyan.FFmpeg -e` y abra una terminal nueva (en Mac: `brew install ffmpeg`).
3. **Descargue e instale el proyecto:**
   ```
   git clone https://github.com/USUARIO/REPO.git magnolia-mvp
   cd magnolia-mvp
   py -m pip install -r requirements.txt
   copy .env.ejemplo .env
   ```
   (En Mac o Linux use `python3` en lugar de `py` y `cp` en lugar de `copy`.)
4. **Cree el bot de Telegram (gratis):** en Telegram busque **@BotFather**, envíe `/newbot`, elija un nombre y un usuario que termine en `bot`, y pegue el token en `.env` en la línea `TELEGRAM_TOKEN=`.
5. **(Recomendado) Clave gratis de Groq:** créela en https://console.groq.com/keys, sin tarjeta, y péguela en `LLM_API_KEY=`. Esa sola clave sirve para entender los audios y para el modo híbrido. Sin clave, el bot funciona con reglas y entiende texto. Para que entienda audios sin clave, instale `faster-whisper`, que corre en el computador (más lento).
6. **Genere la base de datos:** `py scripts\generar_datos.py` (tarda unos 5 segundos). Repítalo si pasan más de 2 semanas, porque la agenda arranca el día en que se genera. Las conversaciones anteriores se guardan antes en `datos/bitacoras/`.
7. **Pruebe sin Telegram:** `py -m magnolia.canales.consola`
8. **Encienda el bot:** `py -m magnolia.canales.telegram_bot`. Busque su bot en Telegram, toque *Iniciar* y mándele una nota de voz. El bot responde mientras esa terminal esté abierta.

**Cédulas de demostración** (para la demo en clase; para pruebas en equipo use `py scripts\cedulas_prueba.py --personas 5`):

| Cédula | Paciente | Para mostrar |
|---|---|---|
| 43527891 | doña María Ofelia (74, Savia Salud) | Ya tiene cita de medicina general (no duplica, ofrece cambiarla) y una **orden vigente de medicina interna** |
| 8345678 | don José Aníbal (81, Nueva EPS) | Tiene **dos citas**: muestra cómo elegir cuál cancelar o cambiar |
| 32456789 | doña Rosa Elena (68, Sura) | Sin citas ni órdenes: agendar desde cero; pedir especialista sin orden |

**Scripts útiles:**

| Comando | Para qué |
|---|---|
| `py -m pytest` | Pruebas automáticas |
| `py scripts\evaluar_nlu.py --errores` | Comprensión con frases de adultos mayores (`--motor hibrido` con clave) |
| `py scripts\cedulas_prueba.py --personas 5` | Repartir pacientes de prueba entre el equipo |
| `py scripts\metricas.py` | Métricas de las conversaciones |
| `py scripts\exportar_bitacora.py` | Conversaciones en CSV, listas para revisar y etiquetar |
| `py scripts\preparar_sedes.py` | Volver a unir las fuentes reales de las sedes (REPS + MEData + horarios) |

---

## 6. Guion sugerido para la demo en clase (2 minutos)

1. Mande una **nota de voz**: *"Buenas, necesito una cita con el de la presión"*. Muestre que entiende lenguaje coloquial.
2. Diga la cédula **en palabras**: *"treinta y dos millones cuatrocientos cincuenta y seis mil setecientos ochenta y nueve"*.
3. Responda *"ninguna, mejor la otra semana por la mañana"*. Busca otros días con esas preferencias.
4. Diga *"¿cómo? repítame"*, luego *"la segunda"* y *"sí"*. La cita queda agendada y llega la confirmación también en audio.
5. Muestre una urgencia: *"me duele mucho el pecho"*, y el bot indica llamar al 123.
6. Cierre con `py scripts\metricas.py`: citas agendadas, turnos hasta agendar y porcentaje de malentendidos.

Para una demo predecible, ponga `FECHA_SIMULADA=2026-11-12T09:00` en `.env` y regenere con `py scripts\generar_datos.py --desde 2026-11-12` (en Colab: variable `FECHA_SIMULADA` del paso 2).

---

## 7. Cómo validar con usuarios reales (siguiente paso del curso)

La guía completa, con la lista de escenarios, el texto de consentimiento y la tabla para anotar, está en [`docs/GUIA_PRUEBAS.md`](docs/GUIA_PRUEBAS.md). En resumen:

- **Prueba con 5 a 10 adultos mayores** (pueden ser las mismas personas de las entrevistas). Tarea: "saque una cita de medicina general". Observe sin ayudar.
- `scripts/metricas.py` calcula de la bitácora: **tasa de éxito al agendar, turnos y minutos hasta agendar, % de turnos no entendidos, % que pidió una persona, % de mensajes por voz y cuánto resolvieron las reglas frente al LLM.** Compárelo con lo que reportaron en las entrevistas sobre el call center.
- `scripts/exportar_bitacora.py` saca las conversaciones en CSV (con un código anónimo en lugar del usuario de Telegram) para marcar qué entendió mal. Esas frases se agregan a `frases_adultos_mayores.csv` y así la cifra del 76 % se reemplaza por una real.
- **Consentimiento:** aunque los pacientes sean simulados, la bitácora guarda lo que dicen los usuarios. Antes de probar con personas reales, pídales autorización (Ley 1581 de 2012) y explíqueles que es una demo. Las bitácoras no se suben a GitHub (`.gitignore`).

---

## 8. Limitaciones conocidas

- **Identidad:** confirmar el nombre basta para una demo, no para producción. Con `VERIFICAR_NACIMIENTO=true` pide el año de nacimiento sin revelar el nombre. En producción se recomienda un código de un solo uso.
- **La agenda es simulada.** El verdadero reto técnico y comercial de un piloto es integrarse con el software de agendas de cada IPS.
- **Supuestos de la agenda:** no hay citas los sábados (aunque muchos centros abren de 7 a 11 a. m.), la consulta externa de las unidades hospitalarias va de 7 a. m. a 4 p. m., y medicina interna no aparece en el extracto del portafolio de Metrosalud que se consultó (se mantiene porque es la remisión más común de los adultos mayores). Detalle en `FUENTES.md`.
- **Adopción de Telegram:** los adultos mayores usan mucho más WhatsApp. Para un piloto real conviene WhatsApp, cuyo costo asume la IPS.
- **Servicios gratuitos de terceros:** edge-tts usa un servicio no oficial de Microsoft que podría cambiar (si falla, pasa a gTTS automáticamente). El plan gratuito de Whisper en Groq tiene límites por minuto y por día (revíselos en la consola de Groq); para un piloto pequeño alcanza. Si el LLM no responde, el bot sigue funcionando con reglas.
- **Sesiones en memoria:** si se reinicia el bot, se pierde la conversación en curso, pero no la identidad ni las citas. En Colab, la sesión se apaga tras unos 90 minutos sin actividad.
- **Fuera del alcance de este MVP:** recordatorios proactivos de la cita (Metrosalud ya los envía por mensaje; por voz serían la extensión natural), resultados de exámenes e historia clínica (el bot explica que no los maneja).

---

## 9. Estructura

```
Magnol-IA_Colab.ipynb  cuaderno para probar sin instalar nada
magnolia/
  config.py            configuración (.env)
  dialogo.py           gestor de diálogo (estados, reglas de negocio, textos)
  agenda.py            operaciones sobre la agenda (buscar, reservar, cancelar, reprogramar)
  catalogo.py          especialidades, sinónimos coloquiales y portafolio real de la red
  bitacora.py          exportación anónima de las conversaciones
  textos.py            fechas, horas y direcciones dichas en voz alta
  db.py                esquema SQLite
  nlu/                 normalizar.py · fechas.py · reglas.py · llm.py · hibrido.py
  voz/                 stt.py (voz a texto) · tts.py (texto a voz → nota de voz OGG/Opus)
  canales/             consola.py · cuaderno.py · telegram_bot.py · whatsapp.py
scripts/               generar_datos.py · preparar_sedes.py · cedulas_prueba.py · evaluar_nlu.py
                       metricas.py · exportar_bitacora.py · descargar_reps.py
datos/
  reales/              REPS, MEData, horarios, indicadores de Metrosalud, DANE + FUENTES.md
  catalogos/           especialidades.csv · sedes_atributos.csv
  sinteticos/          copia en CSV de la data generada (para abrir en Excel)
  pruebas/             frases etiquetadas de adultos mayores
docs/GUIA_PRUEBAS.md   qué probar, consentimiento y tabla de observación
tests/                 69 pruebas automáticas
.github/workflows/     las pruebas corren solas en GitHub en cada cambio
```
