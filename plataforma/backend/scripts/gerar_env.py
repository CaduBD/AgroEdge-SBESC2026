"""Cria plataforma/.env a partir do .env.example, trocando os segredos por valores aleatórios.

Só biblioteca padrão. Não sobrescreve um .env existente.

    python backend/scripts/gerar_env.py                          # notebook
    python3 backend/scripts/gerar_env.py --producao agroedge.tech  # VPS (producao/README.md)
"""

import argparse
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SEGREDOS = {
    "ADMIN_SENHA": lambda: secrets.token_urlsafe(12),
    "SESSION_SECRET": lambda: secrets.token_urlsafe(48),
    "CHATBOT_TOKEN": lambda: secrets.token_urlsafe(32),
    "MQTT_SENHA": lambda: secrets.token_urlsafe(18),
    "DISPOSITIVO_SENHA": lambda: secrets.token_urlsafe(18),
}


def valores_de_producao(dominio: str) -> dict[str, str]:
    """O que muda na VPS. Com COMPOSE_FILE no .env, todo "docker compose" da pasta já usa o
    arquivo de produção (inclusive o criar_dispositivo.py e o gerar_passwd.py)."""
    return {
        "COMPOSE_FILE": "docker-compose.prod.yml",
        "AMBIENTE": "producao",
        "DOMINIO": dominio,
        "MQTT_DOMINIO": f"mqtt.{dominio}",
        "BROKER_HOST_PUBLICO": f"mqtt.{dominio}",
        "BROKER_PORTA_PUBLICA": "8883",
        "BROKER_TLS_PUBLICO": "true",
        "FORWARDED_ALLOW_IPS": "*",
        "DATABASE_URL": "sqlite+aiosqlite:////data/agroedge.db",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--producao", metavar="DOMINIO", help="gera o .env da VPS")
    args = parser.parse_args()

    destino = RAIZ / ".env"
    if destino.exists():
        print(".env já existe; nada a fazer")
        return
    fixos = valores_de_producao(args.producao.strip().lower()) if args.producao else {}
    linhas = []
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        chave = linha.split("=", 1)[0].strip()
        if not linha.lstrip().startswith("#"):
            if chave in SEGREDOS:
                linha = f"{chave}={SEGREDOS[chave]()}"
            elif chave in fixos:
                linha = f"{chave}={fixos.pop(chave)}"
        linhas.append(linha)
    if fixos:
        linhas += ["", "# Produção (gerar_env.py --producao)"]
        linhas += [f"{chave}={valor}" for chave, valor in fixos.items()]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    destino.chmod(0o600)  # só o dono lê os segredos (no Windows não tem efeito)
    print(f".env criado em {destino}")
    print("A senha de login (ADMIN_SENHA) está no .env.")


if __name__ == "__main__":
    sys.exit(main())
