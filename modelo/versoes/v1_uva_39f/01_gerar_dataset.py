"""
AgroEdge - geração do dataset rotulado (uva Itália, Petrolina 2000-2009).

Rótulo = estado hídrico do solo pelo balanço hídrico diário do FAO-56 (cap. 8, eq. 85),
com irrigação SIMULADA (vários "produtores" com regras diferentes), sobre o clima real
do DataClimaBR. Cada ciclo sorteia um solo, uma profundidade de raiz e uma data de poda,
para o modelo servir em qualquer área do Vale (o TAW entra como feature).
Tudo que depende do Prof. Max está marcado como ASSUMIDO.

Uso: python3 01_gerar_dataset.py  -> gera dataset_uva.csv nesta pasta.
"""
import os
import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
CSV_CLIMA = os.path.join(AQUI, "dados", "petrolina_clima_2000_2009.csv")

# ---------------------------------------------------------------- parâmetros
CICLO_DIAS = 109             # Ávila Netto et al. (2000), Petrolina
CICLOS_POR_ANO = 48          # ciclos simulados por ano, cada um com poda, solo e produtor sorteados
AGUA_DISP_FAIXA = (0.06, 0.18)   # ASSUMIDO: θCC − θPMP (m³/m³), de arenoso a Vertissolo (FAO-56, tab. 19)
ZR_FAIXA = (0.4, 0.8)            # ASSUMIDO: profundidade efetiva das raízes (m), gotejamento
P_DEPLECAO = 0.35            # ASSUMIDO: fração p para uva de mesa (FAO-56, tab. 22) - conferir
KS_CRITICO = 0.5             # ASSUMIDO: Ks < 0,5 -> déficit crítico
SEMENTE = 42

CLASSES = {0: "adequado", 1: "deficit_moderado", 2: "deficit_critico"}


def solo(agua_disp, zr):
    """TAW, RAW e o Dr onde Ks = KS_CRITICO, em mm (FAO-56, eq. 82 e 83)."""
    taw = 1000 * agua_disp * zr
    raw = P_DEPLECAO * taw
    dr_critico = taw - KS_CRITICO * (1 - P_DEPLECAO) * taw
    return taw, raw, dr_critico


def kc_uva(dap):
    """Ávila Netto et al. (2000): Kc(DAP), r² = 0,97."""
    return -8e-5 * dap**2 + 0.0089 * dap + 0.488


def carregar_clima():
    df = pd.read_csv(CSV_CLIMA, parse_dates=["data"]).set_index("data").sort_index()
    completo = pd.date_range(df.index.min(), df.index.max(), freq="D")
    faltando = completo.difference(df.index)
    df = df.reindex(completo).interpolate()       # 2 dias faltantes (ver notas)
    df["interpolado"] = df.index.isin(faltando).astype(int)
    return df


def politica_aleatoria(rng, raw):
    """Um 'produtor' simulado. Mistura bons e maus manejos para cobrir as 3 classes."""
    tipo = rng.choice(["gatilho", "turno_fixo"])
    if tipo == "gatilho":
        return dict(tipo=tipo,
                    gatilho=rng.uniform(0.3, 2.4) * raw,     # irriga quando Dr passa disso
                    fracao=rng.uniform(0.3, 1.1),             # repõe essa fração de Dr
                    falha=rng.uniform(0.0, 0.5))             # chance de não irrigar no dia
    return dict(tipo=tipo,
                turno=int(rng.integers(1, 8)),                # irriga a cada N dias
                lamina_fator=rng.uniform(0.2, 1.2),           # lâmina = fator × ETc média × N
                falha=rng.uniform(0.0, 0.5))


