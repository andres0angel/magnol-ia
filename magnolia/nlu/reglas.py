"""Comprensión por reglas: rápida, gratuita, sin internet y explicable.

Trabaja sobre texto normalizado (sin tildes, números en dígitos). El contexto indica qué espera el
diálogo, porque "la dos" significa una opción si se acaban de ofrecer dos citas, y "sí" solo tiene
sentido si se hizo una pregunta.
"""
from __future__ import annotations

import re
from datetime import date

from ..catalogo import buscar_especialidad
from .fechas import DIAS, extraer_tiempo
from .normalizar import normalizar
from .tipos import Interpretacion


def _r(*patrones: str) -> re.Pattern:
    return re.compile("|".join(rf"(?:{p})" for p in patrones))


URGENCIA = _r(
    r"\b(me duele|dolor)\b.*\bpecho\b", r"\bpecho\b.*\bduele\b", r"\bno puedo respirar\b", r"\bme ahogo\b",
    r"\bme desmaye\b", r"\bdesmay", r"\bme quiero morir\b", r"\bquitarme la vida\b", r"\bmatarme\b",
    r"\bsuicid", r"\bsangr\w* mucho\b", r"\binfarto\b", r"\bderrame\b", r"\bconvulsi",
    r"\bse me (durmio|adormecio) (la mitad|un lado|medio)\b", r"\bno puedo hablar\b", r"\bme cai\b.*\bno me puedo parar\b",
    r"\burgencia", r"\bemergencia\b",
)
HUMANO = _r(
    r"\bhablar con (una |un |alguien|la |el )?(persona|alguien|asesor|asesora|humano|operador|operadora|funcionario|funcionaria|senorita)",
    r"\b(paseme|paseme con|comuniqueme|comunicarme) con\b", r"\basesor\b", r"\basesora\b", r"\boperador",
    r"\bpersona de verdad\b", r"\bpersona real\b", r"\bun humano\b",
)
REPETIR = _r(
    r"\brepit", r"\brepet", r"\botra vez\b", r"\bno (le )?entendi\b", r"\bno le escuche\b", r"\bno escuche\b",
    r"^como\b", r"\bque dijo\b", r"\bcomo dijo\b", r"\bmas despacio\b", r"\bde nuevo\b.*\b(dijo|diga)\b",
)
AYUDA = _r(
    r"\bcomo funciona", r"\bno entiendo como\b", r"\bayuda\b", r"\bayudeme\b(?!.*\bcita)", r"\bque puedo hacer\b",
    r"\bque hace usted\b", r"\bpara que sirve\b", r"\bque me ofrece\b", r"\bque servicios\b",
    r"\bcon quien hablo\b", r"\bquien es usted\b", r"\bque es esto\b",
)
FUERA_ALCANCE = _r(
    r"\bresultado", r"\bexamenes\b(?!.*\bcita)", r"\bhistoria clinica\b", r"\bcuota moderadora\b", r"\bcopago\b",
    r"\bincapacidad\b", r"\bcertificado\b", r"\breclamar (los )?medicamentos\b", r"\bdonde queda\b",
    r"\bqueja\b", r"\bpqr", r"\bautorizacion\b", r"\bfactura\b",
)
CANCELAR = _r(
    r"\bcancel", r"\banul", r"\bborr", r"\beliminar? (la |mi )?cita\b", r"\bquitar (la |mi )?cita\b",
    r"\bya no (voy|puedo|necesito|quiero|podre)\b.*\b(ir|cita|asistir)\b", r"\bno (voy|vamos) a (poder )?ir\b",
    r"\bno puedo ir\b", r"\bno voy a poder asistir\b", r"\bya no la necesito\b", r"\bdesagend",
    r"\b(ya )?no necesito (ir|la cita|esa cita)\b",
)
# "Me la cancelaron" cuenta lo que hizo la IPS, no es un pedido de cancelar (entrevista ENT-002)
CANCELADA_POR_OTROS = re.compile(
    r"\b(me|nos|le|les) (la |las |lo )?cancelaron\b|\bse (me )?cancelo\b|\bfue cancelada\b|\bme (la )?anularon\b")
VOLVER_A_AGENDAR = _r(r"\bvuelvan a (dar|asignar|agendar)\b", r"\breagend", r"\bvolver a (sacar|pedir|agendar)\b",
                      r"\bme la (den|asignen) (otra vez|de nuevo)\b")
