"""
AgroEdge - confere o eto.py do firmware contra o ET0 pronto do DataClimaBR (Petrolina, 2000-2009).

Passa o clima de cada dia (Tmax, Tmin, UR média, vento a 2 m e radiação) pela mesma função que
roda na placa e compara com a coluna ETo do arquivo. Se as contas estiverem certas, a diferença
fica pequena (o DataClimaBR usa a mesma equação, mas com latitude/altitude do ponto da grade).

Uso: python3 05_validar_eto.py
"""
import csv
import math
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "firmware", "modelo"))
import eto  # noqa: E402

CSV_CLIMA = os.path.join(AQUI, "dados", "petrolina_clima_2000_2009.csv")
LATITUDE = -9.39      # Petrolina
ALTITUDE_M = 370


def main():
    pares = []
    with open(CSV_CLIMA) as f:
        for r in csv.DictReader(f):
            a, m, d = (int(x) for x in r["data"].split("-"))
            calc = eto.penman_monteith(float(r["Tmax"]), float(r["Tmin"]),
                                       float(r["Radiacao_Solar"]), float(r["Velocidade_Vento"]),
                                       eto.dia_do_ano(a, m, d), LATITUDE, ALTITUDE_M,
                                       ur_media=float(r["Umidade_Relativa"]))
            pares.append((calc, float(r["ETo"])))
    n = len(pares)
    erros = [c - ref for c, ref in pares]
    rmse = math.sqrt(sum(e * e for e in erros) / n)
    vies = sum(erros) / n
    mc = sum(c for c, _ in pares) / n
    mr = sum(r for _, r in pares) / n
    cov = sum((c - mc) * (r - mr) for c, r in pares)
    r2 = cov ** 2 / (sum((c - mc) ** 2 for c, _ in pares) * sum((r - mr) ** 2 for _, r in pares))
    print("dias: %d" % n)
    print("ET0 médio: firmware %.2f | DataClimaBR %.2f mm/dia" % (mc, mr))
    print("RMSE %.3f mm/dia | viés %.3f mm/dia | maior erro %.3f mm/dia | R² %.4f"
          % (rmse, vies, max(abs(e) for e in erros), r2))
    ok = rmse < 0.15 and r2 > 0.99
    print("OK: o eto.py reproduz o Penman-Monteith do DataClimaBR." if ok else "ATENÇÃO: diferença grande")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