def simular_ciclo(clima, inicio, agua_disp, zr, pol, rng, cenario_id):
    taw, raw, dr_critico = solo(agua_disp, zr)
    dias = clima.loc[inicio: inicio + pd.Timedelta(days=CICLO_DIAS - 1)]
    dr = 0.0                       # solo na capacidade de campo na poda (irrigação de pré-poda)
    ultimo = 0
    linhas = []
    for dap, (data, c) in enumerate(dias.iterrows()):
        kc = kc_uva(dap)
        etc = kc * c.ETo
        # decisão de irrigar (com base no estado do início do dia)
        irr = 0.0
        if rng.random() >= pol["falha"]:
            if pol["tipo"] == "gatilho" and dr > pol["gatilho"]:
                irr = pol["fracao"] * dr
            elif pol["tipo"] == "turno_fixo" and dap % pol["turno"] == 0:
                irr = pol["lamina_fator"] * etc * pol["turno"]
        # coeficiente de estresse e balanço (FAO-56 eq. 84 e 85)
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / ((1 - P_DEPLECAO) * taw))
        etc_aj = ks * etc
        dr = dr - c.Precipitacao - irr + etc_aj
        dr = min(max(dr, 0.0), taw)   # excesso drena (DP); não passa do ponto de murcha
        if irr > 0:
            ultimo = dap
        if dr <= raw:
            classe = 0
        elif dr <= dr_critico:
            classe = 1
        else:
            classe = 2
        linhas.append(dict(data=data, cenario=cenario_id, TAW=taw, dap=dap, kc=kc,
                           ETo=c.ETo, ETc=etc, chuva=c.Precipitacao, irrigacao=irr,
                           Tmax=c.Tmax, Tmin=c.Tmin, UR=c.Umidade_Relativa,
                           vento=c.Velocidade_Vento, radiacao=c.Radiacao_Solar,
                           dias_sem_irrigar=dap - ultimo, interpolado=c.interpolado,
                           Dr=dr, classe=classe))
    return linhas


def adicionar_janelas(df):
    """Acumulados que o firmware consegue manter (só passado, por cenário/ciclo)."""
    g = df.groupby(["cenario"], sort=False)
    for n in (3, 7, 14, 21, 28):
        for col in ("ETc", "chuva", "irrigacao"):
            df[f"{col}_{n}d"] = g[col].transform(lambda s: s.rolling(n, min_periods=1).sum())
    for col in ("ETc", "chuva", "irrigacao"):
        df[f"{col}_ciclo"] = g[col].cumsum()                  # desde a poda
    for n in ("7d", "14d", "21d", "28d", "ciclo"):
        df[f"saldo_{n}"] = df[f"chuva_{n}"] + df[f"irrigacao_{n}"] - df[f"ETc_{n}"]
        # a mesma soma em "tanques": 0,5 = metade do TAW do solo; assim um solo arenoso e um
        # argiloso com o mesmo valor estão igualmente secos
        for col in ("ETc", "chuva", "saldo"):
            df[f"{col}_{n}_taw"] = df[f"{col}_{n}"] / df.TAW
    return df


def main():
    rng = np.random.default_rng(SEMENTE)
    clima = carregar_clima()
    linhas = []
    cid = 0
    for ano in sorted(set(clima.index.year)):
        for _ in range(CICLOS_POR_ANO):
            # no Vale não há inverno: cada produtor poda em qualquer época do ano
            inicio = pd.Timestamp(ano, 1, 1) + pd.Timedelta(days=int(rng.integers(0, 365)))
            if inicio + pd.Timedelta(days=CICLO_DIAS - 1) > clima.index.max():
                continue
            agua_disp, zr = rng.uniform(*AGUA_DISP_FAIXA), rng.uniform(*ZR_FAIXA)
            pol = politica_aleatoria(rng, solo(agua_disp, zr)[1])
            linhas += simular_ciclo(clima, inicio, agua_disp, zr, pol, rng, cid)
            cid += 1
    df = adicionar_janelas(pd.DataFrame(linhas))
    # o split usa o ano da poda, para um ciclo não ficar metade no treino e metade no teste
    df["ano"] = df.groupby("cenario")["data"].transform("min").dt.year
    df["split"] = np.where(df.ano <= 2006, "treino", np.where(df.ano <= 2008, "validacao", "teste"))
    df.to_csv(os.path.join(AQUI, "dados", "dataset_uva.csv"), index=False, float_format="%.4f")

    print(f"TAW de {df.TAW.min():.1f} a {df.TAW.max():.1f} mm")
    print(f"{len(df)} linhas, {cid} cenários (ciclo × produtor)")
    tab = pd.crosstab(df.split, df.classe.map(CLASSES), normalize="index").round(3)
    print(tab)
    print(df.classe.map(CLASSES).value_counts())


if __name__ == "__main__":
    main()
