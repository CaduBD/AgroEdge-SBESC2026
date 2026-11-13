"""Configuração do cultivo enviada à placa (regra 9.4) e cálculos só de exibição (TAW, RAW)."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.catalogo import cultura as cultura_do_catalogo
from app.erros import ErroApp
from app.models import Cultivo, Dispositivo, Instalacao, TexturaSolo
from app.mqtt.publicador import Publicador, SemBroker

log = logging.getLogger("configuracao")

# Apêndice B: água disponível (m³/m³) por textura. Avançado = digitado.
PRESETS_SOLO: dict[TexturaSolo, float] = {
    TexturaSolo.arenoso: 0.08,
    TexturaSolo.franco_arenoso: 0.11,
    TexturaSolo.argiloso: 0.16,
}
TAW_TREINO_MM = (25.0, 140.0)  # faixa de treino do classificador


def montar_config(
    cultivo: Cultivo, instalacao: Instalacao, dispositivo: Dispositivo
) -> dict[str, Any]:
    """Payload `config` (seção 7.3)."""
    return {
        "cfg_v": instalacao.cfg_v,
        "instalacao_id": instalacao.id,
        "cultura": cultivo.cultura,
        "data_referencia": cultivo.data_referencia.isoformat(),
        "agua_disp": cultivo.agua_disp,
        "raiz_m": cultivo.raiz_m,
        "eficiencia": cultivo.eficiencia,
        "area_m2": cultivo.area_m2,
        "vazao_l_h": cultivo.vazao_l_h,
        "n_plantas": cultivo.n_plantas,
        "fonte_irrigacao": str(cultivo.fonte_irrigacao),
        "inicio_uso": str(cultivo.inicio_uso),
        "irrigacao_automatica": cultivo.irrigacao_automatica,
        "hora_irrigacao": cultivo.hora_irrigacao.strftime("%H:%M"),
        "intervalo_telemetria_min": dispositivo.intervalo_telemetria_min,
    }


# ---------------------------------------------------------------- solo


def raiz_efetiva(cultivo: Cultivo) -> float:
    if cultivo.raiz_m is not None:
        return cultivo.raiz_m
    dados = cultura_do_catalogo(cultivo.cultura)
    return float(dados["raiz_m"]) if dados else 0.6


def taw_raw(cultivo: Cultivo) -> tuple[float, float]:
    """TAW = 1000 × agua_disp × raiz; RAW = p × TAW (p da cultura). Só para exibir."""
    taw = 1000 * cultivo.agua_disp * raiz_efetiva(cultivo)
    dados = cultura_do_catalogo(cultivo.cultura)
    p = float(dados["p"]) if dados else 0.5
    return round(taw, 1), round(p * taw, 1)


def avisos_cultivo(cultivo: Cultivo) -> list[str]:
    """Avisos que não bloqueiam o salvamento."""
    taw, _ = taw_raw(cultivo)
    minimo, maximo = TAW_TREINO_MM
    if not minimo <= taw <= maximo:
        return [
            f"TAW de {taw:.0f} mm fora da faixa de treino do classificador "
            f"({minimo:.0f} a {maximo:.0f} mm): a classe pode ser pouco confiável."
        ]
    return []


def normalizar_solo(cultivo: Cultivo) -> None:
    """Nas texturas pré-definidas, a água disponível vem do preset e a raiz é a da cultura."""
    if cultivo.textura_solo != TexturaSolo.avancado:
        cultivo.agua_disp = PRESETS_SOLO[cultivo.textura_solo]
        cultivo.raiz_m = None


def validar_cultivo(cultivo: Cultivo) -> None:
    """Faixas da regra 9.4 (o schema da API já confere; aqui vale para qualquer origem)."""
    if cultura_do_catalogo(cultivo.cultura) is None:
        raise ErroApp(400, "cultura_desconhecida", f"Cultura desconhecida: {cultivo.cultura}")
    regras = [
        (0.06 <= cultivo.agua_disp <= 0.18, "Água disponível deve ficar entre 0,06 e 0,18 m³/m³."),
        (
            cultivo.raiz_m is None or 0.4 <= cultivo.raiz_m <= 0.8,
            "Raiz deve ficar entre 0,4 e 0,8 m.",
        ),
        (0.5 <= cultivo.eficiencia <= 0.95, "Eficiência deve ficar entre 0,5 e 0,95."),
        (cultivo.area_m2 > 0, "A área por planta deve ser maior que zero."),
        (cultivo.vazao_l_h > 0, "A vazão por planta deve ser maior que zero."),
        (cultivo.n_plantas is None or cultivo.n_plantas > 0, "O nº de plantas deve ser positivo."),
    ]
    for ok, mensagem in regras:
        if not ok:
            raise ErroApp(400, "valor_fora_da_faixa", mensagem)


# ---------------------------------------------------------------- publicação


async def instalacao_ativa_do_cultivo(sessao: AsyncSession, cultivo_id: int) -> Instalacao | None:
    return (
        await sessao.execute(
            select(Instalacao).where(
                col(Instalacao.cultivo_id) == cultivo_id, col(Instalacao.fim).is_(None)
            )
        )
    ).scalar_one_or_none()


async def publicar_instalacao(
    sessao: AsyncSession, publicador: Publicador, instalacao: Instalacao, cultivo: Cultivo
) -> bool:
    """Grava `config_publicada` e publica (retida). Devolve False se o broker estava fora.

    Sem broker, a config fica guardada e o ingestor republica ao reconectar.
    """
    dispositivo = await sessao.get(Dispositivo, instalacao.dispositivo_id)
    assert dispositivo is not None
    config = montar_config(cultivo, instalacao, dispositivo)
    instalacao.config_publicada = config
    sessao.add(instalacao)
    try:
        await publicador.config(dispositivo.serial, config)
    except SemBroker:
        log.warning("config guardada sem publicar (broker fora) serial=%s", dispositivo.serial)
        return False
    return True


async def reconfigurar_dispositivo(
    sessao: AsyncSession, publicador: Publicador, dispositivo: Dispositivo
) -> Instalacao | None:
    """Mudou algo da placa que vai na config (o intervalo): nova versão para a instalação ativa."""
    instalacao = (
        await sessao.execute(
            select(Instalacao).where(
                col(Instalacao.dispositivo_id) == dispositivo.id, col(Instalacao.fim).is_(None)
            )
        )
    ).scalar_one_or_none()
    if instalacao is None:
        return None
    cultivo = await sessao.get(Cultivo, instalacao.cultivo_id)
    assert cultivo is not None
    instalacao.cfg_v += 1
    await publicar_instalacao(sessao, publicador, instalacao, cultivo)
    return instalacao


async def reconfigurar(
    sessao: AsyncSession, publicador: Publicador, cultivo: Cultivo
) -> Instalacao | None:
    """Regra 9.4: com instalação ativa, nova versão de config e publicação. Sem ela, nada."""
    instalacao = await instalacao_ativa_do_cultivo(sessao, cultivo.id)  # type: ignore[arg-type]
    if instalacao is None:
        return None
    instalacao.cfg_v += 1
    await publicar_instalacao(sessao, publicador, instalacao, cultivo)
    return instalacao
