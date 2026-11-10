# AgroEdge - evapotranspiração de referência diária, Penman-Monteith FAO-56 (Allen et al., 1998).
# Funções puras, sem nada da placa: rodam igual no PC e no MicroPython.
#
# Uso:
#   import eto
#   et0 = eto.penman_monteith(tmax, tmin, rs, u2, dia_do_ano,
#                             lat=cfg.LATITUDE, alt=cfg.ALTITUDE_M, ur_media=ur)
#   # ou, se tiver as umidades extremas do dia (melhor, FAO-56 eq. 17):
#   et0 = eto.penman_monteith(..., ur_max=urmax, ur_min=urmin)
#
# Unidades: °C, %, Rs em MJ/m²/dia, u2 em m/s a 2 m, latitude em graus (sul negativo),
# altitude em m. Saída em mm/dia. G (fluxo de calor no solo) = 0 na escala diária (eq. 42).

import math

SIGMA = 4.903e-9      # Stefan-Boltzmann, MJ K-4 m-2 dia-1
GSC = 0.0820          # constante solar, MJ m-2 min-1
ALBEDO = 0.23         # grama de referência


def pressao_saturacao(t):
    """e°(T), kPa (eq. 11)."""
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def declividade(t):
    """Δ, kPa/°C (eq. 13)."""
    return 4098 * pressao_saturacao(t) / (t + 237.3) ** 2


def psicrometrica(alt):
    """γ, kPa/°C (eq. 7 e 8)."""
    p = 101.3 * ((293 - 0.0065 * alt) / 293) ** 5.26
    return 0.000665 * p


def radiacao_extraterrestre(lat, j):
    """Ra, MJ/m²/dia (eq. 21 a 25)."""
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    return (24 * 60 / math.pi) * GSC * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))


def pressao_real(tmax, tmin, ur_media=None, ur_max=None, ur_min=None):
    """ea, kPa. Com UR máx e mín usa a eq. 17; só com a média, a eq. 19."""
    if ur_max is not None and ur_min is not None:
        return (pressao_saturacao(tmin) * ur_max / 100 + pressao_saturacao(tmax) * ur_min / 100) / 2
    if ur_media is None:
        raise ValueError("informe ur_media ou ur_max e ur_min")
    es = (pressao_saturacao(tmax) + pressao_saturacao(tmin)) / 2
    return ur_media / 100 * es


def saldo_radiacao(tmax, tmin, rs, ea, lat, alt, j):
    """Rn, MJ/m²/dia (eq. 37, 38 e 39)."""
    ra = radiacao_extraterrestre(lat, j)
    rso = (0.75 + 2e-5 * alt) * ra
    rns = (1 - ALBEDO) * rs
    razao = min(rs / rso, 1.0) if rso > 0 else 1.0
    rnl = SIGMA * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 \
        * (0.34 - 0.14 * math.sqrt(max(ea, 0.0))) * (1.35 * razao - 0.35)
    return rns - rnl


def penman_monteith(tmax, tmin, rs, u2, j, lat, alt, ur_media=None, ur_max=None, ur_min=None):
    """ET0 diária em mm (eq. 6)."""
    if tmin > tmax:
        tmax, tmin = tmin, tmax
    t = (tmax + tmin) / 2
    es = (pressao_saturacao(tmax) + pressao_saturacao(tmin)) / 2
    ea = pressao_real(tmax, tmin, ur_media, ur_max, ur_min)
    if ea > es:
        ea = es                         # UR de 100% com erro de sensor não pode dar déficit negativo
    d = declividade(t)
    g = psicrometrica(alt)
    rn = saldo_radiacao(tmax, tmin, rs, ea, lat, alt, j)
    et0 = (0.408 * d * rn + g * 900 / (t + 273) * u2 * (es - ea)) / (d + g * (1 + 0.34 * u2))
    return et0 if et0 > 0 else 0.0


def dia_do_ano(ano, mes, dia):
    bissexto = ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)
    acum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    return acum[mes - 1] + dia + (1 if bissexto and mes > 2 else 0)


if __name__ == "__main__":
    # FAO-56, exemplo 18 (Bruxelas, 6 de julho): resultado do livro = 3,9 mm/dia.
    # Rs = 22,07 MJ/m²/dia, u2 = 2,078 m/s, lat 50°48'N, alt 100 m.
    r = penman_monteith(21.5, 12.3, 22.07, 2.078, dia_do_ano(2001, 7, 6), 50.8, 100,
                        ur_max=84, ur_min=63)
    print("FAO-56 exemplo 18: %.2f mm/dia (livro: 3,9)" % r)
    assert abs(r - 3.9) < 0.1, r
    print("Ra(lat 50,8; J=187) = %.2f (livro: 41,09)" % radiacao_extraterrestre(50.8, 187))
    print("OK")
