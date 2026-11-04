"""Testes da etapa 5. Valida o método em dados sintéticos com efeito conhecido."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.hipoteses import (
    HIPOTESES_DIARIAS,
    Z_MATRIZ,
    ajustar_esteira,
    ajustar_newey_west,
    alinhar,
    avaliar_placebo,
    bases_esteira,
    bootstrap_blocos,
    matriz_exploratoria,
    preparar_diario,
    preparar_sessoes,
    avaliar_diarias,
    avaliar_esteira,
    zscore_movel,
)

N = 300


def diario_sintetico(efeito_treino=0.0, semente=1):
    """Treino de D afeta o RMSSD da noite que termina em D+1, com o efeito pedido por 30 min."""
    g = np.random.default_rng(semente)
    dias = pd.date_range("2026-01-01", periods=N, freq="D")
    treino = g.choice([0.0, 30.0, 60.0], N)
    d = pd.DataFrame({"dia": dias, "treino_min": treino, "min_fc_acima_limiar": treino / 3, "dia_parcial": False})
    for c in Z_MATRIZ:
        d[c] = g.normal(50, 5, N)
    choque = np.r_[0.0, treino[:-1]] / 30
    d["rmssd_noite"] = 70 + g.normal(0, 8, N) + efeito_treino * 8 * choque
    return d


def test_zscore_nao_usa_o_proprio_dia():
    s = pd.Series(np.arange(40, dtype=float))
    alterada = s.copy()
    alterada.iloc[30] = 1000.0
    assert zscore_movel(s).iloc[29] == zscore_movel(alterada).iloc[29]
    assert zscore_movel(alterada).iloc[30] != zscore_movel(s).iloc[30]


def test_zscore_valor_conhecido():
    s = pd.Series([10.0, 12.0] * 14 + [14.0])
    anterior = s.iloc[:28]
    assert zscore_movel(s).iloc[28] == pytest.approx((14 - anterior.mean()) / anterior.std())


def test_zscore_exige_quatorze_valores():
    s = pd.Series(np.arange(30, dtype=float))
    z = zscore_movel(s)
    assert z.iloc[:14].isna().all()
    assert z.iloc[14:].notna().all()
    furada = s.copy()
    furada.iloc[:20] = np.nan
    assert zscore_movel(furada).iloc[25:].isna().all()


def test_calendario_com_buraco_gera_erro():
    d = diario_sintetico().drop(index=10)
    with pytest.raises(ValueError):
        preparar_diario(d)


def test_lag_alinha_treino_de_ontem_com_a_noite_de_hoje():
    d = preparar_diario(diario_sintetico())
    a = alinhar(d, "rmssd_noite", "treino_30min", 1)
    assert a["x"].iloc[5] == d["treino_30min"].iloc[4]
    assert a["y"].iloc[5] == d["rmssd_noite"].iloc[5]
    assert a["y_ant"].iloc[5] == d["rmssd_noite"].iloc[4]


def test_dia_parcial_nao_entra_como_treino():
    bruto = diario_sintetico()
    bruto.loc[0, "dia_parcial"] = True
    assert np.isnan(preparar_diario(bruto)["treino_30min"].iloc[0])


def test_modelo_recupera_efeito_conhecido():
    d = preparar_diario(diario_sintetico(efeito_treino=-0.6))
    modelo, n = ajustar_newey_west(alinhar(d, "z_rmssd_noite", "treino_30min", 1))
    assert n > 250
    assert modelo.params["x"] == pytest.approx(-0.6, abs=0.15)
    assert modelo.pvalues["x"] < 0.001


def test_bootstrap_contem_o_efeito_e_exclui_zero():
    dados = alinhar(preparar_diario(diario_sintetico(efeito_treino=-0.6)), "z_rmssd_noite", "treino_30min", 1)
    inf, sup = bootstrap_blocos(dados, sorteios=200)
    assert inf < -0.6 < sup
    assert sup < 0


def test_criterios_sustentam_efeito_real():
    r, sens = avaliar_diarias(preparar_diario(diario_sintetico(efeito_treino=-0.6)), sorteios=200)
    assert r.set_index("id").loc["H1", "sustentada"]
    assert set(sens["id"]) == {"H1", "H2", "H3"}


def test_falsos_positivos_ficam_perto_do_esperado():
    """Sem efeito nenhum, os critérios quase nunca sustentam uma hipótese."""
    total = 0
    for semente in range(10):
        r, _ = avaliar_diarias(preparar_diario(diario_sintetico(semente=semente)), sorteios=100)
        total += int(r["sustentada"].sum())
    assert total <= 3  # 50 testes sem efeito real


def test_placebo_nao_acusa_efeito_do_treino_sobre_a_noite_anterior():
    r = avaliar_placebo(preparar_diario(diario_sintetico(efeito_treino=-0.6))).set_index("id")
    assert r.loc["H1", "ic_inf"] < 0 < r.loc["H1", "ic_sup"]


def test_hipoteses_nao_usam_scores_da_samsung():
    assert not [h for h in HIPOTESES_DIARIAS if h.x.startswith("sam_") or h.y.startswith("sam_")]


def sessoes_sinteticas(efeito=0.0, semente=3):
    d = preparar_diario(diario_sintetico())
    d["sono_fim_local"] = d.index + pd.Timedelta(hours=9)
    g = np.random.default_rng(semente)
    dias = d.index[60:100]
    s = pd.DataFrame({
        "dia": dias, "inicio_local": dias + pd.Timedelta(hours=12),
        "fc_10_15": 145 + g.normal(0, 3, len(dias)),
        "pre_exercicio": False, "carga_incerta": False, "base_estrita": True,
        "incerta_limiar_menos5": False, "incerta_limiar_mais5": False, "incerta_queda": False, "incerta_alta": False,
    })
    s["fc_10_15"] += efeito * d["z_rmssd_noite"].reindex(dias).to_numpy()
    return preparar_sessoes(s, d), d


def test_sessao_usa_a_noite_do_mesmo_dia():
    s, d = sessoes_sinteticas()
    assert s["z_rmssd_noite"].iloc[0] == d["z_rmssd_noite"].loc[s["dia"].iloc[0]]
    assert s["horas_desde_despertar"].iloc[0] == 3


def test_sessao_usa_o_treino_do_dia_anterior():
    s, d = sessoes_sinteticas()
    assert s["treino_dia_anterior_30min"].iloc[0] == d["treino_30min"].shift(1).loc[s["dia"].iloc[0]]


def test_modelo_da_esteira_recupera_efeito():
    s, _ = sessoes_sinteticas(efeito=-5.0)
    assert ajustar_esteira(s, "z_rmssd_noite")["efeito"] == pytest.approx(-5, abs=1.5)


def test_pre_exercicio_com_poucos_casos_sai_do_modelo():
    s, _ = sessoes_sinteticas()
    assert not ajustar_esteira(s, "z_rmssd_noite")["usa_pre_exercicio"]
    s.loc[s.index[:1], "pre_exercicio"] = True
    r = ajustar_esteira(s, "z_rmssd_noite")
    assert not r["usa_pre_exercicio"] and np.isfinite(r["ic_sup"])
    s.loc[s.index[:4], "pre_exercicio"] = True
    assert ajustar_esteira(s, "z_rmssd_noite")["usa_pre_exercicio"]


def test_bases_alternativas_mantem_queda_e_alta():
    s, _ = sessoes_sinteticas()
    s.loc[0, "incerta_queda"] = True
    s.loc[1, "incerta_limiar_mais5"] = True
    b = bases_esteira(s)
    assert not b["sem_incerta_limiar_menos5"][0]
    assert not b["sem_incerta_limiar_mais5"][1]
    assert b["sem_incerta_limiar_menos5"][1]


def test_sinal_exploratorio_exige_todas_as_bases():
    s, _ = sessoes_sinteticas(efeito=-5.0)
    r = avaliar_esteira(s)
    assert r[r["id"] == "H7"]["sinal_exploratorio"].all()
    assert r["base"].nunique() == 5


def test_matriz_nao_tem_pares_repetidos_nem_scores():
    m = matriz_exploratoria(preparar_diario(diario_sintetico()))
    zero = m[m["lag"] == 0]
    assert not zero.assign(par=[frozenset(p) for p in zip(zero["x"], zero["y"])])["par"].duplicated().any()
    assert not (m["x"] == m["y"]).any()
    assert not m["x"].str.startswith("sam_").any()
    assert (m["n_efetivo"] > 0).all() and m["q"].between(0, 1).all()
