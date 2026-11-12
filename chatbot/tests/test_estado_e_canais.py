from agroedge_bot.canais.telegram import TECLADO_MENU, teclado
from agroedge_bot.config import Settings
from agroedge_bot.nucleo.estado import Estado
from agroedge_bot.nucleo.mensagens import Botao, Resposta


def test_estado_sobrevive_ao_reinicio(tmp_path) -> None:
    caminho = tmp_path / "estado.json"
    e = Estado.carregar(caminho)
    e.conversa("100").cultivo_id = 2
    e.conversa("100").alertas = False
    e.ultimo_diario["2"] = "2026-11-10"
    e.status_placa["agroedge-00001"] = "offline"
    e.salvar()
    de_novo = Estado.carregar(caminho)
    assert de_novo.conversa("100").cultivo_id == 2
    assert de_novo.conversa("100").alertas is False
    assert de_novo.ultimo_diario == {"2": "2026-11-10"}
    assert de_novo.status_placa == {"agroedge-00001": "offline"}


def test_estado_corrompido_recomeca(tmp_path) -> None:
    caminho = tmp_path / "estado.json"
    caminho.write_text("{isso não é json", encoding="utf-8")
    assert Estado.carregar(caminho).conversas == {}


def test_teclado_do_telegram() -> None:
    assert teclado(Resposta("x")) is None
    markup = teclado(Resposta("x", [[Botao("Sim", "ok:a:2:10:1"), Botao("Não", "no")]]))
    assert markup is not None
    assert [[b.callback_data for b in linha] for linha in markup.inline_keyboard] == [
        ["ok:a:2:10:1", "no"]
    ]
    assert TECLADO_MENU.keyboard[0][0].text == "Hoje"


def test_config_lista_separada_por_virgula(monkeypatch) -> None:
    monkeypatch.setenv("BOT_ALERTAS", "diario,status")
    monkeypatch.setenv("AGROEDGE_API_URL", "http://100.101.102.103:8000/")
    s = Settings(_env_file=None)
    assert s.bot_alertas == {"diario", "status"}
    assert s.agroedge_api_url == "http://100.101.102.103:8000"


def test_botao_com_dado_longo_demais() -> None:
    try:
        Botao("x", "a" * 65)
    except ValueError:
        return
    raise AssertionError("deveria recusar")
