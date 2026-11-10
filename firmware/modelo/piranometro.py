# AgroEdge - driver do piranômetro SN-300AL-RA-N01 (RS-485 / Modbus-RTU).
# MicroPython (BitDogLab / RP2040). Mesma lógica do teste de bancada que já funcionou na
# placa (bancada/teste_piranometro_rs485.py, vindo de thallesinacio/AgroEdge-Testes),
# reorganizada em módulo: não roda nada ao ser importado.
#
# Ligação (pinos no config_local.py):
#   GPIO8 (UART1 TX) -> DI do MAX485
#   GPIO9 (UART1 RX) <- RO do MAX485 (via divisor 1k/2k: o MAX485 sai com 5 V)
#   GPIO4            -> DE + RE do MAX485 (1 = transmitir, 0 = receber)
#   Sensor alimentado em 12 V; GND comum entre placa, MAX485, sensor e fonte.
#   A/B do sensor nos A/B do MAX485 (se não responder, inverta A e B).
#
# Uso:
#   import piranometro
#   p = piranometro.criar_padrao()
#   w = p.ler()                 # W/m² (int); levanta ModbusErro se falhar
#   w = p.ler_seguro()          # W/m² ou None, com novas tentativas
#   p.integrar(w, 60)           # soma a energia de 60 s ao total do dia
#   rs = p.fechar_dia()         # Rs do dia em MJ/m²/dia (entrada do FAO-56) e zera

import struct
import time

try:
    from machine import UART, Pin
except ImportError:          # permite testar a lógica no PC
    UART = Pin = None

try:
    import config_local as cfg
except ImportError:
    cfg = None


def _c(nome, padrao):
    return getattr(cfg, nome, padrao) if cfg else padrao


FUNC_READ_HOLDING = 0x03
REG_RADIACAO = 0x0000        # registrador de radiação (W/m²)


class ModbusErro(Exception):
    """Falha de comunicação Modbus com mensagem descritiva."""
    pass


# ------------------------- funções puras (testáveis no PC) -------------------------
def crc16(dados):
    """CRC-16 Modbus: início 0xFFFF, polinômio refletido 0xA001. No quadro, byte baixo primeiro."""
    crc = 0xFFFF
    for b in dados:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def montar_requisicao(endereco, registrador, quantidade=1):
    """Quadro de 8 bytes da função 0x03: [end][03][reg_hi][reg_lo][qtd_hi][qtd_lo][CRC_lo][CRC_hi]."""
    corpo = struct.pack(">BBHH", endereco, FUNC_READ_HOLDING, registrador, quantidade)
    return corpo + struct.pack("<H", crc16(corpo))


def interpretar_resposta(resp, endereco):
    """Valida a resposta de 7 bytes [end][03][02][hi][lo][CRC_lo][CRC_hi] e devolve o valor."""
    if len(resp) == 0:
        raise ModbusErro("timeout (sem resposta)")
    if len(resp) >= 5 and resp[1] == (FUNC_READ_HOLDING | 0x80):
        exc = resp[:5]
        if crc16(exc[:3]) != (exc[3] | (exc[4] << 8)):
            raise ModbusErro("CRC inválido")
        raise ModbusErro("exceção Modbus código {}".format(exc[2]))
    if len(resp) != 7:
        raise ModbusErro("resposta com tamanho errado ({} bytes)".format(len(resp)))
    if crc16(resp[:5]) != (resp[5] | (resp[6] << 8)):
        raise ModbusErro("CRC inválido")
    if resp[0] != endereco:
        raise ModbusErro("endereço inesperado (0x{:02X})".format(resp[0]))
    if resp[1] != FUNC_READ_HOLDING:
        raise ModbusErro("código de função inesperado (0x{:02X})".format(resp[1]))
    if resp[2] != 2:
        raise ModbusErro("byte count inválido ({})".format(resp[2]))
    return (resp[3] << 8) | resp[4]


def hexstr(dados):
    return " ".join("{:02X}".format(b) for b in dados)


