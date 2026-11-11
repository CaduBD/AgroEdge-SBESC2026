"""Cria plataforma/.env a partir do .env.example, trocando os segredos por valores aleatórios.

Só biblioteca padrão. Não sobrescreve um .env existente.

    python backend/scripts/gerar_env.py
"""

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


def main() -> None:
    destino = RAIZ / ".env"
    if destino.exists():
        print(".env já existe; nada a fazer")
        return
    linhas = []
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        chave = linha.split("=", 1)[0].strip()
        if chave in SEGREDOS and not linha.lstrip().startswith("#"):
            linha = f"{chave}={SEGREDOS[chave]()}"
        linhas.append(linha)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f".env criado em {destino}")
    print("A senha de login (ADMIN_SENHA) está no .env.")


if __name__ == "__main__":
    sys.exit(main())
