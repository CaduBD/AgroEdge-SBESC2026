# AgroEdge - biblioteca de culturas.
#
# Aqui ficam os dados CIENTÍFICOS de cada cultura (vêm da literatura, não do produtor):
# como o consumo de água muda ao longo do ciclo (Kc) e quanto a planta tolera de solo seco (p).
# Os dados DO LOCAL (qual cultura está plantada, data da poda/floração, solo, irrigação) ficam
# no config_local.py, que escolhe uma cultura desta biblioteca pelo nome (CULTURA).
#
# Para acrescentar uma cultura: copie um bloco, troque os números e preencha "fonte" com a
# referência de onde cada número veio. Não invente valores: cultura sem fonte não entra.
# O resto do firmware não precisa mudar; ele só pergunta a esta biblioteca o Kc de hoje.
#
# ---------------------------------------------------------------------------------------------
# Significado de cada campo
# ---------------------------------------------------------------------------------------------
# nome        Nome legível, para display, dashboard e relatório.
# referencia  Evento a partir do qual os dias do ciclo são contados. O produtor informa a data
#             desse evento em config_local.DATA_REFERENCIA.
#               "poda"      -> dias após a poda (DAP), usado na uva;
#               "floracao"  -> dias após o início da floração (DAF), usado na manga.
# ciclo_dias  Duração do ciclo coberto pelos dados de Kc, em dias, a partir da referência.
#             Fora de 0..ciclo_dias não há dado medido: o Kc é o da ponta mais próxima e o
#             main.py avisa "fora do ciclo com dados".
# kc          Coeficiente de cultura: ETc = Kc × ET0 (FAO-56, cap. 6). Diz quanto a cultura
#             consome em relação à grama de referência. Duas formas aceitas:
#               ("polinomio", (a, b, c))       -> Kc(d) = a·d² + b·d + c, d = dias do ciclo
#               ("fases", ((nome, dias, kc), ...)) -> Kc constante em cada fase, fases em ordem,
#                                                    cada uma com sua duração em dias
# p           Fração de depleção (FAO-56, tab. 22): fração da água disponível do solo (TAW) que
#             a planta consegue gastar antes de sofrer estresse. RAW = p × TAW. Define o limite
#             entre "adequado" e "déficit" no balanço hídrico (lamina.py).
# raiz_m      Profundidade efetiva das raízes para o manejo da irrigação, em metros: a camada de
#             solo considerada no balanço. TAW = 1000 × (θCC − θPMP) × raiz_m (FAO-56, eq. 82).
#             O config_local pode sobrescrever (RAIZ_M) se houver medida no pomar.
# local       Onde e em que sistema os dados foram obtidos (valem melhor em condições parecidas).
# fonte       Referência bibliográfica de cada número.
# assumido    Lista do que ainda precisa ser confirmado (vazia = tudo com fonte direta).
# ---------------------------------------------------------------------------------------------

CULTURAS = {
    "uva_italia": {
        "nome": "Uva de mesa cv. Itália",
        "referencia": "poda",
        "ciclo_dias": 109,
        # Kc(DAP) = -8e-5·DAP² + 0,0089·DAP + 0,488 (r² = 0,97); Kc de 0,50 a 0,74 no ciclo
        "kc": ("polinomio", (-8e-5, 0.0089, 0.488)),
        "p": 0.35,
        "raiz_m": 0.6,
        "local": "Bebedouro, Petrolina-PE; videira em latada, irrigada",
        "fonte": ("Kc e ciclo: ÁVILA NETTO, J. et al. Exigências hídricas da videira na região "
                  "do Submédio São Francisco. Pesquisa Agropecuária Brasileira, 2000. "
                  "p: ALLEN, R. G. et al. FAO Irrigation and Drainage Paper 56, 1998, tab. 22 "
                  "(uva de mesa, p = 0,35). Raiz: concentração de 0,4 a 0,6 m com gotejamento "
                  "(modelo/DECISOES.md, seção 4)."),
        "assumido": ["raiz_m (0,6 m): valor típico para gotejamento, conferir no pomar"],
    },

    "manga_tommy_atkins": {
        "nome": "Manga cv. Tommy Atkins",
        "referencia": "floracao",
        "ciclo_dias": 149,            # 20 + 39 + 51 + 39 dias, da floração à maturação
        "kc": ("fases", (
            ("floracao", 20, 0.44),
            ("queda_frutos", 39, 0.65),
            ("formacao_frutos", 51, 0.83),
            ("maturacao", 39, 0.84),
        )),
        "p": 0.5,
        "raiz_m": 0.6,
        "local": "Petrolina-PE, pomar de 6 anos, espaçamento 8 × 5 m, safra de 1999",
        "fonte": ("Kc e duração das fases: SILVA, V. P. R. Estimativa das necessidades hídricas "
                  "da mangueira. Tese (Doutorado), UFPB, Campina Grande, 2000; valores adotados "
                  "pela Embrapa Semiárido (Cultivo da Mangueira, Sistemas de Produção 2, 2004) e "
                  "pela Agência de Informação Embrapa (Bassoi, Teixeira e Soares). "
                  "p: fator de reposição de 50% para a mangueira (Soares e Costa, 1995, citado "
                  "em PINTO, J. M.; SILVA, J. A.; COELHO, E. F., Irrigação e fertirrigação na "
                  "cultura da manga, Embrapa). O FAO-56 (tab. 22) não lista manga e usa 0,5 como "
                  "valor comum. Raiz: 65% das raízes de absorção entre 0 e 0,6 m e sensores de "
                  "umidade recomendados até 0,6 m (Pinto, Silva e Coelho)."),
        "assumido": ["Kc fora da floração-maturação (pós-colheita, fluxos vegetativos, indução "
                     "floral, repouso): sem dado; usa o Kc da fase mais próxima",
                     "cv. Palmer não coberta (outras fases e Kc)"],
    },
}