REPROGRAMAR = _r(
    r"\bcambi\w* (la|mi|esa) cita\b", r"\bcambi\w*me la cita\b", r"\bcambiar(la)?\b.*\b(dia|fecha|hora)\b",
    r"\bmov\w* (la|mi) cita\b", r"\bmuev", r"\bcorr\w* (la|mi) cita\b", r"\bcorrer(la)?\b", r"\baplaz",
    r"\bpasar(la)? (para|pa)\b", r"\bpasar (la|mi) cita\b", r"\bla puedo pasar\b", r"\breprogram",
    r"\bposponer\b", r"\bpospon", r"\bcambiarla\b", r"\bla puedo cambiar\b", r"\bme la cambia\b", r"\botro dia\b.*\bcita\b", r"\bcita\b.*\botro dia\b", r"\bcambio de cita\b",
)
CONSULTAR = _r(
    r"\bcuando (es|tengo|me toca|seria|quedo)\b", r"\ba que hora(s)? (es|tengo|quedo)\b", r"\bque dia (es|quedo|tengo)\b",
    r"\btengo (una )?cita", r"\btengo citas\b", r"\bcitas? que tengo\b", r"\b(cuales|que|cuantas) (son )?(las |mis )?citas\b", r"\bcitas? pendiente", r"\bproxima cita\b", r"\bmis citas\b",
    r"\bconfirm\w*\b", r"\bpara (que|cuando) (dia )?(quedo|tengo|es)\b", r"\bquedo (la|mi) cita\b",
    r"\bsaber (de|si tengo|cuando)\b.*\bcita", r"\bdonde es (la|mi) cita\b", r"\ba donde tengo que ir\b",
    r"\b(fecha|hora|dia) de (mi|la) cita\b", r"\bcuando era\b", r"\ba que hora(s)? tengo que ir\b", r"\bme recuerda\b",
    r"\bme acuerdo (de )?(cuando|la cita)\b", r"\bse me olvido (cuando|la cita|la hora)\b",
)
AGENDAR = _r(
    r"\bcita\b", r"\bturno\b", r"\bpedir hora\b", r"\bsacar\b", r"\bagend", r"\bprogram\w* (una )?cita\b",
    r"\bnecesito (ver|ir|que me vea|un|una|el|la|al)\b", r"\bquiero (ver|ir|que me vea)\b", r"\bme (vea|revise)\b",
    r"\bconsulta\b", r"\bcontrol\b", r"\bformul", r"\bme mandaron\b", r"\bme remitieron\b", r"\bdeme\b",
    r"\bdolor\b", r"\bme duele\b", r"\btengo una orden\b", r"\bme siento (mal|maluco|enfermo)\b",
)
SALUDO = _r(r"^(hola|buenas|buenos dias|buenas tardes|buenas noches|alo|buen dia)\b", r"\bbuenos dias\b", r"\bbuenas tardes\b")
DESPEDIDA = _r(
    r"\bchao\b", r"\badios\b", r"\bhasta luego\b", r"\bhasta pronto\b", r"\beso es todo\b", r"\bnada mas\b",
    r"\bya no mas\b", r"^(muchas )?gracias\b", r"\bque dios le pague\b", r"\bbendiciones\b", r"\bme voy\b",
)
MENU = _r(r"\bempezar de nuevo\b", r"\bvolver al (menu|inicio)\b", r"^menu$", r"\bcomenzar otra vez\b", r"^inicio$", r"^reiniciar$")

AFIRMAR = _r(
    r"^(si|sip|aja|ok|okey|okay|listo|claro|dale|bueno|bien|exacto|correcto|perfecto|de una|hagale|eso|vale|obvio|seguro|por supuesto)\b",
    r"\bsi (senora|senor|mija|mijo|senorita|claro|por favor|gracias|esa|ese|asi)\b", r"\bclaro que si\b",
    r"\bas[ii] esta bien\b", r"\besta bien\b", r"\bme sirve\b", r"\bme parece bien\b", r"\bde acuerdo\b",
    r"\bconfirmo\b", r"\bpero claro\b", r"\bpues si\b", r"\beso es\b", r"\basi es\b", r"\bde una\b",
)
NEGAR = _r(
    r"^no\b(?!\s+(?:se|me acuerdo|recuerdo|entiendo|entendi|estoy segur[oa]|tengo|le entendi|escuche)\b)", r"\bno (senora|senor|mija|mijo|senorita|gracias|es esa|es ese|me sirve|puedo|quiero)\b",
    r"\bmejor no\b", r"\bni de riesgos\b", r"\bpara nada\b", r"\bde ninguna manera\b", r"\bnegativo\b",
    r"\bninguna\b", r"\bninguno\b", r"\bespere\b",
)
OPCION_1 = _r(r"\b(la|el|opcion|numero) (1|primera|primero)\b", r"^(1|primera|primero)\b", r"\bprimer[ao]\b", r"\bprimerit[ao]\b", r"\bla de arriba\b")
OPCION_2 = _r(r"\b(la|el|opcion|numero) (2|segunda|segundo)\b", r"^(2|segunda|segundo)\b", r"\bsegund[ao]\b", r"\bsegundit[ao]\b", r"\bultim[ao]\b", r"\bla de abajo\b")
OTRAS = _r(
    r"\bninguna\b", r"\bninguno\b", r"\botro dia\b", r"\botra fecha\b", r"\botra hora\b", r"\bmas tarde\b",
    r"\bmas temprano\b", r"\botras\b", r"\bno me sirve", r"\bno puedo ese dia\b", r"\botra (mas|opcion)\b",
    r"\btiene otra\b", r"\bhay otra\b", r"\bmas opciones\b", r"\bdespues\b",
)
DOCUMENTO = re.compile(r"\b(\d{5,11})\b")


GRUPOS_DIGITOS = re.compile(r"\d[\d\s.,-]*\d|\d")


