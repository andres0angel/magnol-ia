"""Gestor de diálogo de Magnol-IA.

Principios de diseño para adultos mayores (validados en las entrevistas del Entregable 3):
- Frases cortas, trato de usted, "don/doña" + nombre.
- Máximo dos opciones por turno, en días distintos.
- Confirmación explícita (sí/no) antes de agendar, cambiar o cancelar.
- "Repítame" funciona siempre; tras dos malentendidos se ofrece hablar con una persona.
- Urgencias primero: ante síntomas graves se indica llamar al 123, sin importar el estado.
- Cuidadores: se puede pedir la cita para otra persona dando su cédula.
- El texto que se envía es el mismo que se dice en voz alta.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time

import holidays

from . import catalogo
from .agenda import Agenda, Cita, Opcion, Paciente
from .config import config
from .db import conectar
from .nlu import Interpretacion, hibrido
from .nlu.normalizar import normalizar
from .textos import DIAS, fecha_hablada, hora_hablada, profesional_hablado, tratamiento

log = logging.getLogger(__name__)

CONTEXTO = {
    "nuevo": "inicio", "menu": "inicio", "pedir_documento": "esperando_documento",
    "confirmar_identidad": "esperando_confirmacion", "pedir_nacimiento": "esperando_documento",
    "pedir_especialidad": "esperando_especialidad", "ofrecer_mg": "esperando_confirmacion",
    "ofrecer_agendar": "esperando_confirmacion", "elegir_opcion": "esperando_opcion",
    "pedir_fecha": "esperando_fecha", "confirmar_cita": "esperando_confirmacion",
    "elegir_cita": "esperando_cita", "confirmar_cancelacion": "esperando_confirmacion",
    "ya_tiene_cita": "esperando_confirmacion",
}
NEGOCIO = {"agendar", "consultar", "cancelar", "reprogramar"}
OTRA_PERSONA = re.compile(
    r"\bpara (mi|el|la) (mama|mamita|papa|papito|esposo|esposa|senora|marido|hermano|hermana|tio|tia|abuelo|abuela|"
    r"vecino|vecina|hijo|hija|suegra|suegro)\b|\botra persona\b|\bcambiar de paciente\b|\bno es para mi\b")
# "La cita del especialista", "la de la orden", "me remitieron": la persona no recuerda el nombre de la especialidad
ESPECIALISTA = re.compile(r"\bespecialista|\bla orden\b|\buna orden\b|\bme remiti|\bme mandaron (donde|con|a)\b|\bremision")
CRISIS = re.compile(r"\bmorir\b|\bmatarme\b|\bquitarme la vida\b|\bsuicid")
BOTONES_MENU = ["Quiero una cita", "¿Cuándo es mi cita?", "Cancelar una cita"]
BOTONES_SI_NO = ["Sí", "No"]


@dataclass
class Respuesta:
    texto: str
    botones: list[str] = field(default_factory=list)
    resultado: str | None = None


@dataclass
class Sesion:
    estado: str = "nuevo"
    paciente_id: int | None = None
    candidato_id: int | None = None
    pendiente: Interpretacion | None = None
    especialidad: str | None = None
    fecha: date | None = None
    fecha_explicita: bool = False        # dijo un día concreto ("el lunes", "el 25"), no "la otra semana"
    franja: str | None = None
    hora: time | None = None
    opciones: list[Opcion] = field(default_factory=list)
    excluir: list[int] = field(default_factory=list)
    dias_rechazados: set = field(default_factory=set)   # "ninguna de esas": no volver a ofrecer esos días
    elegida: Opcion | None = None
    citas: list[Cita] = field(default_factory=list)
    cita_objetivo: Cita | None = None
    accion: str | None = None            # agendar | cancelar | reprogramar
    orden_id: int | None = None
    fallos: int = 0
    fallos_documento: int = 0
    ultima: Respuesta | None = None
    ultimo_turno: datetime | None = None

    def limpiar_tarea(self) -> None:
        self.especialidad = self.fecha = self.franja = self.hora = None
        self.fecha_explicita = False
        self.opciones, self.excluir, self.citas = [], [], []
        self.dias_rechazados = set()
        self.elegida = self.cita_objetivo = None
        self.accion = None
        self.orden_id = None
        self.fallos = 0


class GestorDialogo:
    def __init__(self, con=None, interpretar=None):
        self.con = con or conectar()
        self.agenda = Agenda(self.con)
        self.interpretar = interpretar or hibrido.interpretar
        self.sesiones: dict[tuple[str, str], Sesion] = {}
        self._festivos = holidays.country_holidays("CO", years=range(2025, 2031))

    # ================================================================== entrada principal
    def procesar(self, canal: str, usuario_id: str, texto: str, es_voz: bool = False) -> Respuesta:
        ahora = config.ahora()
        clave = (canal, str(usuario_id))
        s = self.sesiones.get(clave)
        if s is None or (s.ultimo_turno and (ahora - s.ultimo_turno).total_seconds() > config.minutos_sesion * 60):
            s = Sesion()
            self.sesiones[clave] = s
        if s.paciente_id is None and s.estado == "nuevo":
            p = self.agenda.paciente_por_canal(canal, str(usuario_id))
            if p:
                s.paciente_id = p.id
        self._canal, self._usuario, self._ahora = canal, str(usuario_id), ahora

        interp = self.interpretar(texto, CONTEXTO.get(s.estado, "inicio"), ahora.date())
        estado_previo = s.estado
        try:
            resp = self._manejar(s, interp, texto)
        except Exception:  # nunca dejar a la persona sin respuesta
            log.exception("Error manejando el turno")
            s.estado = "menu"
            resp = Respuesta("Disculpe, tuve un problema. ¿Me puede repetir qué necesita?", BOTONES_MENU, "error")
        if interp.intencion != "repetir":
            s.ultima = resp
        s.ultimo_turno = ahora
        self.agenda.registrar_evento(
            ts=ahora.isoformat(timespec="seconds"), canal=canal, usuario_id=str(usuario_id), paciente_id=s.paciente_id,
            estado=estado_previo, intencion=interp.intencion, fuente_nlu=interp.fuente, es_voz=int(es_voz),
            texto_usuario=texto, respuesta=resp.texto, resultado=resp.resultado)
        return resp

    def reiniciar(self, canal: str, usuario_id: str, olvidar_paciente: bool = False) -> None:
        self.sesiones.pop((canal, str(usuario_id)), None)
        if olvidar_paciente:
            self.agenda.desvincular(canal, str(usuario_id))

    # ================================================================== utilidades
    @property
    def hoy(self) -> date:
        return self._ahora.date()

    def _paciente(self, s: Sesion) -> Paciente:
        return self.agenda.paciente(s.paciente_id)

    def _trato(self, s: Sesion) -> str:
        p = self._paciente(s)
        return tratamiento(p.nombres, p.sexo) if p else ""

    @staticmethod
    def _en_sede(nombre: str) -> str:
        return f"en la {nombre}" if nombre.startswith("Unidad") else f"en el {nombre}"

    def _desc_opcion(self, op: Opcion, sede_anterior: str | None = None) -> str:
        lugar = "en el mismo lugar" if sede_anterior == op.sede_id else self._en_sede(op.sede_nombre)
        return f"{fecha_hablada(op.inicio.date(), self.hoy)}, {hora_hablada(op.inicio)}, {lugar}"

    def _desc_completa(self, x, esp: str | None = None) -> str:
        esp = esp or x.especialidad
        return (f"{catalogo.nombre(esp)}, {fecha_hablada(x.inicio.date(), self.hoy)}, {hora_hablada(x.inicio)}, "
                f"{self._en_sede(x.sede_nombre)}, {x.sede_direccion}, con {profesional_hablado(x.profesional, x.genero, esp)}")

    def _fallo(self, s: Sesion, reprompt: str, botones: list[str] | None = None) -> Respuesta:
        s.fallos += 1
        if s.fallos >= 2:
            s.fallos = 0
            return Respuesta("Disculpe, no le estoy entendiendo bien. Puede decírmelo con otras palabras, "
                             "o si prefiere, diga: hablar con una persona.", (botones or []) + ["Hablar con una persona"],
                             "no_entendido")
        return Respuesta(f"Disculpe, no le entendí. {reprompt}", botones or [], "no_entendido")

    def _menu_texto(self, s: Sesion, saludo: str = "") -> Respuesta:
        s.estado = "menu"
        return Respuesta(f"{saludo}¿En qué le ayudo? Puede decirme, por ejemplo: quiero una cita, "
                         f"cuándo es mi cita, o quiero cancelar una cita.", BOTONES_MENU)

    def _algo_mas(self, s: Sesion, texto: str, resultado: str | None = None) -> Respuesta:
        s.limpiar_tarea()
        s.estado = "menu"
        return Respuesta(f"{texto} ¿Le ayudo con algo más?", ["No, gracias"] + BOTONES_MENU[:1], resultado)

    # ================================================================== router
    def _manejar(self, s: Sesion, i: Interpretacion, texto: str) -> Respuesta:
        t = normalizar(texto)
        if i.intencion == "urgencia":
            if CRISIS.search(t):
                return Respuesta("Lo que siente es importante. Si está pensando en hacerse daño, llame ya a la línea 123 "
                                 "o pídale a alguien cercano que lo acompañe. No tiene que pasar esto solo.", [], "urgencia")
            return Respuesta("Eso puede ser una urgencia. No espere una cita: llame ya a la línea de emergencias 123 "
                             "o vaya al servicio de urgencias más cercano. Si está solo, pida ayuda a un vecino o familiar.",
                             [], "urgencia")
        if i.intencion == "humano":
            s.estado = "menu" if s.paciente_id else s.estado
            if config.modo_demo:
                return Respuesta("Con gusto. En la versión real, en este momento le pasaría con una persona de la IPS. "
                                 "Esto es una demostración.", [], "humano")
            linea = config.linea_atencion or "la línea de atención de su IPS"
            return Respuesta(f"Con gusto. Para hablar con una persona, llame a {linea}.", [], "humano")
        if i.intencion == "repetir" and s.ultima:
            return Respuesta("Claro, le repito: " + s.ultima.texto, s.ultima.botones)
        if i.intencion == "menu":
            s.limpiar_tarea()
            if s.paciente_id is None:
                s.estado = "nuevo"
                return self._identificar(s, i)
            return self._menu_texto(s)

        if s.paciente_id is not None and OTRA_PERSONA.search(t) and s.estado in ("nuevo", "menu", "pedir_especialidad"):
            s.paciente_id, s.candidato_id = None, None
            s.pendiente = i if i.intencion in NEGOCIO else Interpretacion(intencion="agendar", especialidad=i.especialidad)
            s.estado = "pedir_documento"
            return Respuesta("Claro. Dígame el número de cédula de la persona que necesita la cita, número por número.")

        if s.paciente_id is None:
            return self._identificar(s, i)

        manejador = getattr(self, f"_en_{s.estado}", None)
        return manejador(s, i) if manejador else self._en_menu(s, i)

    # ================================================================== identificación
    def _identificar(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if s.estado == "confirmar_identidad":
            if i.intencion == "afirmar":
                return self._vincular(s)
            if i.intencion == "negar":
                s.estado, s.candidato_id = "pedir_documento", None
                return Respuesta("Disculpe. Dígame otra vez el número de cédula, despacio, número por número.")
            if i.documento or re.search(r"\d{5,}", i.texto):
                s.estado = "pedir_documento"
            else:
                p = self.agenda.paciente(s.candidato_id)
                return self._fallo(s, f"¿Su nombre es {p.nombres} {p.apellidos}? Diga sí o no.", BOTONES_SI_NO)

        if s.estado == "pedir_nacimiento":
            anio = re.search(r"\b(19\d{2}|20[0-2]\d)\b", normalizar(i.texto))
            p = self.agenda.paciente(s.candidato_id)
            if anio and p and self.con.execute("SELECT fecha_nacimiento FROM pacientes WHERE id=?", (p.id,)).fetchone()[0][:4] == anio.group(1):
                return self._vincular(s)
            s.fallos_documento += 1
            s.estado = "pedir_documento"
            return Respuesta("Los datos no coinciden. Dígame otra vez el número de cédula, número por número.")

        if s.estado in ("pedir_documento", "confirmar_identidad"):
            doc = i.documento or (re.search(r"\b(\d{5,11})\b", normalizar(i.texto)) or [None, None])[1]
            if not doc:
                if i.intencion in NEGOCIO:
                    s.pendiente = i
                return Respuesta("Para buscar sus citas necesito el número de cédula de la persona que va a la cita. "
                                 "Dígamelo número por número.")
            p = self.agenda.paciente_por_documento(doc)
            if not p:
                s.fallos_documento += 1
                if s.fallos_documento >= 3:
                    s.fallos_documento = 0
                    return Respuesta("No encuentro esa cédula en el sistema. Puede ser que la persona no esté inscrita en esta IPS. "
                                     "Si quiere, diga: hablar con una persona.", ["Hablar con una persona"], "no_encontrado")
                if config.modo_demo:
                    # En la demo los pacientes son inventados: una cédula real nunca va a aparecer
                    return Respuesta("No encontré esa cédula. Como esta es una demostración, los pacientes son "
                                     "inventados: use una cédula de prueba, por ejemplo la 32456789.")
                return Respuesta("No encontré esa cédula. ¿Me la repite, despacio, número por número?")
            s.candidato_id = p.id
            if config.verificar_nacimiento:
                s.estado = "pedir_nacimiento"
                return Respuesta("Gracias. Para proteger sus datos, ¿en qué año nació la persona que va a la cita?")
            s.estado = "confirmar_identidad"
            return Respuesta(f"Encontré a {p.nombres} {p.apellidos}. ¿Es correcto?", BOTONES_SI_NO)

        # Primer contacto sin identificar
        if i.intencion in NEGOCIO:
            s.pendiente = i
        s.estado = "pedir_documento"
        aviso = " Esta es una demostración académica con datos simulados." if config.modo_demo else ""
        if i.documento or re.search(r"\b\d{5,11}\b", normalizar(i.texto)):
            return self._identificar(s, i)
        return Respuesta(f"Hola, soy Magnol-IA, la asistente de citas médicas de {config.ips_nombre}.{aviso} "
                         "Para empezar, dígame el número de cédula de la persona que necesita la cita.")

    def _vincular(self, s: Sesion) -> Respuesta:
        s.paciente_id = s.candidato_id
        s.fallos_documento = 0
        self.agenda.vincular(self._canal, self._usuario, s.paciente_id, self._ahora)
        pendiente, s.pendiente = s.pendiente, None
        if pendiente:
            s.estado = "menu"
            r = self._en_menu(s, pendiente)
            r.texto = f"Mucho gusto, {self._trato(s)}. " + r.texto
            return r
        return self._menu_texto(s, f"Mucho gusto, {self._trato(s)}. ")

    # ================================================================== estados
    def _en_nuevo(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion in NEGOCIO or (i.intencion == "informar" and i.especialidad):
            r = self._en_menu(s, i)
            r.texto = f"Hola, {self._trato(s)}. " + r.texto
            return r
        return self._menu_texto(s, f"Hola, {self._trato(s)}. Soy Magnol-IA, su asistente de citas. ")

    def _en_menu(self, s: Sesion, i: Interpretacion) -> Respuesta:
        s.estado = "menu"
        intencion = i.intencion
        if intencion == "informar" and i.especialidad:
            intencion = "agendar"
        if intencion == "agendar":
            s.limpiar_tarea()
            s.accion = "agendar"
            self._actualizar_preferencias(s, i)
            if i.especialidad:
                return self._con_especialidad(s, i.especialidad)
            if ESPECIALISTA.search(normalizar(i.texto or "")):
                return self._especialista_por_orden(s)
            s.estado = "pedir_especialidad"
            return Respuesta("Claro. ¿Con quién necesita la cita? Por ejemplo: médico general, odontología, "
                             "o el especialista que le hayan ordenado.", ["Médico general", "Odontología", "Otro especialista"])
        if intencion == "consultar":
            return self._consultar(s, i)
        if intencion in ("cancelar", "reprogramar"):
            return self._seleccionar_cita(s, i, intencion)
        if intencion == "saludo":
            return self._menu_texto(s, f"Hola, {self._trato(s)}. ")
        if intencion in ("despedida", "negar"):
            s.limpiar_tarea()
            return Respuesta(f"Con mucho gusto, {self._trato(s)}. Que esté muy bien.", [], "despedida")
        if intencion == "afirmar":
            return Respuesta("Claro, dígame en qué le ayudo: sacar una cita, saber cuándo es su cita, cambiarla o cancelarla.",
                             BOTONES_MENU)
        if intencion == "ayuda":
            return Respuesta("Yo le ayudo con sus citas médicas, hablando como con una persona. Puedo sacarle una cita, "
                             "decirle cuándo y dónde es su próxima cita, cambiarla para otro día o cancelarla. "
                             "Puede hablarme con notas de voz o escribirme. ¿Qué necesita?", BOTONES_MENU)
        if intencion == "fuera_alcance":
            return Respuesta("Por ahora solo le puedo ayudar con citas: sacar, consultar, cambiar o cancelar. "
                             "Para resultados, historia clínica o pagos, comuníquese con su sede. ¿Le ayudo con una cita?",
                             BOTONES_MENU)
        return self._fallo(s, "Puede decirme: quiero una cita, cuándo es mi cita, o cancelar mi cita.", BOTONES_MENU)

    # ---------------------------------------------------------------- agendar
    def _con_especialidad(self, s: Sesion, codigo: str) -> Respuesta:
        esp = catalogo.especialidades()[codigo]
        s.fallos = 0
        if not esp.disponible:
            s.estado = "ofrecer_mg"
            if esp.portafolio_metrosalud:
                explicacion = (f"Las citas de {esp.nombre} se dan con una orden del médico general y no se agendan "
                               "por este medio. ")
            else:
                explicacion = (f"Esta red no presta {esp.nombre}. Para esa especialidad, el médico general le da una orden "
                               "y su EPS le asigna la cita en otra institución; no se agendan por este medio. ")
            return Respuesta(f"{explicacion}¿Le saco una cita con medicina general?", BOTONES_SI_NO)
        if s.accion == "agendar":
            existentes = [c for c in self.agenda.citas_futuras(s.paciente_id, self._ahora) if c.especialidad == codigo]
            if existentes:
                s.cita_objetivo = existentes[0]
                s.estado = "ya_tiene_cita"
                return Respuesta(f"Usted ya tiene una cita de {self._desc_corta(existentes[0])}, "
                                 f"{self._en_sede(existentes[0].sede_nombre)}. ¿Quiere cambiarla para otro día?", BOTONES_SI_NO)
        prefacio = ""
        if esp.requiere_orden:
            s.orden_id = self.agenda.orden_activa(s.paciente_id, codigo, self.hoy)
            if not s.orden_id:
                s.estado = "ofrecer_mg"
                return Respuesta(f"Para {esp.nombre} se necesita una orden del médico general, y no veo una orden vigente "
                                 "a su nombre. ¿Le saco una cita con medicina general?", BOTONES_SI_NO)
            prefacio = f"Veo que tiene una orden para {esp.nombre}. "
        s.especialidad = codigo
        return self._buscar_y_ofrecer(s, prefacio)

    def _buscar_y_ofrecer(self, s: Sesion, prefacio: str = "") -> Respuesta:
        p = self._paciente(s)
        def buscar(**kw):
            r = self.agenda.buscar_opciones(p, s.especialidad, self._ahora, excluir=s.excluir,
                                            excluir_dias=s.dias_rechazados, **kw)
            return r or (self.agenda.buscar_opciones(p, s.especialidad, self._ahora, excluir=s.excluir, **kw)
                         if s.dias_rechazados else r)
        opciones = buscar(desde=s.fecha, franja=s.franja, hora=s.hora)
        nota = ""
        if s.fecha and s.fecha in self._festivos and s.fecha_explicita:
            nota = f"El {DIAS[s.fecha.weekday()]} {s.fecha.day} es festivo. "
        if not opciones and (s.franja or s.hora):
            opciones = buscar(desde=s.fecha)
            nota += "En ese horario no me quedan citas. " if opciones else ""
        if not opciones and s.fecha:
            opciones = buscar()
            nota += "Para esa fecha no me quedan citas. " if opciones else ""
        if s.fecha and opciones and opciones[0].inicio.date() != s.fecha and s.fecha_explicita:
            nota += "Las más cercanas son estas. " if nota else "Para ese día no me quedan citas. Las más cercanas son estas. "
        if not opciones:
            nombre = catalogo.nombre(s.especialidad)
            s.limpiar_tarea()
            s.estado = "menu"
            return Respuesta(f"{prefacio}En este momento no hay citas disponibles de {nombre} en los próximos dos meses. "
                             "Le recomiendo comunicarse con su sede. ¿Le ayudo con algo más?", BOTONES_MENU, "sin_cupos")
        s.opciones = opciones
        nombre = catalogo.nombre(s.especialidad)
        if len(opciones) == 1:
            s.elegida = opciones[0]
            s.estado = "confirmar_cita"
            return Respuesta(f"{prefacio}{nota}Encontré esta cita disponible de {nombre}: {self._desc_opcion(opciones[0])}. "
                             "¿Le sirve? Diga sí o no.", BOTONES_SI_NO)
        s.estado = "elegir_opcion"
        return Respuesta(
            f"{prefacio}{nota}Encontré dos citas disponibles de {nombre}. La primera: {self._desc_opcion(opciones[0])}. "
            f"La segunda: {self._desc_opcion(opciones[1], opciones[0].sede_id)}. "
            "¿Cuál prefiere, la primera o la segunda? Si ninguna le sirve, dígame otro día o si la prefiere en la tarde.",
            ["La primera", "La segunda", "Otro día"])

    def _en_pedir_especialidad(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.especialidad:
            s.fecha = i.fecha or s.fecha
            s.franja = i.franja or s.franja
            return self._con_especialidad(s, i.especialidad)
        if i.intencion in NEGOCIO - {"agendar"} or i.intencion in ("despedida", "ayuda", "fuera_alcance"):
            return self._en_menu(s, i)
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno.")
        if ESPECIALISTA.search(normalizar(i.texto or "")):
            return self._especialista_por_orden(s)
        return self._fallo(s, "¿La cita es con medicina general, odontología, u otro especialista?",
                           ["Médico general", "Odontología"])

    def _especialista_por_orden(self, s: Sesion) -> Respuesta:
        """Pidió 'el especialista' sin decir cuál: se usa la orden vigente que tenga."""
        esps = catalogo.especialidades()
        ordenes = [c for c in self.agenda.ordenes_activas(s.paciente_id, self.hoy) if c in esps and esps[c].disponible]
        if len(ordenes) == 1:
            return self._con_especialidad(s, ordenes[0])
        if ordenes:
            nombres = [catalogo.nombre(c) for c in ordenes]
            s.estado = "pedir_especialidad"
            return Respuesta(f"Veo que tiene órdenes para {', '.join(nombres[:-1])} y {nombres[-1]}. "
                             "¿Para cuál le busco la cita?", [n[0].upper() + n[1:] for n in nombres])
        s.estado = "ofrecer_mg"
        return Respuesta("No veo órdenes vigentes a su nombre, y para ir al especialista se necesita una orden del médico "
                         "general. ¿Le saco una cita con medicina general?", BOTONES_SI_NO)

    def _en_ya_tiene_cita(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion in ("afirmar", "reprogramar") or i.fecha or i.franja:
            s.accion = "reprogramar"
            self._actualizar_preferencias(s, i)
            return self._con_cita(s, s.cita_objetivo)
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno, su cita sigue igual.")
        if i.intencion in NEGOCIO:
            return self._en_menu(s, i)
        return self._fallo(s, "¿Quiere cambiar esa cita para otro día? Diga sí o no.", BOTONES_SI_NO)

    def _en_ofrecer_mg(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion == "afirmar":
            s.orden_id = None
            return self._con_especialidad(s, "medicina_general")
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno.")
        if i.especialidad:
            return self._con_especialidad(s, i.especialidad)
        if i.intencion in NEGOCIO:
            return self._en_menu(s, i)
        return self._fallo(s, "¿Le saco una cita con medicina general? Diga sí o no.", BOTONES_SI_NO)

    def _actualizar_preferencias(self, s: Sesion, i: Interpretacion) -> bool:
        cambio = False
        if i.fecha or i.asap:
            s.fecha = None if i.asap else i.fecha
            s.fecha_explicita = bool(re.search(r"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo|\d{1,2})\b",
                                               normalizar(i.texto)))
            cambio = True
        if i.franja:
            s.franja, cambio = i.franja, True
        if i.hora:
            s.hora, cambio = i.hora, True
        return cambio

    def _en_elegir_opcion(self, s: Sesion, i: Interpretacion) -> Respuesta:
        elegida = None
        if i.intencion == "elegir_opcion":
            if i.opcion and 1 <= i.opcion <= len(s.opciones):
                elegida = s.opciones[i.opcion - 1]
            elif i.dia_semana is not None:
                coinciden = [o for o in s.opciones if o.inicio.weekday() == i.dia_semana]
                elegida = coinciden[0] if len(coinciden) == 1 else None
        elif i.intencion == "afirmar" and len(s.opciones) == 1:
            elegida = s.opciones[0]
        if elegida:
            s.elegida = elegida
            s.estado = "confirmar_cita"
            s.fallos = 0
            if s.accion == "reprogramar":
                return Respuesta(f"Le confirmo el cambio: su cita pasaría para {self._desc_completa(elegida)}. "
                                 "¿Hago el cambio? Diga sí o no.", BOTONES_SI_NO)
            return Respuesta(f"Le confirmo: cita de {self._desc_completa(elegida)}. ¿Se la agendo? Diga sí o no.", BOTONES_SI_NO)
        if i.intencion in ("otras_opciones", "informar") or self._actualizar_preferencias(s, i):
            self._actualizar_preferencias(s, i)
            s.excluir.extend(o.cupo_id for o in s.opciones)
            if re.search(r"\b(ninguna|ninguno|no me sirve|otro dia|otra fecha)\b", normalizar(i.texto)):
                s.dias_rechazados.update(o.inicio.date() for o in s.opciones)
            if i.intencion == "otras_opciones" and not (i.fecha or i.asap or i.franja or i.hora) and \
                    re.search(r"\b(otro dia|otra fecha|ninguna|no me sirve)\b", normalizar(i.texto)):
                s.estado = "pedir_fecha"
                return Respuesta("Con gusto. ¿Qué día o en qué horario le queda mejor? Por ejemplo: la otra semana, "
                                 "el lunes, o en la tarde.", ["La otra semana", "En la mañana", "En la tarde"])
            return self._buscar_y_ofrecer(s)
        if i.intencion == "negar":
            s.estado = "pedir_fecha"
            return Respuesta("Bueno. ¿Qué día o en qué horario le queda mejor? Por ejemplo: la otra semana, o en la tarde.",
                             ["La otra semana", "En la mañana", "En la tarde"])
        if i.intencion in NEGOCIO - {"agendar"} or i.intencion in ("despedida",):
            return self._en_menu(s, i)
        return self._fallo(s, "¿Prefiere la primera o la segunda?", ["La primera", "La segunda", "Otro día"])

    def _en_pedir_fecha(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if self._actualizar_preferencias(s, i):
            s.fallos = 0
            return self._buscar_y_ofrecer(s)
        if i.intencion in ("afirmar", "otras_opciones"):
            return self._buscar_y_ofrecer(s)
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno, no le agendo nada por ahora.")
        if i.intencion in NEGOCIO - {"agendar"} or i.intencion == "despedida":
            return self._en_menu(s, i)
        return self._fallo(s, "Dígame un día, por ejemplo el lunes o la otra semana, o si la quiere en la mañana o en la tarde.",
                           ["La otra semana", "En la mañana", "En la tarde"])

    def _en_confirmar_cita(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion == "afirmar":
            op = s.elegida
            if s.accion == "reprogramar" and s.cita_objetivo:
                nueva = self.agenda.reprogramar(s.cita_objetivo.id, s.paciente_id, op.cupo_id, self._canal, self._ahora)
                resultado, verbo = "cita_reprogramada", "Su cita quedó cambiada para"
            else:
                nueva = self.agenda.reservar(s.paciente_id, op.cupo_id, self._canal, self._ahora, s.orden_id)
                resultado, verbo = "cita_agendada", "Su cita quedó agendada:"
            if nueva is None:  # alguien tomó ese cupo segundos antes
                s.excluir.append(op.cupo_id)
                return self._buscar_y_ofrecer(s, "Uy, esa cita la acaban de tomar. ")
            texto = (f"Listo, {self._trato(s)}. {verbo} {self._desc_completa(op)}. "
                     "Recuerde llegar 20 minutos antes con su cédula.")
            return self._algo_mas(s, texto, resultado)
        if i.intencion == "negar" or i.intencion in ("otras_opciones",) or self._actualizar_preferencias(s, i):
            if i.intencion == "negar" and len(s.opciones) == 2 and not (i.fecha or i.franja):
                otra = s.opciones[1] if s.elegida == s.opciones[0] else s.opciones[0]
                s.excluir.append(s.elegida.cupo_id)
                s.opciones = [otra]
                s.estado = "elegir_opcion"
                return Respuesta(f"Bueno. ¿Prefiere la otra opción, {self._desc_opcion(otra)}? Diga sí, u otro día.",
                                 ["Sí, esa", "Otro día"])
            s.excluir.extend(o.cupo_id for o in s.opciones)
            if i.intencion == "negar" and not (i.fecha or i.franja or i.hora):
                s.estado = "pedir_fecha"
                return Respuesta("Bueno. ¿Qué día o en qué horario le queda mejor?", ["La otra semana", "En la mañana", "En la tarde"])
            return self._buscar_y_ofrecer(s)
        if i.intencion == "elegir_opcion":
            s.estado = "elegir_opcion"
            return self._en_elegir_opcion(s, i)
        return self._fallo(s, "¿Se la agendo? Diga sí o no.", BOTONES_SI_NO)

    # ---------------------------------------------------------------- consultar
    def _consultar(self, s: Sesion, i: Interpretacion) -> Respuesta:
        citas = self.agenda.citas_futuras(s.paciente_id, self._ahora)
        if i.especialidad:
            citas = [c for c in citas if c.especialidad == i.especialidad] or citas
        if not citas:
            s.estado = "ofrecer_agendar"
            return Respuesta("No tiene citas programadas. ¿Quiere que le saque una?", BOTONES_SI_NO, "consulta")
        if len(citas) == 1:
            texto = f"Tiene una cita de {self._desc_completa(citas[0])}."
        else:
            partes = [f"La {'primera' if n == 0 else 'segunda' if n == 1 else 'tercera'}: {self._desc_completa(c)}."
                      for n, c in enumerate(citas[:3])]
            texto = f"Tiene {len(citas)} citas. " + " ".join(partes)
        return self._algo_mas(s, texto, "consulta")

    def _en_ofrecer_agendar(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion == "afirmar":
            return self._en_menu(s, Interpretacion(intencion="agendar", especialidad=i.especialidad))
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno.")
        return self._en_menu(s, i)

    # ---------------------------------------------------------------- cancelar / reprogramar
    def _seleccionar_cita(self, s: Sesion, i: Interpretacion, accion: str) -> Respuesta:
        s.limpiar_tarea()
        s.accion = accion
        if accion == "reprogramar":  # "cámbiemela para el viernes en la tarde"
            self._actualizar_preferencias(s, i)
        citas = self.agenda.citas_futuras(s.paciente_id, self._ahora)
        verbo = "cancelar" if accion == "cancelar" else "cambiar"
        if not citas:
            if accion == "reprogramar":
                s.estado = "ofrecer_agendar"
                return Respuesta("No tiene citas programadas para cambiar. ¿Quiere que le saque una nueva?", BOTONES_SI_NO)
            return self._algo_mas(s, "No tiene citas programadas para cancelar.")
        filtradas = self._filtrar_citas(citas, i, usar_fecha=accion == "cancelar")
        if len(filtradas) == 1:
            return self._con_cita(s, filtradas[0])
        s.citas = (filtradas or citas)[:2]
        s.estado = "elegir_cita"
        return Respuesta(f"Tiene {len(citas)} citas. ¿Cuál quiere {verbo}? La primera: {self._desc_corta(s.citas[0])}. "
                         f"La segunda: {self._desc_corta(s.citas[1])}.", ["La primera", "La segunda"])

    def _desc_corta(self, c: Cita) -> str:
        return f"{catalogo.nombre(c.especialidad)}, {fecha_hablada(c.inicio.date(), self.hoy)}, {hora_hablada(c.inicio)}"

    @staticmethod
    def _filtrar_citas(citas: list[Cita], i: Interpretacion, usar_fecha: bool = True) -> list[Cita]:
        r = citas
        if i.especialidad:
            r = [c for c in r if c.especialidad == i.especialidad] or r
        if usar_fecha and i.fecha:
            r = [c for c in r if c.inicio.date() == i.fecha] or r
        if i.dia_semana is not None:
            r = [c for c in r if c.inicio.weekday() == i.dia_semana] or r
        return r

    def _con_cita(self, s: Sesion, cita: Cita) -> Respuesta:
        s.cita_objetivo = cita
        s.fallos = 0
        if s.accion == "cancelar":
            s.estado = "confirmar_cancelacion"
            return Respuesta(f"Su cita es de {self._desc_corta(cita)}, {self._en_sede(cita.sede_nombre)}. ¿Seguro que la quiere cancelar? "
                             "Diga sí o no.", BOTONES_SI_NO)
        s.especialidad = cita.especialidad
        s.excluir = [cita.cupo_id]
        return self._buscar_y_ofrecer(s, f"Su cita actual es de {self._desc_corta(cita)}. Le busco otra fecha. ")

    def _en_elegir_cita(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion == "elegir_opcion" and i.opcion and 1 <= i.opcion <= len(s.citas):
            return self._con_cita(s, s.citas[i.opcion - 1])
        filtradas = self._filtrar_citas(s.citas, i)
        if (i.especialidad or i.fecha or i.dia_semana is not None) and len(filtradas) == 1:
            return self._con_cita(s, filtradas[0])
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno, no cambio nada.")
        return self._fallo(s, "¿La primera o la segunda?", ["La primera", "La segunda"])

    def _en_confirmar_cancelacion(self, s: Sesion, i: Interpretacion) -> Respuesta:
        if i.intencion == "afirmar":
            c = s.cita_objetivo
            ok = self.agenda.cancelar(c.id, s.paciente_id, self._ahora)
            if not ok:
                return self._algo_mas(s, "Esa cita ya no aparece como programada.")
            return self._algo_mas(s, f"Listo, cancelé su cita de {self._desc_corta(c)}. Gracias por avisar: "
                                     "así ese espacio le sirve a otra persona.", "cita_cancelada")
        if i.intencion == "negar":
            return self._algo_mas(s, "Bueno, su cita sigue igual.")
        if i.intencion == "reprogramar":
            s.accion = "reprogramar"
            return self._con_cita(s, s.cita_objetivo)
        return self._fallo(s, "¿La cancelo? Diga sí o no.", BOTONES_SI_NO)
