"""AgroEdge - confere os experimentos 09 (registro manual) e 10 (placa ligada logo após uma irrigação
forte) com 5 sementes e TODOS os anos (2000-2009), só com o balanço da placa (não treina rede).
O teste de 2009 tem poucos cenários (~35) e varia vários pontos de uma semente para outra; esta
conta dá a média mais estável. Uso: python3 11_inicio_varias_sementes.py"""
import contextlib
import io
import os

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTOS = (("registro manual, placa ligada em qualquer dia", "09_experimento_registro.py"),
                ("registro manual, placa ligada logo após irrigação forte", "10_experimento_inicio_apos_irrigacao.py"))
SEMENTES = (7, 11, 23, 31, 47)

res = {}
for nome, script in EXPERIMENTOS:
    caminho = os.path.join(AQUI, script)
    fonte = open(caminho, encoding="utf-8").read().split("g.main()")[0] + "g.main()\n"   # só gera o dataset
    for s in SEMENTES:
        os.environ["SEMENTE"] = str(s)
        ns = {"__file__": caminho, "__name__": "experimento"}
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(fonte, script, "exec"), ns)
        df = pd.read_csv(ns["g"].SAIDA)
        for rot, m in (("ligada no início do ciclo", df.inicio_meio == 0), ("ligada no meio do ciclo", df.inicio_meio == 1)):
            d = df[m]
            res.setdefault((nome, rot, "acurácia"), []).append((d.classe == d.classe_balanco_placa).mean())
            res.setdefault((nome, rot, "crítico"), []).append(
                ((d.classe == 2) & (d.classe_balanco_placa == 2)).sum() / (d.classe == 2).sum())
        os.remove(ns["g"].SAIDA)
for (nome, rot, met), v in res.items():
    print(f"{nome} | {rot} | {met}: {np.mean(v):.3f} (de {min(v):.3f} a {max(v):.3f})")
