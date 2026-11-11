"""AgroEdge - experimento: e se todos os cenários tivessem sensor de vazão? (irrigação medida com erro de ±5%);
os outros erros (ET0, chuva, TAW, placa ligada no meio do ciclo) continuam. Uso: python3 08_experimento_vazao.py"""
import sys, os
from importlib import import_module
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
g = import_module("06_gerar_dataset_geral")
g.REGISTRO = {"parcial": 1.0}
orig = g.sortear_observacao
def obs(rng, L):
    o = orig(rng, L); o.update(prob_reg=1.0, erro_reg=(0.95, 1.05)); return o
g.sortear_observacao = obs
g.SAIDA = os.path.join(g.AQUI, "dados", "dataset_vazao.csv")
g.main()
t = import_module("07_treinar_mlp_geral")   # TensorFlow só a partir daqui
df = pd.read_csv(g.SAIDA)
feats = [c for c in df.columns if c not in ("data","cenario","cultura","registro","inicio_meio","dia_ciclo","Dr","TAW_real","classe","classe_balanco_placa","ano","split")]
tr, va, te = (df[df.split == s] for s in ("treino","validacao","teste"))
_,_,_,prever = t.treinar(tr, va, feats, 16, 0)
p = prever(te); y = te.classe.values; b = te.classe_balanco_placa.values
for nome, mask in (("geral", np.ones(len(te), bool)), ("ligada no início", (te.inicio_meio==0).values), ("ligada no meio", (te.inicio_meio==1).values)):
    mb, mr = t.metricas(y[mask], b[mask]), t.metricas(y[mask], p[mask])
    print(f"{nome:18s} balanço {mb['acc']:.3f} (crít {mb['rec_crit']:.2f}) | rede {mr['acc']:.3f} (crít {mr['rec_crit']:.2f}) | dias {mask.sum()}")
