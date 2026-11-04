"""Cálculos da demonstração interativa. Só usam public_data/sintetico_diario.csv."""
from __future__ import annotations

import pandas as pd

JANELA_BASE = 28
MINIMO_BASE = 14
ROTULOS_TREINO = {0.0: "Sem treino", 30.0: "30 min", 45.0: "45 min", 60.0: "60 min"}


def zscore_movel(serie: pd.Series) -> pd.Series:
    """Desvio em relação aos 28 dias anteriores, como na análise real."""
    anterior = serie.shift(1).rolling(JANELA_BASE, min_periods=MINIMO_BASE)
    return (serie - anterior.mean()) / anterior.std()


def resumo_por_atraso(diario: pd.DataFrame, atraso: int) -> tuple[pd.DataFrame, float]:
    """Média da FC noturna por duração do treino feito há `atraso` dias, e a correlação."""
    z = zscore_movel(diario["fc_sono_media"])
    treino = diario["treino_min"].shift(atraso)
    grupos = z.groupby(treino).agg(["count", "mean", "sem"]).reindex(list(ROTULOS_TREINO))
    tabela = pd.DataFrame({
        "treino": list(ROTULOS_TREINO.values()),
        "n": grupos["count"].astype(int).to_numpy(),
        "media": grupos["mean"].to_numpy(),
        "ic_inf": (grupos["mean"] - 1.96 * grupos["sem"]).to_numpy(),
        "ic_sup": (grupos["mean"] + 1.96 * grupos["sem"]).to_numpy(),
    })
    return tabela, float(z.corr(treino, method="spearman"))
