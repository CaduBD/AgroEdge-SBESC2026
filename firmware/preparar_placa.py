"""Prepara e grava a estação AgroEdge (firmware definitivo) na BitDogLab.

Monta firmware/para_a_placa/ com o firmware, a raiz do certificado e o config_rede.py (Wi-Fi
e senha da placa; fora do git) e, com --gravar, copia tudo para a placa pela USB.

Uso, a partir da raiz do repositório (Python com o mpremote, ex.: o do backend da plataforma):
    python firmware/preparar_placa.py --wifi "MinhaRede" --gravar       # placa nova ou firmware novo
    python firmware/preparar_placa.py --wifi "OutraRede" --so-rede --gravar   # só trocar o Wi-Fi
    python firmware/preparar_placa.py --serial agroedge-00003 --cadastrar --wifi "Rede" --gravar

A senha do Wi-Fi é pedida sem aparecer na tela. Sem --wifi, reaproveita o da última preparação.
A senha MQTT da placa vem da VPS pela chave SSH (alias agroedge-vps), sem aparecer na tela:
  - placa padrão (DISPOSITIVO_SERIAL do .env da VPS): lida do .env;
  - outra placa: --cadastrar cria o serial e a senha na VPS (uma vez); a senha fica guardada
    em firmware/senhas_placas.env (fora do git) para as próximas preparações.
"""

import argparse
import ast
import getpass
import secrets
import shutil
import ssl
import subprocess
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIRMWARE = AQUI / "modelo"
SAIDA = AQUI / "para_a_placa"
SENHAS = AQUI / "senhas_placas.env"
SSH_VPS = "agroedge-vps"
PASTA_VPS = "/opt/agroedge/plataforma"
HOST_MQTT = "mqtt.agroedge.tech"
CA = "isrg_root_x2.der"

ARQUIVOS = [
    "main.py", "config_local.py", "culturas.py", "eto.py", "relogio.py", "lamina.py",
    "classificador.py", "historico_v3.py", "agroedge_pesos_v3_1.py", "historico.py",
    "agroedge_pesos.py", "termohigro.py", "anemometro.py", "pluviometro.py", "piranometro.py",
    "ssd1306.py", "conexao.py", "valvula.py",
]


def ssh(comando, entrada=None):
    r = subprocess.run(["ssh", SSH_VPS, comando], input=entrada, capture_output=True, check=False)
    if r.returncode != 0:
        sys.exit("falhou na VPS (a chave SSH agroedge-vps está neste computador?)")
    return r.stdout.decode()


def ler_env(texto):
    env = {}
    for linha in texto.splitlines():
        k, _, v = linha.strip().partition("=")
        if k and not k.startswith("#"):
            env[k] = v
    return env


def senha_da_placa(serial, cadastrar):
    """Senha MQTT do serial: do .env da VPS (placa padrão), do arquivo local ou cadastrando."""
    guardadas = ler_env(SENHAS.read_text(encoding="utf-8")) if SENHAS.exists() else {}
    if cadastrar:
        senha = secrets.token_urlsafe(18)
        # em bytes: em modo texto o Windows mandaria "\r\n" e o "\r" iria junto com a senha
        ssh(f'read -r S && cd {PASTA_VPS} && '
            f'python3 backend/scripts/criar_dispositivo.py {serial} --senha "$S" >/dev/null',
            (senha + "\n").encode())
        guardadas[serial] = senha
        SENHAS.write_text("# Senhas MQTT das placas (preparar_placa.py; fora do git)\n"
                          + "".join(f"{k}={v}\n" for k, v in guardadas.items()), encoding="utf-8")
        print(f"{serial} cadastrada na VPS. Instale a placa num cultivo pelo painel.")
        return senha
    if serial in guardadas:
        return guardadas[serial]
    env = ler_env(ssh(f"grep -E '^(DISPOSITIVO_SERIAL|DISPOSITIVO_SENHA)=' {PASTA_VPS}/.env"))
    if env.get("DISPOSITIVO_SERIAL") == serial:
        return env["DISPOSITIVO_SENHA"]
    sys.exit(f"não sei a senha de {serial}: use --cadastrar para criar na VPS")