# ----------------------------------- driver -----------------------------------
class Piranometro:
    def __init__(self, tx=None, rx=None, de_re=None, endereco=None, baud=None,
                 uart_id=1, timeout_ms=300, debug=False):
        self.tx = _c("PINO_RS485_TX", 8) if tx is None else tx
        self.rx = _c("PINO_RS485_RX", 9) if rx is None else rx
        self.endereco = _c("PIRANO_ENDERECO", 1) if endereco is None else endereco
        self.baud = _c("PIRANO_BAUD", 4800) if baud is None else baud
        self.timeout_ms = timeout_ms
        self.debug = debug
        pino_de = _c("PINO_RS485_DE_RE", 4) if de_re is None else de_re
        # começa em 0 (recepção) para não ocupar o barramento
        self.de_re = Pin(pino_de, Pin.OUT, value=0)
        self.uart = UART(uart_id, baudrate=self.baud, bits=8, parity=None, stop=1,
                         tx=Pin(self.tx), rx=Pin(self.rx))
        self.energia_j = 0.0     # J/m² acumulados no dia
        self.n = 0
        self.maximo = 0

    def _fim_tx(self, n_bytes):
        # write() só copia para o FIFO; espera o último bit sair antes de soltar o DE/RE
        try:
            self.uart.flush()
        except (AttributeError, OSError):
            time.sleep_us((n_bytes * 10 * 1000000) // self.baud + 1000)

    def _transacao(self, quadro, n_esperado):
        while self.uart.any() > 0:
            self.uart.read()
        self.de_re.value(1)
        self.uart.write(quadro)
        self._fim_tx(len(quadro))
        self.de_re.value(0)
        if self.debug:
            print("  TX:", hexstr(quadro))
        resp = b""
        inicio = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), inicio) < self.timeout_ms:
            if self.uart.any() > 0:
                pedaco = self.uart.read()
                if pedaco:
                    resp += pedaco
                while resp and resp[0] != quadro[0]:   # lixo da troca de direção (ex.: 0x00)
                    resp = resp[1:]
                if len(resp) >= n_esperado:
                    break
                if len(resp) >= 5 and (resp[1] & 0x80):
                    break
            else:
                time.sleep_ms(1)
        if self.debug:
            print("  RX:", hexstr(resp) if resp else "(nada)")
        return resp

    def ler(self):
        """Radiação solar em W/m² (int). Levanta ModbusErro com a causa."""
        quadro = montar_requisicao(self.endereco, REG_RADIACAO, 1)
        return interpretar_resposta(self._transacao(quadro, 7), self.endereco)

    def ler_seguro(self, tentativas=3):
        """Como ler(), mas tenta de novo e devolve None se todas falharem."""
        for _ in range(tentativas):
            try:
                return self.ler()
            except ModbusErro as e:
                if self.debug:
                    print("piranômetro:", e)
                time.sleep_ms(50)       # silêncio mínimo do Modbus-RTU
        return None

    # --------------- acumulado do dia (Rs para o FAO-56) ---------------
    def integrar(self, w_m2, dt_s):
        """Soma a energia de um intervalo: w_m2 lido, mantido por dt_s segundos."""
        if w_m2 is None:
            return
        self.energia_j += w_m2 * dt_s
        self.n += 1
        if w_m2 > self.maximo:
            self.maximo = w_m2

    def fechar_dia(self):
        """Devolve (Rs em MJ/m²/dia, pico em W/m², n de leituras) e zera o acumulado."""
        r = (self.energia_j / 1e6, self.maximo, self.n)
        self.energia_j = 0.0
        self.n = 0
        self.maximo = 0
        return r


def criar_padrao(debug=False):
    """Piranômetro no UART1 (GPIO8/9), DE/RE no GPIO4, endereço e baud do config_local."""
    return Piranometro(debug=debug)


if __name__ == "__main__" and UART is None:
    # testes no PC
    ok = True

    def confere(nome, obtido, esperado):
        global ok
        passou = obtido == esperado
        ok = ok and passou
        print("OK   " if passou else "FALHA", nome, "obtido", obtido, "esperado", esperado)

    req = montar_requisicao(1, 0, 1)
    confere("quadro de leitura end=1 reg=0", hexstr(req), "01 03 00 00 00 01 84 0A")
    corpo = bytes([0x01, 0x03, 0x02, 0x02, 0x8A])          # 0x028A = 650 W/m²
    resp = corpo + struct.pack("<H", crc16(corpo))
    confere("resposta 650 W/m²", interpretar_resposta(resp, 1), 650)
    for nome, ruim, msg in (
            ("timeout", b"", "timeout"),
            ("CRC errado", corpo + b"\x00\x00", "CRC"),
            ("tamanho", corpo, "tamanho")):
        try:
            interpretar_resposta(ruim, 1)
            confere(nome, "sem erro", msg)
        except ModbusErro as e:
            confere(nome, msg in str(e), True)
    print("\nTodos os testes passaram." if ok else "\nHá testes falhando.")
