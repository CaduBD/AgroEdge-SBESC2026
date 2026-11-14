"""O catálogo da plataforma (app/catalogo/culturas.json) é um espelho do firmware/modelo/culturas.py.

Se alguém acrescentar ou mudar uma cultura num lugar e esquecer o outro, a placa e o painel passam a
discordar (Kc, fases, duração do ciclo). Este teste compara os dois. Se a pasta do firmware não
estiver disponível (ex.: só o backend dentro do container), o teste é pulado.
"""

import importlib.util
from pathlib import Path

import pytest

from app.catalogo import culturas

FIRMWARE = Path(__file__).resolve().parents[3] / "firmware" / "modelo" / "culturas.py"


def _culturas_do_firmware():
    if not FIRMWARE.exists():
        pytest.skip(f"firmware não encontrado em {FIRMWARE}")
    spec = importlib.util.spec_from_file_location("firmware_culturas", FIRMWARE)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.CULTURAS


def test_catalogo_igual_ao_firmware() -> None:
    fw = _culturas_do_firmware()
    catalogo = {c["chave"]: c for c in culturas()}
    assert set(catalogo) == set(fw), "culturas diferentes entre o catálogo e o firmware"
    for chave, c in fw.items():
        cat = catalogo[chave]
        assert cat["referencia"] == c["referencia"], chave
        assert cat["ciclo_dias"] == c["ciclo_dias"], chave
        assert cat["p"] == pytest.approx(c["p"]), chave
        assert cat["raiz_m"] == pytest.approx(c["raiz_m"]), chave
        tipo, dados = c["kc"]
        if tipo == "fases":
            assert cat["fases"] is not None, chave
            assert [(f["chave"], f["dias"]) for f in cat["fases"]] == [(n, d) for n, d, _ in dados], chave
            assert [f["kc"] for f in cat["fases"]] == pytest.approx([k for _, _, k in dados]), chave
            assert sum(f["dias"] for f in cat["fases"]) == c["ciclo_dias"], chave
        else:
            assert cat["fases"] is None, chave   # Kc por equação (uva): o painel não mostra fases
