"""AgroEdge - experimento: placa ligada no meio do ciclo, mas LOGO DEPOIS de uma irrigação forte ou de
uma chuva grande (solo perto do cheio), com registro manual da irrigação como no 09.
Uso: python3 10_experimento_inicio_apos_irrigacao.py"""
import os, sys
from importlib import import_module
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
g = import_module("06_gerar_dataset_geral")
LIMITE_CHEIO = 0.2        # "solo perto do cheio": déficit verdadeiro até 20% do TAW
CHUVA_GRANDE_MM = 10.0

g.REGISTRO = {"parcial": 1.0}
orig = g.sortear_observacao
def obs(rng, L):
    o = orig(rng, L); o.update(prob_reg=rng.uniform(0.85, 0.98), erro_reg=(0.75, 1.25)); return o
g.sortear_observacao = obs


def simular(clima, inicio_data, cult, ad, pol, obs, rng, cid):
    """Igual ao 06, mas a placa só liga no 1º dia, a partir do início sorteado, em que houve
    irrigação ou chuva grande e o solo ficou perto do cheio (se nunca houver, liga no sorteado)."""
    L, p, kcf = cult["L"], cult["p"], cult["kc"]
    taw = 1000 * ad * cult["zr"]
    placa = g.PlacaGeral(taw * obs["taw_fator"], p, L)
    dias = clima.loc[inicio_data: inicio_data + pd.Timedelta(days=L - 1)]
    dr, ligada, linhas = 0.0, obs["inicio"] == 0, []
    for d, (data, c) in enumerate(dias.iterrows()):
        kc = kcf(d); etc = kc * c.ETo; irr = 0.0
        if rng.random() >= pol["falha"]:
            if pol["tipo"] == "gatilho" and dr > pol["gatilho"]:
                irr = pol["fracao"] * dr
            elif pol["tipo"] == "turno_fixo" and d % pol["turno"] == 0:
                irr = pol["lamina_fator"] * etc * pol["turno"]
        dr, _ = g.balanco(dr, etc, c.Precipitacao, irr, taw, p)
        classe = g.classe_do_deficit(dr, taw, p)
        if not ligada:
            if d < obs["inicio"]:
                continue
            molhou = irr > 0 or c.Precipitacao >= CHUVA_GRANDE_MM
            if not (molhou and dr <= LIMITE_CHEIO * taw) and d < L - 1:
                continue
            ligada = True
            obs["inicio_real"] = d
        if obs["registro"] == "parcial":
            irr_inf = irr * rng.uniform(*obs["erro_reg"]) if irr > 0 and rng.random() < obs["prob_reg"] else 0.0
        else:
            irr_inf = irr
        v = placa.dia(d, kc, c.ETo * obs["et0_vies"] * (1 + rng.normal(0, g.ET0_RUIDO)),
                      c.Precipitacao * obs["chuva_fator"], irr_inf, c.Tmax, c.Tmin,
                      c.Umidade_Relativa, c.Velocidade_Vento, c.Radiacao_Solar)
        v.update(data=data, cenario=cid, cultura=cult["nome"], registro=obs["registro"],
                 inicio_meio=int(obs["inicio"] > 0), dia_ciclo=d, Dr=dr, TAW_real=taw, classe=classe,
                 classe_balanco_placa=g.classe_do_deficit(placa.deficit, taw * obs["taw_fator"], p))
        linhas.append(v)
    return linhas


g.simular = simular
g.SEMENTE = int(os.environ.get("SEMENTE", g.SEMENTE))
g.SAIDA = os.path.join(g.AQUI, "dados", "dataset_inicio.csv")
g.main()
t = import_module("07_treinar_mlp_geral")   # TensorFlow só a partir daqui
df = pd.read_csv(g.SAIDA)
feats = [c for c in df.columns if c not in ("data","cenario","cultura","registro","inicio_meio","dia_ciclo","Dr","TAW_real","classe","classe_balanco_placa","ano","split")]
tr, va, te = (df[df.split == s] for s in ("treino","validacao","teste"))
_, _, _, prever = t.treinar(tr, va, feats, 16, 0)
p = prever(te); y = te.classe.values; b = te.classe_balanco_placa.values
atraso = te[te.inicio_meio == 1].groupby("cenario").dia_ciclo.min()
print("ligadas no meio: começam em média no dia %.1f do ciclo" % atraso.mean())
for nome, mask in (("geral", np.ones(len(te), bool)), ("ligada no início", (te.inicio_meio==0).values), ("ligada no meio", (te.inicio_meio==1).values)):
    mb, mr = t.metricas(y[mask], b[mask]), t.metricas(y[mask], p[mask])
    print(f"{nome:18s} balanço {mb['acc']:.3f} (crít {mb['rec_crit']:.2f}) | rede {mr['acc']:.3f} (crít {mr['rec_crit']:.2f}) | dias {mask.sum()}")
