# Fuentes de los datos reales

El MVP simula la agenda de la **E.S.E. Metrosalud** (red pública de Medellín). Todo lo que describe a la red y a la población es real; las personas, profesionales, cupos y citas son sintéticos porque los datos clínicos son reservados por ley.

## Datos reales que usa el generador

| Archivo | Qué contiene | Fuente |
|---|---|---|
| `reps_sedes_metrosalud_medellin.csv` | 54 sedes de Metrosalud: código de habilitación, nombre, dirección y teléfono (corte REPS 12-mar-2026) | Minsalud, REPS, datos.gov.co, conjunto `c36g-9fc2`: https://www.datos.gov.co/Salud-y-Protecci-n-Social/Registro-Especial-de-Prestadores-y-Sedes-de-Servic/c36g-9fc2 |
| `medata_centros_atencion_metrosalud.csv` | 51 centros de atención con **comuna, barrio, longitud y latitud** | Alcaldía de Medellín, MEData, "Centros de atención de Metrosalud" (09-nov-2022, CC BY-SA 4.0): https://medata.gov.co/dataset/1-048-22-000400 · ficha en datos.gov.co `k879-7jb3` |
| `coordenadas_complementarias.csv` | Coordenadas de la UH de Buenos Aires (abrió en 2023, no está en MEData) | OpenStreetMap (Nominatim), objeto `way/120374270`, © colaboradores de OpenStreetMap, ODbL |
| `horarios_sedes_metrosalud.csv` | **Horario de atención** de cada sede, de lunes a domingo | Gobernación de Antioquia, "Prestadores de Salud Departamento de Antioquia" (REPS), datos.gov.co `b4dp-ximh` |
| `sedes_metrosalud_georreferenciadas.csv` | Las cuatro fuentes anteriores unidas, más la UH más cercana a cada centro de salud | Generado por `scripts/preparar_sedes.py` |
| `metrosalud_indicadores.csv` | Población asignada y su reparto por EPS y régimen; días de espera por servicio (2019 y 2023); citas incumplidas; consultorios y unidades odontológicas; uso del asistente virtual y recordatorios en 2025 | Metrosalud, Informe de empalme (18-oct-2023): https://www.medellin.gov.co/es/wp-content/uploads/2023/12/1-Formato-Informe-de-Empalme-con-correcciones.pdf · Alcaldía de Medellín, 15-ene-2022: https://www.medellin.gov.co/es/?p=52958 · Alcaldía de Medellín, 21-ago-2025: https://www.medellin.gov.co/es/sala-de-prensa/noticias/a-traves-del-canal-virtual-metrosalud-ha-asignado-mas-de-12-000-citas-medicas-en-medellin/ |
| `poblacion_medellin_60mas_2026.csv` | Población de Medellín de 60 años y más por grupo quinquenal y sexo, 2026 | Proyecciones de población del DANE (post-COVID), tabuladas en https://telencuestas.com/censos-de-poblacion/colombia/2026/antioquia/medellin |
| `oportunidad_citas_referencia.csv` | Días máximos de espera según la norma y días observados (Metrosalud y referencias nacionales) | Circular Externa 038 de 2025 (Minsalud): https://normograma.supersalud.gov.co/compilacion/docs/circular_minsaludps_0038_2025.htm · Metrosalud, informe de empalme · EPS SOS, carta de desempeño 2025 · IETS citado en el Auto 1174 de 2025 · El Colombiano, ago-2025 |
| `inasistencia_referencia.csv` | Porcentaje de citas perdidas (Metrosalud 2023 y referencias) | Metrosalud, informe de empalme · Nueva EPS (Minuto30) · Secretaría de Salud de Medellín, estrategia CIGA (Telemedellín) |
| `eps_medellin_2026.csv` | EPS autorizadas en Medellín tras la reorganización territorial de 2026 | Infobae, 5-mar-2026 |

## Cómo se usa cada dato en el MVP

