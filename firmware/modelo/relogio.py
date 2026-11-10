# AgroEdge - data e hora da estação.
# O RP2040 não guarda a hora quando a energia cai: ao ligar, o relógio interno volta para
# 2021. O sistema precisa da data para fechar o dia à meia-noite, para o dia do ano do ET0 e
# para os dias após a poda/floração. Duas fontes, nesta ordem:
#   1. Módulo DS3231 (RTC com bateria CR2032) no I²C0 da BitDogLab (SDA GPIO0, SCL GPIO1,
#      endereço 0x68, alimentado em 3V3). Guarda a hora com a placa desligada.
#   2. Internet (NTP) pelo Wi-Fi da Pico W, se WIFI_SSID estiver no config_local. Quando o NTP
#      funciona, ele também acerta o DS3231.
# Sem nenhum dos dois, dá para acertar à mão pelo Thonny: relogio.acertar(2026, 11, 11, 14, 30).
# Tudo em hora LOCAL (FUSO_HORAS no config_local; Petrolina = -3).
#
# Uso:
#   import relogio
#   fonte = relogio.iniciar()      # "ds3231", "ntp", "ds3231+ntp" ou None (hora não confiável)
#   relogio.valido()               # True se a data é de 2025 em diante
#   relogio.agora()                # (ano, mês, dia, hora, minuto, segundo)
#   relogio.hoje()                 # (ano, mês, dia)

import time

try:
    from machine import I2C, Pin, RTC
except ImportError:          # permite testar a lógica no PC
    I2C = Pin = RTC = None

try:
    import config_local as cfg
except ImportError:
    cfg = None

ENDERECO_DS3231 = 0x68
ANO_MINIMO = 2025


def _c(nome, padrao):
    return getattr(cfg, nome, padrao) if cfg else padrao


def bcd2dec(b):
    return (b >> 4) * 10 + (b & 0x0F)


def dec2bcd(d):
    return ((d // 10) << 4) | (d % 10)


def dia_semana(ano, mes, dia):
    """0 = segunda ... 6 = domingo (mesmo padrão do time.localtime do MicroPython)."""
    t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    a = ano - 1 if mes < 3 else ano
    domingo0 = (a + a // 4 - a // 100 + a // 400 + t[mes - 1] + dia) % 7   # 0 = domingo
    return (domingo0 + 6) % 7


def codificar_ds3231(ano, mes, dia, hora, minuto, segundo):
    """7 bytes dos registradores 0x00 a 0x06 do DS3231 (modo 24 h)."""
    return bytes((dec2bcd(segundo), dec2bcd(minuto), dec2bcd(hora),
                  dia_semana(ano, mes, dia) + 1, dec2bcd(dia), dec2bcd(mes), dec2bcd(ano - 2000)))


def decodificar_ds3231(b):
    seg = bcd2dec(b[0] & 0x7F)
    minuto = bcd2dec(b[1] & 0x7F)
    hora = bcd2dec(b[2] & 0x3F)
    dia = bcd2dec(b[4] & 0x3F)
    mes = bcd2dec(b[5] & 0x1F)
    ano = 2000 + bcd2dec(b[6])
    return ano, mes, dia, hora, minuto, seg


class DS3231:
    def __init__(self, i2c, endereco=ENDERECO_DS3231):
        self.i2c = i2c
        self.end = endereco

    def presente(self):
        try:
            return self.end in self.i2c.scan()
        except OSError:
            return False

    def ler(self):
        return decodificar_ds3231(self.i2c.readfrom_mem(self.end, 0x00, 7))

    def gravar(self, ano, mes, dia, hora, minuto, segundo):
        self.i2c.writeto_mem(self.end, 0x00, codificar_ds3231(ano, mes, dia, hora, minuto, segundo))
        # zera o bit OSF (oscilador parou), para saber depois se a bateria acabou
        st = self.i2c.readfrom_mem(self.end, 0x0F, 1)[0]
        self.i2c.writeto_mem(self.end, 0x0F, bytes((st & 0x7F,)))

    def perdeu_hora(self):
        """True se o oscilador parou desde o último acerto (bateria fraca ou ausente)."""
        return bool(self.i2c.readfrom_mem(self.end, 0x0F, 1)[0] & 0x80)


_ds = None


def _ds3231():
    global _ds
    if _ds is None and I2C is not None:
        try:
            i2c = I2C(0, sda=Pin(_c("PINO_I2C0_SDA", 0)), scl=Pin(_c("PINO_I2C0_SCL", 1)),
                      freq=100000)
            d = DS3231(i2c)
            _ds = d if d.presente() else False
        except Exception:
            _ds = False
    return _ds or None


def _rtc_interno(ano, mes, dia, hora, minuto, segundo):
    RTC().datetime((ano, mes, dia, dia_semana(ano, mes, dia), hora, minuto, segundo, 0))


def acertar(ano, mes, dia, hora=0, minuto=0, segundo=0):
    """Acerta à mão (hora local): relógio interno e, se houver, o DS3231."""
    _rtc_interno(ano, mes, dia, hora, minuto, segundo)
    d = _ds3231()
    if d:
        d.gravar(ano, mes, dia, hora, minuto, segundo)
    return agora()


def _ntp():
    """Acerta pelo NTP via Wi-Fi. Devolve True se conseguiu."""
    ssid = _c("WIFI_SSID", "")
    if not ssid:
        return False
    try:
        import network
        import ntptime
        w = network.WLAN(network.STA_IF)
        w.active(True)
        if not w.isconnected():
            w.connect(ssid, _c("WIFI_SENHA", ""))
            for _ in range(30):                     # até ~15 s
                if w.isconnected():
                    break
                time.sleep_ms(500)
        if not w.isconnected():
            return False
        ntptime.settime()                           # acerta o RTC interno em UTC
        local = time.localtime(time.time() + int(_c("FUSO_HORAS", -3) * 3600))
        _rtc_interno(*local[:6])
        return True
    except Exception:
        return False


def iniciar(usar_ntp=True):
    """Acerta o relógio interno ao ligar. Devolve a fonte usada ou None."""
    fonte = None
    d = _ds3231()
    if d:
        try:
            if not d.perdeu_hora():
                t = d.ler()
                if t[0] >= ANO_MINIMO:
                    _rtc_interno(*t)
                    fonte = "ds3231"
        except OSError:
            pass
    if usar_ntp and _ntp():
        fonte = "ntp" if fonte is None else "ds3231+ntp"
        if d:
            try:
                d.gravar(*agora())
            except OSError:
                pass
    return fonte if valido() else None


def agora():
    return tuple(time.localtime()[:6])


def hoje():
    return agora()[:3]


def valido():
    return agora()[0] >= ANO_MINIMO


if __name__ == "__main__":
    if I2C is None:
        for t in ((2026, 11, 11, 14, 30, 5), (2027, 2, 28, 23, 59, 59), (2030, 1, 1, 0, 0, 0)):
            assert decodificar_ds3231(codificar_ds3231(*t)) == t, t
        assert dia_semana(2026, 11, 10) == 1      # 10/11/2026 é terça
        assert dia_semana(2026, 11, 15) == 6      # domingo
        print("OK")
    else:
        print("fonte:", iniciar(), " agora:", agora(), " DS3231:", bool(_ds3231()))
