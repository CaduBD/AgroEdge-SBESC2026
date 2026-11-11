"""Gera mosquitto/passwd com o usuário `plataforma` e a placa padrão, usando as senhas do .env.

Roda no notebook (só biblioteca padrão), com o Docker instalado. Usa o mosquitto_passwd
da própria imagem do Mosquitto, então não precisa instalar nada. Não sobrescreve um
passwd existente (use --forcar para recriar).

    python backend/scripts/gerar_passwd.py
"""

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from criar_dispositivo import _ler_env  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forcar", action="store_true", help="recria o passwd")
    args = parser.parse_args()

    passwd = RAIZ / "mosquitto" / "passwd"
    if passwd.is_dir():  # o Docker cria uma pasta se o arquivo não existia no primeiro "up"
        passwd.rmdir()
    if passwd.exists() and not args.forcar:
        print("mosquitto/passwd já existe; nada a fazer (use --forcar para recriar)")
        return
    passwd.unlink(missing_ok=True)  # o mosquitto_passwd -c não sobrescreve

    env = _ler_env()
    faltando = [
        c
        for c in ("MQTT_USUARIO", "MQTT_SENHA", "DISPOSITIVO_SERIAL", "DISPOSITIVO_SENHA")
        if not env.get(c)
    ]
    if faltando:
        sys.exit(
            f"faltam no .env: {', '.join(faltando)} "
            "(rode antes: python backend/scripts/gerar_env.py)"
        )

    comando = (
        'mosquitto_passwd -c -b /m/passwd "$1" "$2" && '
        'mosquitto_passwd -b /m/passwd "$3" "$4" && '
        # O broker roda como o usuário mosquitto (uid 1883) e exige o arquivo só para ele.
        "chown 1883:1883 /m/passwd && chmod 0700 /m/passwd"
    )
    resultado = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{RAIZ / 'mosquitto'}:/m",
            "eclipse-mosquitto:2",
            "sh",
            "-c",
            comando,
            "sh",
            env["MQTT_USUARIO"],
            env["MQTT_SENHA"],
            env["DISPOSITIVO_SERIAL"],
            env["DISPOSITIVO_SENHA"],
        ],
        check=False,  # sem traceback: ele mostraria as senhas no terminal
    )
    if resultado.returncode != 0:
        sys.exit("falha ao gerar o passwd: o Docker está rodando?")
    print(f"mosquitto/passwd criado com {env['MQTT_USUARIO']} e {env['DISPOSITIVO_SERIAL']}")


if __name__ == "__main__":
    main()
