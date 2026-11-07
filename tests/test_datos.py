"""La base generada respeta los datos reales con que se calibra."""
import csv
import sqlite3

from conftest import RAIZ

REALES = RAIZ / "datos" / "reales"


def _con(db_base):
    con = sqlite3.connect(db_base)
    con.row_factory = sqlite3.Row
    return con


def test_todas_las_sedes_tienen_coordenadas_y_comuna(db_base):
    con = _con(db_base)
    sin_geo = con.execute("SELECT nombre FROM sedes WHERE latitud IS NULL OR longitud IS NULL OR comuna IS NULL").fetchall()
    assert not sin_geo
    lat_min, lat_max, lon_min, lon_max = con.execute(
        "SELECT min(latitud), max(latitud), min(longitud), max(longitud) FROM sedes").fetchone()
    assert 6.1 < lat_min and lat_max < 6.4 and -75.75 < lon_min and lon_max < -75.45  # dentro de Medellín


def test_uh_de_referencia_es_la_mas_cercana(db_base):
    import math

    con = _con(db_base)
    uhs = con.execute("SELECT id, latitud, longitud FROM sedes WHERE tipo='UH'").fetchall()
    for cs in con.execute("SELECT * FROM sedes WHERE tipo='CS'"):
        cercana = min(uhs, key=lambda u: math.dist((u["latitud"], u["longitud"]), (cs["latitud"], cs["longitud"])))
        assert cs["uh_referencia"] == cercana["id"], cs["nombre"]


def test_agenda_respeta_horario_real_de_cada_centro(db_base):
    con = _con(db_base)
    # Centro de Salud Trinidad atiende de 7 a. m. a 3 p. m.; Enciso, hasta las 7 p. m. (Gobernación de Antioquia)
    fin_trinidad = con.execute("SELECT max(time(fin)) FROM cupos WHERE sede_id='050010217814'").fetchone()[0]
    fin_enciso = con.execute("SELECT max(time(fin)) FROM cupos WHERE sede_id='050010217820'").fetchone()[0]
    assert fin_trinidad <= "15:00:00"
    assert fin_enciso > "17:00:00"
    sabados = con.execute("SELECT count(*) FROM cupos WHERE strftime('%w', inicio) IN ('0', '6')").fetchone()[0]
    assert sabados == 0


def test_reparto_de_eps_parecido_al_de_metrosalud(db_base):
    con = _con(db_base)
    total = con.execute("SELECT count(*) FROM pacientes").fetchone()[0]
    savia_sub = con.execute("SELECT count(*) FROM pacientes WHERE eps='Savia Salud' AND regimen='subsidiado'").fetchone()[0]
    ppna = con.execute("SELECT count(*) FROM pacientes WHERE regimen='no asegurado'").fetchone()[0]
    assert 0.65 < savia_sub / total < 0.85   # real: 75 %
    assert 0.08 < ppna / total < 0.22        # real: 15 %


def test_mayoria_de_pacientes_son_mujeres_como_en_la_piramide_dane(db_base):
    con = _con(db_base)
    mujeres = con.execute("SELECT avg(sexo='F') FROM pacientes").fetchone()[0]
    assert 0.52 < mujeres < 0.68             # real: 60 %


def test_georreferenciado_cubre_todas_las_sedes_con_citas():
    with open(RAIZ / "datos" / "catalogos" / "sedes_atributos.csv", encoding="utf-8") as f:
        con_citas = {r["codigo_habilitacion_sede"] for r in csv.DictReader(f) if r["ofrece_citas"] == "1"}
    with open(REALES / "sedes_metrosalud_georreferenciadas.csv", encoding="utf-8") as f:
        geo = {r["codigo_habilitacion_sede"] for r in csv.DictReader(f)}
    assert con_citas == geo
