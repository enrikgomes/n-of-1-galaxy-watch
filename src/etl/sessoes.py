"""Etapa 3 do ETL: monta a tabela de análise das sessões de esteira inclinada.

Regras do projeto aplicadas aqui:
  - A velocidade nunca é inferida da FC. Sinais na FC só marcam a carga como incerta.
  - RPE e carga só vêm do registro manual; sem registro, ficam nulos.
  - O VO2 vem da equação do ACSM, só com velocidade e inclinação registradas.

Uso: python -m src.etl.sessoes
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CODIGO_ESTEIRA_INCLINADA = 15007
CODIGO_CAMINHADA = 1001
DURACAO_MINIMA_MIN = 20
JANELA_PRE_EXERCICIO_MIN = 15
MINUTO_LIMITE_REGRA = 10
BURACO_MAXIMO_S = 60

# Comparação da FC média em 3 min antes e 3 min depois de cada minuto, a partir do minuto 8,
# depois do aquecimento. Sessões têm queda típica perto de zero, por isso 4 bpm já se destaca.
INICIO_MUDANCA_MIN = 8
JANELA_MUDANCA_MIN = 3
AMOSTRAS_MINIMAS_MINUTO = 30
QUEDA_MINIMA_BPM = 4
ALTA_MINIMA_BPM = 8

COLUNAS_CARGA = ["velocidade_kmh", "inclinacao_pct", "rpe_imediato", "rpe_30min"]


def vo2_acsm(velocidade_kmh, inclinacao_pct):
    """VO2 de caminhada (ml/kg/min) pelo ACSM: 3,5 + 0,1·v + 1,8·v·i, com v em m/min e i em fração."""
    v = velocidade_kmh * 1000 / 60
    return 3.5 + 0.1 * v + 1.8 * v * (inclinacao_pct / 100)


def anexar_sequencia(exercicio: pd.DataFrame) -> pd.DataFrame:
    """Usa todos os exercícios, inclusive os de fora da análise, para saber o que veio antes."""
    df = exercicio.sort_values("inicio_utc").copy()
    df["min_desde_anterior"] = (df["inicio_utc"] - df["fim_utc"].shift()).dt.total_seconds() / 60
    df["tipo_anterior"] = df["exercise_type"].shift().astype("Int64")
    return df


def medir_mudancas(fc_minuto: pd.DataFrame) -> pd.DataFrame:
    """Maior queda e maior alta de FC dentro de cada sessão, em bpm, ambas positivas."""
    validos = fc_minuto[fc_minuto["n"] >= AMOSTRAS_MINIMAS_MINUTO]
    linhas = []
    for uuid, grupo in validos.groupby("datauuid"):
        serie = grupo.set_index("minuto")["fc"].sort_index()
        serie = serie.reindex(range(int(serie.index.max()) + 1))
        w = JANELA_MUDANCA_MIN
        antes = serie.rolling(w, min_periods=w - 1).mean().shift(1)
        depois = serie[::-1].rolling(w, min_periods=w - 1).mean()[::-1].shift(-1)
        dif = (depois - antes)[serie.index >= INICIO_MUDANCA_MIN + w].dropna()
        linhas.append({
            "datauuid": uuid,
            "queda_fc_bpm": max(-dif.min(), 0.0) if len(dif) else np.nan,
            "alta_fc_bpm": max(dif.max(), 0.0) if len(dif) else np.nan,
            "minuto_queda": int(dif.idxmin()) if len(dif) else pd.NA,
        })
    return pd.DataFrame(linhas, columns=["datauuid", "queda_fc_bpm", "alta_fc_bpm", "minuto_queda"])


def _base_esteira(exercicio: pd.DataFrame, fc_sessao: pd.DataFrame) -> pd.DataFrame:
    df = anexar_sequencia(exercicio)
    df["duracao_min"] = df["duration"] / 60000
    df = df[df["exercise_type"] == CODIGO_ESTEIRA_INCLINADA].merge(fc_sessao, on="datauuid", how="left")
    return df[df["status_fc"].eq("ok") & (df["duracao_min"] >= DURACAO_MINIMA_MIN)]


def construir_sessoes(
    exercicio: pd.DataFrame,
    fc_sessao: pd.DataFrame,
    fc_minuto: pd.DataFrame,
    carga: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Retorna uma linha por sessão de esteira inclinada com pelo menos 20 min e FC."""
    df = _base_esteira(exercicio, fc_sessao).merge(medir_mudancas(fc_minuto), on="datauuid", how="left")

    # Calendário
    df["dia"] = df["inicio_local"].dt.normalize()
    df["hora_local"] = df["inicio_local"].dt.hour + df["inicio_local"].dt.minute / 60
    df["dia_semana"] = df["inicio_local"].dt.dayofweek
    df["dias_desde_sessao"] = df["inicio_local"].diff().dt.total_seconds() / 86400

    # O que veio antes. Caminhar até o local é rotina, por isso fica em coluna separada.
    perto = df["min_desde_anterior"] <= JANELA_PRE_EXERCICIO_MIN
    df["pre_caminhada"] = perto & df["tipo_anterior"].eq(CODIGO_CAMINHADA).fillna(False)
    df["pre_exercicio"] = perto & ~df["tipo_anterior"].eq(CODIGO_CAMINHADA).fillna(False)
    df["buraco_fc"] = df["maior_buraco_s"] > BURACO_MAXIMO_S

    # Carga e RPE: só do registro manual. Sem registro, permanecem nulos.
    if carga is None:
        for coluna in COLUNAS_CARGA:
            df[coluna] = np.nan
    else:
        df = df.merge(carga[["datauuid", *COLUNAS_CARGA]], on="datauuid", how="left")
    df["vo2_acsm"] = vo2_acsm(df["velocidade_kmh"], df["inclinacao_pct"])
    df["carga_registrada"] = df["velocidade_kmh"].notna() & df["inclinacao_pct"].notna()

    # Marcações de carga incerta. A carga registrada prevalece sobre qualquer sinal na FC.
    sem_registro = ~df["carga_registrada"]
    regra = {
        "incerta_limiar": "min_ate_limiar",
        "incerta_limiar_menos5": "min_ate_limiar_menos5",
        "incerta_limiar_mais5": "min_ate_limiar_mais5",
    }
    for marcacao, coluna in regra.items():
        df[marcacao] = sem_registro & (df[coluna] < MINUTO_LIMITE_REGRA)
    df["incerta_queda"] = sem_registro & (df["queda_fc_bpm"] >= QUEDA_MINIMA_BPM)
    df["incerta_alta"] = sem_registro & (df["alta_fc_bpm"] >= ALTA_MINIMA_BPM)
    df["carga_incerta"] = df["incerta_limiar"] | df["incerta_queda"] | df["incerta_alta"]
    df["base_estrita"] = ~(df["carga_incerta"] | df["pre_exercicio"] | df["buraco_fc"])

    descartar = [
        "exercise_type", "duration", "mean_heart_rate", "max_heart_rate", "min_heart_rate", "count",
        "mean_cadence", "tem_gps", "inicio_utc", "fim_utc", "status_fc",
    ]
    return df.drop(columns=descartar).sort_values("inicio_local", ignore_index=True)


