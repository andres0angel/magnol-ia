import pytest

from magnolia.nlu.normalizar import normalizar


@pytest.mark.parametrize("entrada,esperado", [
    ("cuarenta y tres millones quinientos veintisiete mil ochocientos noventa y uno", "43527891"),
    ("ocho millones trescientos cuarenta y cinco mil seiscientos setenta y ocho", "8345678"),
    ("setenta y un millones doscientos mil cuatrocientos", "71200400"),
    ("tres dos cuatro cinco seis siete ocho nueve", "32456789"),
    ("8.345.678", "8345678"),
    ("32 456 789", "32456789"),
    ("mil novecientos cincuenta y dos", "1952"),
])
def test_numeros(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_una_cita_no_es_un_numero():
    assert normalizar("quiero una cita") == "quiero una cita"
    assert normalizar("a la una de la tarde") == "a la una de la tarde"


def test_correcciones_y_tildes():
    assert normalizar("Kiero una SITA con el médico jeneral pa mañana") == "quiero una cita con el medico general para manana"
    assert normalizar("nooo") == "no"
    assert normalizar("el veinticinco") == "el 25"
