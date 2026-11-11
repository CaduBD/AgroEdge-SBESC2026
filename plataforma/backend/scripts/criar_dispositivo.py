"""Cadastra uma placa nova: senha MQTT no passwd do Mosquitto, registro no banco e
recarga do broker. Imprime os valores para o config_local.py da placa.

Roda no notebook (só biblioteca padrão), a partir de plataforma/, com o compose no ar:

    python backend/scripts/criar_dispositivo.py agroedge-00002

Internamente chama a si mesmo dentro do container `app` com --somente-banco.
"""

import argparse
import asyncio
import re
import secrets
import subprocess
import sys
from pathlib import Path

PADRAO_SERIAL = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
RAIZ = Path(__file__).resolve().parents[2]  # plataforma/


def _ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    arquivo = RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                env[chave.strip()] = valor.strip()
    return env


def _compose(*args: str, entrada: str | None = None) -> None:
    subprocess.run(["docker", "compose", *args], cwd=RAIZ, check=True, input=entrada, text=True)


def no_notebook(serial: str, senha: str | None) -> None:
    senha = senha or secrets.token_urlsafe(18)
    print(f"→ senha MQTT de {serial} no passwd do Mosquitto")
    # O mosquitto_passwd recria o arquivo como root; devolve ao usuário mosquitto.
    _compose(
        "exec",
        "-T",
        "mosquitto",
        "sh",
        "-c",
        'mosquitto_passwd -b /mosquitto/config/passwd "$1" "$2" && '
        "chown mosquitto:mosquitto /mosquitto/config/passwd && "
        "chmod 0700 /mosquitto/config/passwd",
        "sh",
        serial,
        senha,
    )
    print("→ registro no banco")
    _compose(
        "exec", "-T", "app", "python", "-m", "scripts.criar_dispositivo", "--somente-banco", serial
    )
    print("→ recarregando o Mosquitto")
    _compose("kill", "-s", "SIGHUP", "mosquitto")

    env = _ler_env()
    print("\nCopie para o config_local.py da placa:\n")
    print(f'MQTT_HOST = "{env.get("BROKER_HOST_PUBLICO", "172.20.10.10")}"')
    print("MQTT_PORTA = 1883")
    print(f'MQTT_USUARIO = "{serial}"')
    print(f'MQTT_SENHA = "{senha}"')


async def no_banco(serial: str) -> None:
    from sqlalchemy import select

    from app.config import obter_settings
    from app.db import fabrica_sessao
    from app.models import Dispositivo, Usuario

    async with fabrica_sessao() as sessao:
        # Hoje há um usuário só (o do .env): a placa nova é dele.
        email = obter_settings().admin_email.strip().lower()
        dono = (
            await sessao.execute(select(Usuario).where(Usuario.email == email))
        ).scalar_one_or_none()
        if dono is None:
            sys.exit("usuário do .env não existe no banco: rode o seed antes")
        existe = (
            await sessao.execute(select(Dispositivo).where(Dispositivo.serial == serial))
        ).scalar_one_or_none()
        if existe:
            if existe.usuario_id is None:
                existe.usuario_id = dono.id
                await sessao.commit()
            print(f"  {serial} já estava no banco (id={existe.id})")
            return
        sessao.add(Dispositivo(serial=serial, usuario_id=dono.id))
        await sessao.commit()
        print(f"  {serial} criado no banco")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("serial", help="ex.: agroedge-00002")
    parser.add_argument("--senha", help="senha MQTT (padrão: gerada aleatoriamente)")
    parser.add_argument("--somente-banco", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not PADRAO_SERIAL.match(args.serial):
        sys.exit("serial inválido: use letras minúsculas, números e hífen (ex.: agroedge-00002)")
    if args.somente_banco:
        asyncio.run(no_banco(args.serial))
    else:
        no_notebook(args.serial, args.senha)


if __name__ == "__main__":
    main()