def construir_funil(exercicio: pd.DataFrame, fc_sessao: pd.DataFrame, sessoes: pd.DataFrame) -> pd.DataFrame:
    """Conta as sessões em cada filtro e cada marcação. Só contagens."""
    esteira = exercicio[exercicio["exercise_type"] == CODIGO_ESTEIRA_INCLINADA].merge(fc_sessao, on="datauuid", how="left")
    com_fc = esteira[esteira["status_fc"].eq("ok")]
    etapas = [
        ("Todos os exercícios", len(exercicio)),
        ("Esteira inclinada", len(esteira)),
        ("Com FC", len(com_fc)),
        (f"Com pelo menos {DURACAO_MINIMA_MIN} min", len(sessoes)),
        ("Com carga registrada", int(sessoes["carga_registrada"].sum())),
        ("Marcadas: limiar da zona 4", int(sessoes["incerta_limiar"].sum())),
        ("Marcadas: queda de FC", int(sessoes["incerta_queda"].sum())),
        ("Marcadas: alta de FC", int(sessoes["incerta_alta"].sum())),
        ("Marcadas: carga incerta (qualquer motivo)", int(sessoes["carga_incerta"].sum())),
        ("Marcadas: outro exercício antes", int(sessoes["pre_exercicio"].sum())),
        ("Marcadas: buraco na medição", int(sessoes["buraco_fc"].sum())),
        ("Base estrita (sem nenhuma marcação)", int(sessoes["base_estrita"].sum())),
    ]
    return pd.DataFrame(etapas, columns=["etapa", "sessoes"])


def executar(entrada: Path = Path("data/interim"), saida: Path = Path("data/processed")) -> pd.DataFrame:
    exercicio = pd.read_parquet(entrada / "exercicio.parquet")
    fc_sessao = pd.read_parquet(entrada / "fc_sessao.parquet")
    fc_minuto = pd.read_parquet(entrada / "fc_minuto.parquet")
    sessoes = construir_sessoes(exercicio, fc_sessao, fc_minuto)
    funil = construir_funil(exercicio, fc_sessao, sessoes)
    saida.mkdir(parents=True, exist_ok=True)
    sessoes.to_parquet(saida / "sessoes.parquet", index=False)
    funil.to_parquet(saida / "funil_sessoes.parquet", index=False)
    return funil


if __name__ == "__main__":
    print(executar().to_string(index=False))
