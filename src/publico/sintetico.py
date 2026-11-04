"""Gera dados sintéticos para os gráficos interativos e para demonstrar o método.

Nenhuma função aqui lê dados reais. Todos os parâmetros são valores redondos e inventados,
e os efeitos foram escolhidos para serem fáceis de ver: não são estimativas da pessoa real.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEMENTE = 2024
DIAS = 360
# Efeitos inventados, por 30 min de treino no dia anterior.
EFEITO_TREINO_FC = 1.0
EFEITO_TREINO_RMSSD = -3.0


def _ar1(gerador: np.random.Generator, n: int, desvio: float, phi: float = 0.3) -> np.ndarray:
    """Ruído com autocorrelação, como em séries fisiológicas diárias."""
    choques = gerador.normal(0, desvio * np.sqrt(1 - phi**2), n)
    serie = np.zeros(n)
    serie[0] = gerador.normal(0, desvio)
    for t in range(1, n):
        serie[t] = phi * serie[t - 1] + choques[t]
    return serie


def gerar_diario(dias: int = DIAS, semente: int = SEMENTE) -> pd.DataFrame:
    """Tabela com as mesmas colunas usadas pela análise real."""
    g = np.random.default_rng(semente)
    treino = g.choice([0.0, 0.0, 0.0, 30.0, 45.0, 60.0], dias)
    treino_ontem_30 = np.r_[0.0, treino[:-1]] / 30

    cama = 450 + _ar1(g, dias, 60)
    sono = cama * np.clip(g.normal(0.92, 0.02, dias), 0.8, 0.98)
    d = pd.DataFrame({
        "dia": pd.date_range("2024-01-01", periods=dias, freq="D"),
        "treino_min": treino,
        "min_fc_acima_limiar": treino * g.uniform(0, 0.2, dias),
        "tempo_cama_min": cama,
        "sono_total_min": sono,
        "profundo_min": sono * g.normal(0.17, 0.02, dias),
        "rem_min": sono * g.normal(0.25, 0.03, dias),
        "eficiencia": sono / cama * 100,
        "hora_dormir": 1.0 + _ar1(g, dias, 1.0),
        "rmssd_noite": 60 + _ar1(g, dias, 8) + EFEITO_TREINO_RMSSD * treino_ontem_30,
        "fc_sono_media": 60 + _ar1(g, dias, 3) + EFEITO_TREINO_FC * treino_ontem_30,
        "temperatura_pele": 34 + _ar1(g, dias, 0.2),
        "respiracao": 14 + _ar1(g, dias, 0.4),
        "spo2": 95 + _ar1(g, dias, 1.0),
        "dia_parcial": False,
    })
    d.loc[[0, dias - 1], "dia_parcial"] = True

    # Noites sem registro: blocos, como quando o relógio fica fora do pulso, e dias soltos.
    noturnas = [c for c in d.columns if c not in ("dia", "treino_min", "min_fc_acima_limiar", "dia_parcial")]
    for inicio in g.integers(40, dias - 20, 2):
        d.loc[inicio: inicio + 6, noturnas] = np.nan
    d.loc[g.random(dias) < 0.04, noturnas] = np.nan
    return d


def gerar_sessoes_fc(semente: int = SEMENTE) -> pd.DataFrame:
    """Duas sessões inventadas de 30 min: velocidade constante e troca no minuto 15."""
    g = np.random.default_rng(semente)
    minutos = np.arange(30)
    base = 95 + 45 * (1 - np.exp(-minutos / 3)) + 0.4 * np.clip(minutos - 8, 0, None)
    constante = base + g.normal(0, 0.8, 30)
    troca = base + 9 * (minutos < 15) * (1 - np.exp(-minutos / 3)) + g.normal(0, 0.8, 30)
    return pd.concat([
        pd.DataFrame({"sessao": "Velocidade constante", "minuto": minutos, "fc": constante}),
        pd.DataFrame({"sessao": "Troca de velocidade no minuto 15", "minuto": minutos, "fc": troca}),
    ], ignore_index=True)


def para_publicacao(diario: pd.DataFrame) -> pd.DataFrame:
    """Troca a data por um índice e arredonda."""
    d = diario.drop(columns="dia").round(2)
    d.insert(0, "dia_indice", np.arange(len(d)))
    return d


def reconstruir_diario(publico: pd.DataFrame) -> pd.DataFrame:
    """Recria o calendário que a análise espera, a partir do arquivo publicado."""
    d = publico.drop(columns="dia_indice").copy()
    d.insert(0, "dia", pd.Timestamp("2024-01-01") + pd.to_timedelta(publico["dia_indice"], unit="D"))
    return d
