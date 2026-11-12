from datetime import datetime
from zoneinfo import ZoneInfo

from agroedge_bot.nucleo import textos
from agroedge_bot.nucleo.mensagens import para_texto_simples
from tests.conftest import resumo_exemplo

FUSO = ZoneInfo("America/Bahia")
AGORA = datetime(2026, 11, 11, 20, 30, tzinfo=FUSO)


def test_numeros_com_virgula() -> None:
    assert textos.br(11.94) == "11,9"
    assert textos.br(0.68, 2) == "0,68"
    assert textos.br(None) == "—"


def test_hora_converte_utc_para_local() -> None:
    # 23:00 UTC = 20:00 em Petrolina (UTC−3); mesmo dia: só a hora
    assert textos.hora("2026-11-11T23:00:00Z", FUSO, AGORA) == "20:00"
    # outro dia: com a data
    assert textos.hora("2026-11-12T08:00:00Z", FUSO, AGORA) == "12/11 05:00"
    assert textos.hora(1794438000, FUSO, AGORA) == "20:00"  # ts Unix
    assert textos.hora(None, FUSO, AGORA) == "—"


def test_dia_local_sem_conversao() -> None:
    assert textos.dia("2026-11-10") == "10/11"


def test_resumo_completo() -> None:
    texto = textos.resumo(resumo_exemplo(), FUSO, AGORA)
    assert "<b>Bancada uva</b> · Fazenda Exemplo" in texto
    assert "dia 22 de 109" in texto
    assert "🟢 Estado hídrico: <b>Adequado</b> (fechamento de 10/11)" in texto
    assert "<b>11,9 mm</b> · 47,6 L/planta · 5 h 57 min de válvula" in texto
    assert "31,6 °C" in texto and "(20:00)" in texto
    assert "próxima prevista 12/11 05:00" in texto
    assert "Placa agroedge-00001: ao vivo · 20:00" in texto


def test_lamina_zero() -> None:
    d = resumo_exemplo()["ultimo_diario"] | {"lamina_bruta": 0.0, "minutos": 0.0}
    assert "Não precisa irrigar" in textos.alerta_diario("B", d)


def test_resumo_sem_fechamento_e_sem_placa() -> None:
    r = resumo_exemplo(com_placa=False)
    r["ultimo_diario"] = None
    r["ultima_leitura"] = None
    texto = textos.resumo(r, FUSO, AGORA)
    assert "Ainda não há fechamento diário" in texto
    assert "Nenhuma placa instalada" in texto
    assert "Sem leituras" in texto


def test_sem_classe_mostra_avisos() -> None:
    r = resumo_exemplo()
    r["ultimo_diario"] |= {"classe": None, "avisos": ["dia incompleto (40% com leituras)"]}
    texto = textos.resumo(r, FUSO, AGORA)
    assert "⚪ Estado hídrico: <b>Sem classe</b>" in texto
    assert "⚠️ <i>dia incompleto (40% com leituras)</i>" in texto


def test_placa_sem_contato_e_valvula_aberta() -> None:
    r = resumo_exemplo()
    r["dispositivo"]["status"] = "sem_contato"
    r["valvula"] = {
        "aberta": True,
        "em_andamento": {"ts_inicio": 1794436200, "minutos": 10.0, "origem": "manual"},
        "ultima": None,
        "proxima_prevista": None,
    }
    texto = textos.resumo(r, FUSO, AGORA)
    assert "sem contato desde 20:00 ⚠️" in texto
    assert "Válvula <b>aberta</b> desde 19:30 (manual, 10 min)" in texto


def test_nomes_sao_escapados() -> None:
    r = resumo_exemplo(nome="Lote <A> & B")
    assert "<b>Lote &lt;A&gt; &amp; B</b>" in textos.resumo(r, FUSO, AGORA)


def test_historico_mais_recente_primeiro() -> None:
    texto = textos.historico(
        "Bancada",
        [
            {
                "data": "2026-11-09",
                "classe": 1,
                "etc": 4.0,
                "chuva": 0,
                "irrigacao": 0,
                "lamina_bruta": 9.0,
            },
            {
                "data": "2026-11-10",
                "classe": 2,
                "etc": 5.0,
                "chuva": 0,
                "irrigacao": 0,
                "lamina_bruta": 12.0,
            },
        ],
    )
    assert texto.index("10/11") < texto.index("09/11")
    assert "🔴 Déficit crítico" in texto and "🟡 Déficit moderado" in texto


def test_resposta_de_comando() -> None:
    assert "aberta por 10 min" in textos.comando_respondido(
        "B", "abrir", 10, "executado", "executado"
    )
    assert "fechada" in textos.comando_respondido("B", "cancelar", None, "executado", "executado")
    assert "já havia uma irrigação" in textos.comando_respondido(
        "B", "abrir", 10, "recusado", "recusado_em_andamento"
    )
    assert "não respondeu em 10 minutos" in textos.comando_respondido(
        "B", "abrir", 10, "expirado", None
    )


def test_alertas() -> None:
    d = resumo_exemplo()["ultimo_diario"] | {"classe": 2}
    texto = textos.alerta_diario("Bancada", d)
    assert "Fechamento de 10/11" in texto and "déficit crítico" in texto
    assert "sem contato" in textos.alerta_status("Bancada", "agroedge-00001", "offline")
    assert "voltou" in textos.alerta_status("Bancada", "agroedge-00001", "online")
    assert "começou" in textos.alerta_irrigacao(
        "B", {"estado": "iniciada", "origem": "automatica", "minutos": 30}
    )
    assert textos.alerta_irrigacao("B", {"estado": "desconhecido"}) is None


def test_texto_simples_para_whatsapp() -> None:
    assert para_texto_simples("<b>Lote &amp; B</b> <i>ok</i>") == "*Lote & B* _ok_"