def _documento(t: str) -> str | None:
    """Cédula aunque la dicten por grupos: '29 28 57 72', '2.92.85.772', '32-456-789', 'veintinueve 285 772'."""
    m = DOCUMENTO.search(t)
    for grupo in GRUPOS_DIGITOS.findall(t):
        digitos = re.sub(r"\D", "", grupo)
        if 5 <= len(digitos) <= 11:
            return digitos
    return m.group(1) if m else None


def _dia_semana(t: str) -> int | None:
    m = re.search(r"\b(?:la|el) del? (" + "|".join(DIAS) + r")\b", t)
    return DIAS[m.group(1)] if m else None


def interpretar(texto: str, contexto: str = "inicio", hoy: date | None = None) -> Interpretacion:
    hoy = hoy or date.today()
    t = normalizar(texto)
    # muletillas al comienzo: "uy si", "ay no mija", "eh pues quiero..."
    t = re.sub(r"^(?:(?:uy|ay|ah|eh|ehh|mmm|mm|pues|ve|oiga|mire|bueno pues)\s+)+(?=\w)", "", t)
    tiempo = extraer_tiempo(t, hoy)
    r = Interpretacion(
        texto=texto,
        especialidad=buscar_especialidad(t),
        fecha=tiempo.fecha,
        asap=tiempo.asap,
        franja=tiempo.franja,
        hora=tiempo.hora,
        fuente="reglas",
    )

    def decide(intencion: str, confianza: float = 0.9) -> Interpretacion:
        r.intencion, r.confianza = intencion, confianza
        return r

    if not t:
        return decide("desconocido", 0.0)

    # 1. Seguridad primero, en cualquier estado.
    if URGENCIA.search(t):
        return decide("urgencia", 0.95)
    if HUMANO.search(t):
        return decide("humano")
    if MENU.search(t):
        return decide("menu")

    # 2. Lo que el diálogo está esperando.
    if contexto == "esperando_documento":
        doc = _documento(t)
        if not doc and "," in texto:
            # "veintinueve, doscientos ochenta y cinco, setecientos setenta y dos": cada grupo por aparte
            doc = _documento(" ".join(normalizar(parte) for parte in texto.split(",")))
        if doc:
            r.documento = doc
            return decide("dar_documento", 0.95)

    if contexto == "esperando_opcion":
        if OPCION_1.search(t) and not OPCION_2.search(t):
            r.opcion = 1
            return decide("elegir_opcion")
        if OPCION_2.search(t):
            r.opcion = 2
            return decide("elegir_opcion")
        r.dia_semana = _dia_semana(t)
        if r.dia_semana is not None:
            return decide("elegir_opcion", 0.8)
        if OTRAS.search(t) or r.fecha or r.asap or (r.franja and not AFIRMAR.search(t)):
            return decide("otras_opciones")

    if contexto in ("esperando_confirmacion", "esperando_opcion", "esperando_cita"):
        if NEGAR.search(t):
            return decide("negar")
        if AFIRMAR.search(t):
            return decide("afirmar")

    if contexto == "esperando_cita":
        if OPCION_1.search(t) and not OPCION_2.search(t):
            r.opcion = 1
            return decide("elegir_opcion")
        if OPCION_2.search(t):
            r.opcion = 2
            return decide("elegir_opcion")
        if r.especialidad or r.fecha or _dia_semana(t) is not None:
            r.dia_semana = _dia_semana(t)
            return decide("elegir_opcion", 0.75)

    if REPETIR.search(t):
        return decide("repetir")

    # 3. Intenciones de negocio. Cancelar y reprogramar antes que consultar/agendar porque suelen
    #    mencionar "cita" ("tengo una cita y la quiero cancelar").
    if REPROGRAMAR.search(t):
        return decide("reprogramar")
    if CANCELAR.search(CANCELADA_POR_OTROS.sub(" ", t)):
        return decide("cancelar")
    if VOLVER_A_AGENDAR.search(t):
        return decide("agendar", 0.85)
    if CONSULTAR.search(t):
        return decide("consultar")
    if FUERA_ALCANCE.search(t) and not re.search(r"\bcita\b", t):
        return decide("fuera_alcance")

    if contexto == "esperando_especialidad" and r.especialidad:
        return decide("informar")
    if contexto == "esperando_fecha" and (r.fecha or r.asap or r.franja or r.hora):
        return decide("informar")

    if AGENDAR.search(t) or (r.especialidad and contexto == "inicio"):
        return decide("agendar", 0.9 if re.search(r"\bcita|turno|agend|sacar|pedir hora\b", t) else 0.75)
    if AYUDA.search(t):
        return decide("ayuda")
    if SALUDO.search(t):
        return decide("saludo")
    if DESPEDIDA.search(t):
        return decide("despedida")
    if r.especialidad or r.fecha or r.asap or r.franja:
        return decide("informar", 0.6)
    if contexto not in ("esperando_confirmacion", "esperando_opcion") and AFIRMAR.search(t):
        return decide("afirmar", 0.6)
    if NEGAR.search(t):
        return decide("negar", 0.6)
    return decide("desconocido", 0.2)