- **Sedes y direcciones** que dice el bot: REPS.
- **Unidad hospitalaria de referencia** (donde se agendan los especialistas): la UH más cercana en línea recta, calculada con las coordenadas reales. Antes era un supuesto; las coordenadas corrigieron 5 de 41 asignaciones (Aranjuez, Civitón, San Camilo, Estadio y Llanaditas).
- **Horario de la agenda**: los centros de salud ofrecen citas dentro de su horario real de lunes a viernes (por ejemplo, Trinidad hasta las 3 p. m. y Enciso hasta las 7 p. m.).
- **Días de espera** (calibración): los de Metrosalud en 2023, pasados a días hábiles (× 5/7): medicina general 3 días calendario ≈ 2 hábiles, odontología 3,3 ≈ 2, ginecología 14,5 ≈ 10.
- **Tamaño de la plantilla**: unos 125 médicos generales y 117 odontólogos sintéticos, frente a 115 consultorios de medicina general y 129 unidades odontológicas reales.
- **Pacientes**: edad y sexo con la pirámide DANE 2026 de Medellín (60 % mujeres entre los mayores de 60); EPS y régimen con el reparto real de la población asignada a Metrosalud (75 % Savia Salud subsidiado, 10 % contributivo, 15 % población pobre no asegurada).
- **Especialidades fuera de la red**: el bot distingue entre lo que Metrosalud sí presta pero no se agenda por este canal (ortopedia, urología, fisioterapia) y lo que la red no presta (cardiología, dermatología, neurología, oftalmología, reumatología), según el portafolio del informe de empalme.

## Qué sigue siendo supuesto (y está marcado así en el código)

- Consulta externa de las unidades hospitalarias de 7 a. m. a 4 p. m. (el horario "24 horas" del REPS es el de urgencias) y pausa de 12 a 1 en los centros de salud.
- Qué especialidades hay en cada sede: medicina general y odontología en todas; los especialistas, solo en las UH, 3 días a la semana. **Medicina interna** no aparece en el extracto del portafolio de consulta externa del informe de empalme; se mantiene porque es la remisión más común de los adultos mayores con enfermedades crónicas, pero hay que confirmarlo con la IPS.
- Días de espera de medicina interna (25 hábiles), optometría (10), nutrición (12) y psicología (15): Metrosalud no los publica.
- El 2 % del régimen contributivo que no es de Savia Salud se reparte entre Nueva EPS y Sura.
- Las UH tienen el triple de pacientes adscritos que un centro de salud.
- No hay citas los sábados, aunque muchos centros abren de 7 a 11 a. m.
- Personas, profesionales, agendas, órdenes y citas: **100 % sintéticos** (Faker, reproducibles con semilla).

## Hallazgos útiles para el modelo de negocio

- Metrosalud **ya tiene** un chatbot de WhatsApp, línea telefónica y portal web para citas, y en el primer semestre de 2025 envió 325.189 recordatorios automáticos. Su asistente virtual asignó unas 2.000 citas al mes, frente a 320.219 citas de medicina general asignadas en 2023: el canal digital todavía mueve una parte pequeña de la demanda. El diferencial de Magnol-IA no son los recordatorios ni el chat, sino **la voz y el diseño para adultos mayores**.
- En 2023 la red cumplía la norma en medicina general (3 días), pero no en ginecología (14,5 frente a 8). El cuello de botella en primer nivel parece estar más en el **acceso al canal** (lograr comunicarse) que en la falta de cupos, lo que coincide con la hipótesis del canal telefónico.
- La inasistencia real ronda el 17 % en medicina general y el 21 % en odontología (calculado con los conteos del informe).

## Para medir la voz a texto con voces de personas mayores

Mozilla Common Voice en español trae la edad que declaran los hablantes (miles de clips de personas de 60 a 69 años y algunos cientos de 70 a 89; licencia CC0). Descarga con cuenta en https://datacollective.mozillafoundation.org/. Lo más valioso, de todas formas, son los audios de las pruebas con usuarios reales (con su consentimiento).
