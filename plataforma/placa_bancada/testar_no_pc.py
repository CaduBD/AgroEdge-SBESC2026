"""Roda o bancada.py no PC, contra o broker de verdade, antes de gravar na placa.

Substitui o que só existe no MicroPython (machine, network, umqtt.simple, time.ticks_*) e usa
os módulos de cálculo do firmware como estão. Simula uma queda de rede para testar o buffer.

Uso (a partir de plataforma/, com o compose no ar e o venv do backend):
    backend/.venv/Scripts/python placa_bancada/testar_no_pc.py --segundos 180 --queda 40-75

Os arquivos de estado (historico.json etc.) vão para uma pasta temporária.
"""

import argparse
import os
import queue
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import paho.mqtt.client as mqtt

AQUI = Path(__file__).resolve().parent
FIRMWARE = AQUI.parent.parent / "firmware" / "modelo"
INICIO = time.time()
QUEDA: tuple[float, float] | None = None


def em_queda() -> bool:
    return QUEDA is not None and QUEDA[0] <= time.time() - INICIO < QUEDA[1]


# ---------------------------------------------------------------- substitutos do MicroPython


def instalar_substitutos() -> None:
    # time.ticks_* e sleep_ms
    time.ticks_ms = lambda: int(time.time() * 1000)  # type: ignore[attr-defined]
    time.ticks_add = lambda a, b: a + b  # type: ignore[attr-defined]
    time.ticks_diff = lambda a, b: a - b  # type: ignore[attr-defined]
    time.sleep_ms = lambda ms: time.sleep(ms / 1000)  # type: ignore[attr-defined]

    machine = types.ModuleType("machine")

    class Pin:
        OUT = 1

        def __init__(self, numero, modo=None, value=0):
            self.numero, self._v = numero, value

        def value(self, v=None):
            if v is None:
                return self._v
            if v != self._v:
                print(f"    [relé GPIO{self.numero}] {'LIGADO' if v else 'desligado'}")
            self._v = v

    class I2C:  # o relogio.py procura o DS3231; no PC não há
        def __init__(self, *a, **k):
            raise OSError("sem I2C no PC")

    machine.Pin, machine.I2C = Pin, I2C  # type: ignore[attr-defined]
    sys.modules["machine"] = machine

    network = types.ModuleType("network")

    class WLAN:
        def __init__(self, _modo):
            pass

        def isconnected(self):
            return not em_queda()

        def active(self, *_):
            return True

        def connect(self, *_):
            pass

        def ifconfig(self):
            return ("127.0.0.1",)

        def status(self, _=None):
            return -55

    network.WLAN, network.STA_IF = WLAN, 0  # type: ignore[attr-defined]
    sys.modules["network"] = network

    umqtt = types.ModuleType("umqtt")
    simples = types.ModuleType("umqtt.simple")

    class MQTTClient:
        """API do umqtt.simple sobre o paho-mqtt."""

        def __init__(self, client_id, server, port=1883, user=None, password=None, keepalive=60):
            self.args = (client_id, server, port, user, password, keepalive)
            self.fila: queue.Queue = queue.Queue()
            self.cb = None
            self.lwt = None
            self.sock = types.SimpleNamespace(close=self._fechar)
            self.c = None

        def set_last_will(self, topic, msg, retain=False, qos=0):
            self.lwt = (topic, msg, retain, qos)

        def set_callback(self, cb):
            self.cb = cb

        def connect(self, clean_session=True):
            if em_queda():
                raise OSError("rede fora (simulada)")
            cid, server, port, user, password, keepalive = self.args
            c = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=cid,
                clean_session=clean_session,
                protocol=mqtt.MQTTv311,
            )
            c.username_pw_set(user, password)
            if self.lwt:
                t, m, r, q = self.lwt
                c.will_set(t, m, qos=q, retain=r)
            pronto = threading.Event()
            c.on_connect = lambda *a: pronto.set()
            c.on_message = lambda _c, _u, msg: self.fila.put((msg.topic.encode(), msg.payload))
            c.connect(server, port, keepalive)
            c.loop_start()
            if not pronto.wait(5):
                raise OSError("sem resposta do broker")
            self.c = c

        def _fechar(self):
            if self.c:
                self.c.loop_stop()
                self.c._sock_close()  # queda abrupta: o broker publica o LWT
                self.c = None

        def subscribe(self, topic, qos=0):
            self.c.subscribe(topic, qos)
            time.sleep(0.3)  # deixa a config retida chegar
            self.check_msg()

        def publish(self, topic, msg, retain=False, qos=0):
            if em_queda() or self.c is None:
                raise OSError("rede fora (simulada)")
            self.c.publish(topic, msg, qos=qos, retain=retain).wait_for_publish(5)

        def check_msg(self):
            if em_queda():
                raise OSError("rede fora (simulada)")
            while not self.fila.empty():
                self.cb(*self.fila.get())

        def ping(self):
            pass

        def disconnect(self):
            if self.c:
                self.c.disconnect()
                self.c.loop_stop()

    simples.MQTTClient = MQTTClient  # type: ignore[attr-defined]
    umqtt.simple = simples  # type: ignore[attr-defined]
    sys.modules["umqtt"], sys.modules["umqtt.simple"] = umqtt, simples


def config_de_teste(segundos_telemetria: int, dias: int, dia_minutos: float) -> None:
    env = {}
    for linha in (AQUI.parent / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    cb = types.ModuleType("config_bancada")
    cb.MQTT_HOST, cb.MQTT_PORTA = "localhost", 1883  # type: ignore[attr-defined]
    cb.MQTT_USUARIO = env["DISPOSITIVO_SERIAL"]  # type: ignore[attr-defined]
    cb.MQTT_SENHA = env["DISPOSITIVO_SENHA"]  # type: ignore[attr-defined]
    cb.TELEMETRIA_S = segundos_telemetria  # type: ignore[attr-defined]
    cb.ACELERADO_DIAS, cb.DIA_MINUTOS = dias, dia_minutos  # type: ignore[attr-defined]
    cb.PINO_RELE = 19  # type: ignore[attr-defined]
    sys.modules["config_bancada"] = cb


def main() -> None:
    global QUEDA
    p = argparse.ArgumentParser()
    p.add_argument("--segundos", type=float, default=180)
    p.add_argument("--queda", help="janela sem rede, em segundos desde o início: 40-75")
    p.add_argument("--telemetria-s", type=int, default=5)
    p.add_argument("--dias", type=int, default=3)
    p.add_argument("--dia-minutos", type=float, default=1)
    args = p.parse_args()
    if args.queda:
        a, b = (float(x) for x in args.queda.split("-"))
        QUEDA = (a, b)

    instalar_substitutos()
    config_de_teste(args.telemetria_s, args.dias, args.dia_minutos)
    pasta = tempfile.mkdtemp(prefix="bancada_")  # estado da "placa" fora do repositório
    # Na placa, o main.py do firmware vai com o nome estacao.py (o main.py é o da bancada).
    (Path(pasta) / "estacao.py").write_bytes((FIRMWARE / "main.py").read_bytes())
    sys.path[:0] = [pasta, str(AQUI), str(FIRMWARE)]
    os.chdir(pasta)

    import bancada

    bancada.RTC_LOCAL = False  # no PC o relógio já está em UTC
    placa = bancada.Bancada()

    def parar():
        time.sleep(args.segundos)
        import _thread

        _thread.interrupt_main()

    threading.Thread(target=parar, daemon=True).start()
    placa.rodar()


if __name__ == "__main__":
    main()
