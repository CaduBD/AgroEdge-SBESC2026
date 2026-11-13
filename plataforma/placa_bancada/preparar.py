"""Monta a pasta placa_bancada/para_a_placa/ com tudo o que vai para a BitDogLab.

- Gera config_bancada.py com o serial e a senha MQTT da placa padrão (do plataforma/.env, ou
  do .env da VPS com --vps). A senha não aparece na tela.
- Copia do firmware os módulos de cálculo (eto, culturas, classificador, histórico, lâmina,
  relógio e o config_local com o Wi-Fi) e o main.py do firmware com o nome estacao.py.
- Copia o programa de bancada (bancada.py e main.py).

Uso (a partir de plataforma/):
    python placa_bancada/preparar.py --host 192.168.0.10 --wifi "MinhaRede"   # pede a senha
    python placa_bancada/preparar.py --listar-ips      # mostra os IPs deste computador
    python placa_bancada/preparar.py --vps             # placa falando com a VPS (TLS)

--host é o IP do notebook NA MESMA REDE Wi-Fi que a placa vai usar.

--vps: broker mqtt.agroedge.tech:8883 com TLS. A senha da placa é a do .env da VPS (lida pela
chave SSH, sem aparecer na tela) e vai junto a raiz do certificado (isrg_root_x2.der). Sem
--wifi, reaproveita o Wi-Fi da última preparação.
Só biblioteca padrão.
"""

import argparse
import ast
import getpass
import shutil
import socket
import ssl
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLATAFORMA = AQUI.parent
FIRMWARE = PLATAFORMA.parent / "firmware" / "modelo"
SAIDA = AQUI / "para_a_placa"
HOST_VPS = "mqtt.agroedge.tech"
SSH_VPS = "agroedge-vps"  # alias do ~/.ssh/config (producao/README.md)
ENV_VPS = "/opt/agroedge/plataforma/.env"
CA_PEM = AQUI / "isrg_root_x2.pem"  # raiz do Let's Encrypt que assina o certificado do broker
CA_PLACA = "isrg_root_x2.der"

DO_FIRMWARE = [
    "config_local.py",
    "culturas.py",
    "eto.py",
    "classificador.py",
    "agroedge_pesos.py",
    "historico.py",
    "lamina.py",
    "relogio.py",
]


def ler_env() -> dict[str, str]:
    env: dict[str, str] = {}
    arquivo = PLATAFORMA / ".env"
    if not arquivo.exists():
        sys.exit("plataforma/.env não existe: rode antes  make up  (ou .\\tarefas.ps1 up)")
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def env_da_vps() -> dict[str, str]:
    """Serial e senha da placa padrão no .env da VPS. Ficam só na memória e no arquivo gerado."""
    r = subprocess.run(
        ["ssh", SSH_VPS, f"grep -E '^(DISPOSITIVO_SERIAL|DISPOSITIVO_SENHA)=' {ENV_VPS}"],
        capture_output=True,
        check=False,
    )
    if r.returncode != 0:
        sys.exit("não consegui ler o .env da VPS (a chave SSH agroedge-vps está no notebook?)")
    env = {}
    for linha in r.stdout.decode().splitlines():
        k, _, v = linha.strip().partition("=")
        env[k] = v
    return env


def wifi_anterior() -> tuple[str, str]:
    """Wi-Fi da última preparação (para_a_placa/config_bancada.py, fora do git)."""
    arquivo = SAIDA / "config_bancada.py"
    valores: dict[str, str] = {}
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            k, _, v = linha.partition("=")
            if k.strip() in ("WIFI_SSID", "WIFI_SENHA"):
                valores[k.strip()] = ast.literal_eval(v.strip())
    return valores.get("WIFI_SSID", ""), valores.get("WIFI_SENHA", "")


def ips_locais() -> list[str]:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--host", help="IP do notebook na rede Wi-Fi da placa")
    p.add_argument("--wifi", help="nome da rede Wi-Fi 2,4 GHz da placa (a senha é pedida)")
    p.add_argument("--listar-ips", action="store_true", help="mostra os IPs deste computador")
    p.add_argument("--vps", action="store_true", help=f"broker da VPS ({HOST_VPS}:8883, TLS)")
    p.add_argument("--telemetria-s", type=int, default=60)
    p.add_argument("--dias-acelerados", type=int, default=7)
    p.add_argument("--dia-minutos", type=int, default=10)
    args = p.parse_args()

    if args.vps:
        args.host = HOST_VPS
    if args.listar_ips or not args.host:
        print("IPs deste computador:", ", ".join(ips_locais()) or "nenhum encontrado")
        if not args.host:
            print("\nUse um deles com --host (o da rede Wi-Fi em que a placa vai entrar).")
        return

    if not (FIRMWARE / "main.py").exists():
        sys.exit(f"firmware não encontrado em {FIRMWARE}")
    env = env_da_vps() if args.vps else ler_env()
    serial, senha = env.get("DISPOSITIVO_SERIAL"), env.get("DISPOSITIVO_SENHA")
    if not serial or not senha:
        origem = "no .env da VPS" if args.vps else "no plataforma/.env"
        sys.exit(f"faltam DISPOSITIVO_SERIAL / DISPOSITIVO_SENHA {origem}")
    porta, tls = (8883, True) if args.vps else (1883, False)

    if args.wifi:
        wifi_ssid = args.wifi
        wifi_senha = getpass.getpass(f"Senha do Wi-Fi '{wifi_ssid}' (não aparece na tela): ")
    else:
        wifi_ssid, wifi_senha = wifi_anterior()

    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir()
    for nome in DO_FIRMWARE:
        shutil.copy2(FIRMWARE / nome, SAIDA / nome)
    shutil.copy2(FIRMWARE / "main.py", SAIDA / "estacao.py")  # sem rodar sozinho ao ligar
    shutil.copy2(AQUI / "bancada.py", SAIDA / "bancada.py")
    shutil.copy2(AQUI / "main.py", SAIDA / "main.py")
    if tls:
        pem = CA_PEM.read_text(encoding="utf-8")
        (SAIDA / CA_PLACA).write_bytes(ssl.PEM_cert_to_DER_cert(pem[pem.index("-----BEGIN") :]))
    (SAIDA / "config_bancada.py").write_text(
        "# Gerado por preparar.py. Não vai para o git (tem a senha MQTT da placa).\n"
        f'MQTT_HOST = "{args.host}"\n'
        f"MQTT_PORTA = {porta}\n"
        f"MQTT_TLS = {tls}\n"
        + (f'MQTT_CA = "{CA_PLACA}"\n' if tls else "")
        + f'MQTT_USUARIO = "{serial}"\n'
        f'MQTT_SENHA = "{senha}"\n'
        f"TELEMETRIA_S = {args.telemetria_s}\n"
        f"ACELERADO_DIAS = {args.dias_acelerados}\n"
        f"DIA_MINUTOS = {args.dia_minutos}\n"
        "PINO_RELE = 19\n"
        + (f"WIFI_SSID = {wifi_ssid!r}\nWIFI_SENHA = {wifi_senha!r}\n" if wifi_ssid else ""),
        encoding="utf-8",
    )
    print(f"Pronto: {SAIDA}")
    print(f"  placa {serial} -> broker {args.host}:{porta}" + (" (TLS)" if tls else ""))
    print(f"  Wi-Fi: {wifi_ssid or 'o do config_local.py do firmware'}")
    print(f"  {len(list(SAIDA.iterdir()))} arquivos. Grave todos na raiz da placa (README.md).")


if __name__ == "__main__":
    main()
