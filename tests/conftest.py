import argparse
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from magnolia.config import config  # noqa: E402

FECHA = "2026-11-12T09:00"  # jueves; el lunes 16 es festivo


@pytest.fixture(scope="session")
def db_base(tmp_path_factory):
    import generar_datos

    ruta = tmp_path_factory.mktemp("db") / "base.db"
    generar_datos.generar(argparse.Namespace(desde="2026-11-12", dias_habiles=40, pacientes=200, semilla=13,
                                             db=str(ruta), exportar=False, silencioso=True))
    return ruta


@pytest.fixture
def gestor(db_base, tmp_path, monkeypatch):
    """Gestor de diálogo sobre una copia limpia de la base, sin LLM y con fecha fija."""
    import shutil

    from magnolia.db import conectar
    from magnolia.dialogo import GestorDialogo
    from magnolia.nlu import reglas

    copia = tmp_path / "magnolia.db"
    shutil.copy(db_base, copia)
    monkeypatch.setattr(config, "fecha_simulada", FECHA)
    monkeypatch.setattr(config, "llm_api_key", "")
    monkeypatch.setattr(config, "modo_demo", True)
    return GestorDialogo(con=conectar(copia), interpretar=reglas.interpretar)


class Conversacion:
    def __init__(self, gestor, usuario="u1", canal="prueba"):
        self.g, self.u, self.c = gestor, usuario, canal
        self.ultima = None

    def __call__(self, texto):
        self.ultima = self.g.procesar(self.c, self.u, texto)
        return self.ultima.texto


@pytest.fixture
def charla(gestor):
    return Conversacion(gestor)
