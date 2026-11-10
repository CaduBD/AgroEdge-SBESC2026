"""AgroEdge - testa no PC a parte de cálculo do main.py (fechar o dia), sem a placa.
Usa 109 dias reais de Petrolina (2009) como se fossem os totais diários dos sensores.
Uso: python3 teste_main_pc.py   (na pasta firmware/modelo, com petrolina_clima_2000_2009.csv
     em ../../modelo/dados/ ou nesta pasta)"""
import csv
import os

import config_local as cfg
import historico
import main

AQUI = os.path.dirname(os.path.abspath(__file__))
CSV = next(p for p in (os.path.join(AQUI, "petrolina_clima_2000_2009.csv"),
                       os.path.join(AQUI, "..", "..", "modelo", "dados", "petrolina_clima_2000_2009.csv"))
           if os.path.exists(p))

cfg.DATA_PODA = (2009, 3, 1)
h = historico.Historico(arquivo=None)
contagem = [0, 0, 0]
maior_dif = 0.0
with open(CSV) as f:
    for r in csv.DictReader(f):
        a, m, d = (int(x) for x in r["data"].split("-"))
        if (a, m, d) < cfg.DATA_PODA:
            continue
        if cfg.dap((a, m, d)) > 108:
            break
        ar = {"tmax": float(r["Tmax"]), "tmin": float(r["Tmin"]), "ur_media": float(r["Umidade_Relativa"]),
              "ur_max": None, "ur_min": None, "n": 1440}
        res = main.processar_dia(h, (a, m, d), ar, float(r["Radiacao_Solar"]),
                                 float(r["Velocidade_Vento"]), float(r["Precipitacao"]), 0.0, 1.0)
        assert res["classe"] is not None, res
        contagem[res["classe"]] += 1
        maior_dif = max(maior_dif, abs(res["et0"] - float(r["ETo"])))
        if res["dap"] in (0, 30, 60, 90, 108):
            print(res["data"], "DAP %3d  ET0 %.2f (ref %.2f)  ETc %.2f  déficit %5.1f  %-16s lâmina %.1f mm"
                  % (res["dap"], res["et0"], float(r["ETo"]), res["etc"], res["deficit"],
                     res["nome_classe"], res["lamina_bruta"]))
        linha, cab = main.linha_diario(res)

print("classes no ciclo (sem irrigar):", dict(zip(("adequado", "moderado", "crítico"), contagem)))
print("maior diferença de ET0 para o DataClimaBR: %.2f mm/dia" % maior_dif)

# dados faltando
ar = {"tmax": 32.0, "tmin": 21.0, "ur_media": 60.0, "ur_max": 85.0, "ur_min": 35.0}
r = main.processar_dia(historico.Historico(arquivo=None), (2009, 3, 10), ar, None, None, 0, 0, 1.0)
assert r["et0"] and "sem vento: usado 2 m/s" in r["avisos"] and len(r["avisos"]) == 3, r
r = main.processar_dia(historico.Historico(arquivo=None), (2009, 3, 10), {}, 20.0, 2.0, 0, 0, 1.0)
assert r["et0"] is None and r["classe"] is None
r = main.processar_dia(historico.Historico(arquivo=None), (2009, 3, 10), ar, 20.0, 2.0, 0, 0, 0.4)
assert r["classe"] is None and "incompleto" in r["avisos"][0]
print("cabeçalho do diário:", cab.strip())
print("linha exemplo:", linha.strip())
print("OK: casos de dado faltando e dia incompleto tratados")
