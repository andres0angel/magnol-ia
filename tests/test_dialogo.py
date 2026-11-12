from magnolia.config import config


def identificar(charla, cedula="43527891"):
    charla("hola")
    assert "Encontré" in charla(cedula)
    assert "Mucho gusto" in charla("sí")


def test_flujo_completo_agendar(charla, gestor):
    identificar(charla, "32456789")  # doña Rosa: sin citas
    assert "dos citas disponibles de medicina general" in charla("necesito una cita con el médico")
    assert "Le confirmo" in charla("la primera")
    texto = charla("sí señora")
    assert "quedó agendada" in texto and "20 minutos antes" in texto
    n = gestor.con.execute("SELECT COUNT(*) FROM citas WHERE paciente_id=3 AND estado='programada' AND canal='prueba'").fetchone()[0]
    assert n == 1


def test_intencion_antes_de_identificarse_se_conserva(charla):
    assert "cédula" in charla("quiero cancelar mi cita")
    charla("8345678")
    assert "¿Cuál quiere cancelar?" in charla("sí")  # don José tiene dos citas


def test_cancelar_libera_el_cupo(charla, gestor):
    identificar(charla, "8345678")
    charla("quiero cancelar la cita del odontólogo")
    assert "cancelé" in charla("sí")
    cupo = gestor.con.execute("SELECT c.estado FROM citas ci JOIN cupos c ON c.id=ci.cupo_id "
                              "WHERE ci.paciente_id=2 AND ci.especialidad='odontologia'").fetchone()[0]
    assert cupo == "libre"


def test_reprogramar_es_atomico(charla, gestor):
    identificar(charla, "8345678")
    assert "Le busco otra fecha" in charla("me cambia la cita del médico")
    charla("la primera")
    assert "quedó cambiada" in charla("sí")
    estados = [r[0] for r in gestor.con.execute(
        "SELECT estado FROM citas WHERE paciente_id=2 AND especialidad='medicina_general' ORDER BY id")]
    assert estados == ["reprogramada", "programada"]


def test_especialista_sin_orden_ofrece_medicina_general(charla):
    identificar(charla, "32456789")
    assert "se necesita una orden" in charla("quiero cita con la nutricionista")
    assert "medicina general" in charla("sí")


def test_especialista_con_orden(charla, gestor):
    identificar(charla)  # doña María tiene orden de medicina interna
    assert "Veo que tiene una orden" in charla("cita con el internista")
    charla("la segunda")
    charla("sí")
    estado = gestor.con.execute("SELECT estado FROM ordenes WHERE paciente_id=1 AND especialidad='medicina_interna'").fetchone()[0]
    assert estado == "usada"


def test_no_duplica_citas_de_la_misma_especialidad(charla):
    identificar(charla)  # doña María ya tiene medicina general
    assert "ya tiene una cita de medicina general" in charla("quiero cita con el médico general")


def test_especialidad_no_disponible(charla):
    identificar(charla, "32456789")
    respuesta = charla("necesito el cardiólogo")
    assert "no se agendan por este medio" in respuesta
    assert "no presta cardiología" in respuesta      # Metrosalud no tiene cardiología en su portafolio


def test_especialidad_de_la_red_que_no_se_agenda_por_aqui(charla):
    identificar(charla, "32456789")
    respuesta = charla("necesito cita con el de los huesos")
    assert "ortopedia se dan con una orden" in respuesta  # sí está en el portafolio, pero no por este canal
    assert "no presta" not in respuesta


def test_urgencia_interrumpe_cualquier_estado(charla):
    identificar(charla, "32456789")
    charla("quiero una cita con el médico")
    assert "123" in charla("ay me duele mucho el pecho")


def test_repetir(charla):
    identificar(charla, "32456789")
    oferta = charla("quiero una cita con el médico")
    assert charla("¿cómo? repítame").endswith(oferta)


def test_cedula_desconocida_tres_veces(charla):
    charla("hola")
    charla("11111111")
    charla("22222222")
    assert "hablar con una persona" in charla("33333333")


def test_cuidador_cambia_de_paciente(charla):
    identificar(charla)
    assert "cédula de la persona" in charla("quiero una cita para mi esposo")
    assert "José Aníbal" in charla("8345678")


def test_festivo_explicito(charla):
    identificar(charla, "32456789")
    assert "es festivo" in charla("una cita con el médico para el lunes")


def test_cupo_tomado_por_otra_persona(charla, gestor):
    identificar(charla, "32456789")
    charla("quiero una cita con el médico")
    charla("la primera")
    sesion = gestor.sesiones[("prueba", "u1")]
    gestor.con.execute("UPDATE cupos SET estado='ocupado' WHERE id=?", (sesion.elegida.cupo_id,))  # alguien se adelantó
    assert "la acaban de tomar" in charla("sí")


def test_identidad_recordada_por_canal(gestor):
    gestor.procesar("prueba", "u9", "hola")
    gestor.procesar("prueba", "u9", "43527891")
    gestor.procesar("prueba", "u9", "sí")
    gestor.reiniciar("prueba", "u9")  # nueva sesión, mismo usuario de Telegram
    assert "doña María" in gestor.procesar("prueba", "u9", "hola").texto


def test_eventos_para_metricas(charla, gestor):
    identificar(charla, "32456789")
    charla("quiero una cita con el médico")
    charla("la primera")
    charla("sí")
    resultados = [r[0] for r in gestor.con.execute("SELECT resultado FROM eventos WHERE resultado IS NOT NULL")]
    assert "cita_agendada" in resultados


def test_verificacion_por_anio(charla, monkeypatch):
    monkeypatch.setattr(config, "verificar_nacimiento", True)
    charla("hola")
    assert "año nació" in charla("32456789")
    anio = config.ahora().year - 68
    assert "Mucho gusto" in charla(f"en el {anio}")


def test_ninguna_no_repite_los_mismos_dias(charla, gestor):
    identificar(charla, "32456789")
    charla("quiero una cita con el médico")
    dias_antes = {o.inicio.date() for o in gestor.sesiones[("prueba", "u1")].opciones}
    charla("ninguna, mejor la otra semana por la mañana")
    dias_despues = {o.inicio.date() for o in gestor.sesiones[("prueba", "u1")].opciones}
    assert dias_despues and not (dias_antes & dias_despues)


def test_especialista_sin_nombre_usa_la_orden_vigente(charla):
    identificar(charla)  # doña María tiene orden de medicina interna
    assert "orden para medicina interna" in charla("necesito la cita del especialista")


def test_boton_otro_especialista_usa_la_orden_vigente(charla):
    identificar(charla)
    charla("quiero una cita")
    assert "orden para medicina interna" in charla("Otro especialista")


def test_especialista_sin_nombre_y_sin_orden(charla):
    identificar(charla, "32456789")  # doña Rosa no tiene órdenes
    assert "No veo órdenes vigentes" in charla("me remitieron al especialista")


def test_cedula_real_en_la_demo_sugiere_una_de_prueba(charla):
    charla("hola")
    respuesta = charla("1000640329")
    assert "No encontré esa cédula" in respuesta
    assert "32456789" in respuesta


def test_cedulas_fijas_faciles(charla):
    charla("hola")
    assert "Luz Marina" in charla("uno dos tres")


def test_cedula_000(charla):
    charla("hola")
    assert "Jesús Antonio" in charla("000")