def wifi_anterior():
    for arq in (SAIDA / "config_rede.py", FIRMWARE / "config_rede.py",
                AQUI.parent / "plataforma" / "placa_bancada" / "para_a_placa" / "config_bancada.py"):
        if arq.exists():
            v = {}
            for linha in arq.read_text(encoding="utf-8").splitlines():
                k, _, val = linha.partition("=")
                if k.strip() in ("WIFI_SSID", "WIFI_SENHA"):
                    v[k.strip()] = ast.literal_eval(val.split("#")[0].strip())
            if v.get("WIFI_SSID"):
                return v["WIFI_SSID"], v.get("WIFI_SENHA", "")
    return "", ""


def mpremote(*args):
    """mpremote com novas tentativas: com o programa rodando, a 1ª pode falhar (raw REPL)."""
    for _ in range(5):
        r = subprocess.run([sys.executable, "-m", "mpremote", *args], capture_output=True,
                           text=True, check=False)
        if r.returncode == 0:
            return r.stdout
        time.sleep(2)
    sys.exit(f"mpremote {' '.join(args)} falhou:\n{r.stderr[-500:]}")


def gravar(arquivos):
    print("gravando na placa (USB)...")
    tem_umqtt = "simple" in mpremote("exec", "import os\ntry: print(os.listdir('/lib/umqtt'))\n"
                                             "except OSError: print([])")
    if not tem_umqtt:
        print("  instalando umqtt.simple (mip, precisa de internet no computador)")
        mpremote("mip", "install", "umqtt.simple")
    for arq in arquivos:
        mpremote("cp", str(SAIDA / arq), ":" + arq)
        print("  ", arq)
    mpremote("reset")
    print("placa reiniciada: a estação já está rodando.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wifi", help="nome da rede Wi-Fi 2,4 GHz (a senha é pedida)")
    p.add_argument("--serial", help="serial da placa (padrão: o da placa padrão na VPS)")
    p.add_argument("--cadastrar", action="store_true", help="cria o serial e a senha na VPS")
    p.add_argument("--so-rede", action="store_true", help="só o config_rede.py (trocar Wi-Fi)")
    p.add_argument("--gravar", action="store_true", help="copia para a placa pela USB")
    a = p.parse_args()

    serial = a.serial
    if not serial:
        serial = ler_env(ssh(f"grep '^DISPOSITIVO_SERIAL=' {PASTA_VPS}/.env")).get(
            "DISPOSITIVO_SERIAL")
    if a.cadastrar and not a.serial:
        sys.exit("--cadastrar precisa de --serial (ex.: agroedge-00003)")
    senha = senha_da_placa(serial, a.cadastrar)
    if a.wifi:
        ssid = a.wifi
        senha_wifi = getpass.getpass(f"Senha do Wi-Fi '{ssid}' (não aparece na tela): ")
    else:
        ssid, senha_wifi = wifi_anterior()
        if not ssid:
            sys.exit("informe o Wi-Fi com --wifi \"NomeDaRede\"")

    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir()
    (SAIDA / "config_rede.py").write_text(
        "# Gerado por firmware/preparar_placa.py. FORA DO GIT: tem as senhas.\n"
        f"WIFI_SSID = {ssid!r}\nWIFI_SENHA = {senha_wifi!r}\n"
        f'MQTT_HOST = "{HOST_MQTT}"\nMQTT_PORTA = 8883\nMQTT_TLS = True\nMQTT_CA = "{CA}"\n'
        f'MQTT_USUARIO = "{serial}"\nMQTT_SENHA = "{senha}"\n', encoding="utf-8")
    arquivos = ["config_rede.py"]
    if not a.so_rede:
        for nome in ARQUIVOS:
            shutil.copy2(FIRMWARE / nome, SAIDA / nome)
        pem = (FIRMWARE / "isrg_root_x2.pem").read_text(encoding="utf-8")
        (SAIDA / CA).write_bytes(ssl.PEM_cert_to_DER_cert(pem[pem.index("-----BEGIN"):]))
        arquivos += ARQUIVOS + [CA]
    print(f"pronto em {SAIDA}: placa {serial}, Wi-Fi '{ssid}', {len(arquivos)} arquivos")
    if a.gravar:
        gravar(arquivos)
    else:
        print("para gravar: rode de novo com --gravar (placa na USB)")


if __name__ == "__main__":
    main()
