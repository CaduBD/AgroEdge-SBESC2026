# AgroEdge - lâmina de irrigação pelo balanço do FAO-56.
# A classe do classificador decide SE irriga; esta conta decide QUANTO.
#
# Uso:
#   import lamina
#   deficit = lamina.atualizar_deficit(deficit, etc, chuva, irrigacao, taw)   # fim do dia
#   liquida, bruta = lamina.recomendar(classe, deficit)                      # mm para amanhã
#   minutos = lamina.tempo_min(bruta)                                        # tempo de válvula aberta
#   litros = lamina.litros_planta(mm)          # mm -> litros por planta (1 mm em 1 m² = 1 L)
#   total = lamina.litros_total(mm)            # litros na área toda (None sem N_PLANTAS)

import config_local as cfg


def atualizar_deficit(deficit, etc, chuva, irrigacao, taw, p=cfg.P_DEPLECAO):
    """Quanto falta para o solo voltar à capacidade de campo, em mm (FAO-56, eq. 84 e 85).
    Com o solo seco além do RAW, a planta transpira menos (Ks < 1) e gasta menos água.
    A chuva acima do que falta escorre ou drena, por isso o déficit não fica negativo;
    e não passa do TAW, que é o solo no ponto de murcha."""
    raw = p * taw
    ks = 1.0 if deficit <= raw else max(0.0, (taw - deficit) / ((1 - p) * taw))
    d = deficit + ks * etc - chuva - irrigacao
    if d < 0.0:
        return 0.0
    return d if d < taw else taw


def recomendar(classe, deficit, eficiencia=cfg.EFICIENCIA):
    """Lâmina para repor o déficit, em mm: (líquida, bruta).
    Adequado (classe 0): não irriga. Déficit moderado ou crítico: repõe tudo o que falta.
    A bruta é a líquida dividida pela eficiência do gotejamento (parte da água se perde)."""
    if classe == 0:
        return 0.0, 0.0
    return deficit, deficit / eficiencia


def litros_planta(mm, area_m2=cfg.AREA_M2):
    """Converte uma lâmina em mm para litros por planta: 1 mm sobre 1 m² é 1 litro."""
    return mm * area_m2


def litros_total(mm, area_m2=cfg.AREA_M2, n_plantas=getattr(cfg, "N_PLANTAS", None)):
    """Litros na área toda atendida pela estação; None se N_PLANTAS não foi configurado."""
    return None if not n_plantas else mm * area_m2 * n_plantas


def tempo_min(bruta, area_m2=cfg.AREA_M2, vazao_l_h=cfg.VAZAO_L_H):
    """Minutos de válvula aberta para aplicar a lâmina bruta (1 mm em 1 m² = 1 litro)."""
    return bruta * area_m2 / vazao_l_h * 60