def cultura(nome):
    """Dados de uma cultura da biblioteca, com erro claro se o nome não existir."""
    try:
        return CULTURAS[nome]
    except KeyError:
        raise ValueError("cultura '%s' não está na biblioteca; opções: %s"
                         % (nome, ", ".join(sorted(CULTURAS))))


def kc_do_dia(nome, dias):
    """(Kc, nome da fase ou None, True se 'dias' está dentro do ciclo com dados)."""
    c = cultura(nome)
    tipo, dados = c["kc"]
    dentro = 0 <= dias <= c["ciclo_dias"]
    d = min(max(dias, 0), c["ciclo_dias"])      # fora do ciclo: ponta mais próxima
    if tipo == "polinomio":
        a, b, k = dados
        return a * d * d + b * d + k, None, dentro
    if tipo == "fases":
        inicio = 0
        for fase, duracao, kc in dados:
            if d < inicio + duracao:
                return kc, fase, dentro
            inicio += duracao
        fase, _, kc = dados[-1]
        return kc, fase, dentro
    raise ValueError("tipo de Kc desconhecido: %s" % tipo)


def dias_desde(inicio, hoje):
    """Dias entre duas datas (ano, mês, dia), sem depender do time.mktime da placa."""
    def ordinal(a, m, d):
        a2 = a - 1
        acum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
        bis = a % 4 == 0 and (a % 100 != 0 or a % 400 == 0)
        return a2 * 365 + a2 // 4 - a2 // 100 + a2 // 400 + acum[m - 1] + d + (1 if bis and m > 2 else 0)
    return ordinal(*hoje) - ordinal(*inicio)


if __name__ == "__main__":
    # testes no PC
    assert dias_desde((2026, 1, 15), (2026, 1, 15)) == 0
    assert dias_desde((2025, 12, 31), (2026, 1, 1)) == 1
    assert dias_desde((2028, 2, 28), (2028, 3, 1)) == 2           # bissexto
    k, _, dentro = kc_do_dia("uva_italia", 0)
    assert abs(k - 0.488) < 1e-9 and dentro
    k, _, _ = kc_do_dia("uva_italia", 56)
    assert abs(k - (-8e-5 * 56 * 56 + 0.0089 * 56 + 0.488)) < 1e-9
    m = "manga_tommy_atkins"
    assert kc_do_dia(m, 0)[:2] == (0.44, "floracao")
    assert kc_do_dia(m, 19)[:2] == (0.44, "floracao")
    assert kc_do_dia(m, 20)[:2] == (0.65, "queda_frutos")
    assert kc_do_dia(m, 59)[:2] == (0.83, "formacao_frutos")
    assert kc_do_dia(m, 110)[:2] == (0.84, "maturacao")
    assert kc_do_dia(m, 149) == (0.84, "maturacao", True)
    assert kc_do_dia(m, 200) == (0.84, "maturacao", False)
    assert kc_do_dia(m, -10) == (0.44, "floracao", False)
    for nome, c in CULTURAS.items():
        assert c["fonte"] and 0 < c["p"] < 1 and c["raiz_m"] > 0, nome
        if c["kc"][0] == "fases":
            assert sum(f[1] for f in c["kc"][1]) == c["ciclo_dias"], nome
    print("OK:", ", ".join(c["nome"] for c in CULTURAS.values()))
