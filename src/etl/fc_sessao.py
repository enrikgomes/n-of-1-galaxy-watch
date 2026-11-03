"""Etapa 2 do ETL: transforma os JSONs de FC em indicadores por sessão.

Cada sessão de exercicio.parquet aponta, pelo datauuid, para um arquivo
<datauuid>.com.samsung.health.exercise.live_data.json com uma lista de medições.

O limiar de zona vem de data/config_local.json, fora do git, porque revela um
dado pessoal de FC: {"limiar_zona_4_bpm": <valor>}

Uso: python -m src.etl.fc_sessao
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.etl.leitura import localizar_export

SUFIXO_ARQUIVO = ".com.samsung.health.exercise.live_data.json"
FC_MINIMA, FC_MAXIMA = 30, 230
MINIMO_AMOSTRAS = 5
COBERTURA_MINIMA = 0.5
# Nome da coluna: (minuto inicial, minuto final), com o final fora da janela.
JANELAS = {
    "fc_05_10": (5, 10),
    "fc_10_15": (10, 15),
    "fc_15_20": (15, 20),
    "fc_20_25": (20, 25),
    "fc_25_30": (25, 30),
    "fc_minuto_10": (9, 11),
}
INICIO_DERIVA_MIN = 10
DURACAO_MINIMA_DERIVA_MIN = 10
JANELA_LIMIAR = "30s"
MINIMO_AMOSTRAS_LIMIAR = 15
DELTA_SENSIBILIDADE_BPM = 5
# O CSV trunca a média para inteiro (até 1 bpm) e os tempos repetidos a alteram um pouco.
TOLERANCIA_MEDIA_BPM = 1.5


def encontrar_arquivos(raiz_export: Path) -> dict[str, Path]:
    """Mapeia datauuid -> arquivo. O sufixo exato exclui os arquivos *_internal."""
    pasta = raiz_export / "jsons" / "com.samsung.shealth.exercise"
    return {p.name.removesuffix(SUFIXO_ARQUIVO): p for p in pasta.rglob(f"*{SUFIXO_ARQUIVO}")}


def ler_amostras(caminho: Path) -> pd.DataFrame:
    """Lê um JSON e retorna uma medição válida por instante, em ordem de tempo."""
    itens = json.loads(caminho.read_text(encoding="utf-8"))
    # Alguns itens só trazem calorias; precisam de horário e de FC para valer.
    pares = [
        (i["start_time"], i["heart_rate"])
        for i in itens
        if i.get("heart_rate") is not None and i.get("start_time") is not None
    ]
    df = pd.DataFrame(pares, columns=["t_ms", "fc"], dtype="float64")
    df = df[df["fc"].between(FC_MINIMA, FC_MAXIMA)]
    # O export repete alguns instantes; vira uma medição só, com a média.
    return df.groupby("t_ms", as_index=False)["fc"].mean().sort_values("t_ms", ignore_index=True)


def _segundos_com_dado(minutos: pd.Series) -> int:
    return int(np.floor(minutos * 60).nunique())


def _media_janela(a: pd.DataFrame, inicio: float, fim: float) -> float:
    """Média da janela, ou nulo se menos de metade dos segundos tiver dado."""
    trecho = a[(a["minuto"] >= inicio) & (a["minuto"] < fim)]
    if _segundos_com_dado(trecho["minuto"]) < COBERTURA_MINIMA * (fim - inicio) * 60:
        return np.nan
    return float(trecho["fc"].mean())


def calcular_deriva(a: pd.DataFrame) -> float:
    """Inclinação da FC (bpm/min) do minuto 10 ao fim da sessão, por mínimos quadrados."""
    trecho = a[a["minuto"] >= INICIO_DERIVA_MIN]
    if trecho.empty:
        return np.nan
    span = trecho["minuto"].max() - INICIO_DERIVA_MIN
    if span < DURACAO_MINIMA_DERIVA_MIN or _segundos_com_dado(trecho["minuto"]) < COBERTURA_MINIMA * span * 60:
        return np.nan
    return float(np.polyfit(trecho["minuto"], trecho["fc"], 1)[0])


def minutos_ate_limiar(a: pd.DataFrame, limiar: float) -> float:
    """Primeiro minuto em que a mediana dos 30 s anteriores atinge o limiar.

    A mediana evita que um salto isolado do sensor conte como chegada à zona.
    Nulo significa que a sessão não atingiu o limiar.
    """
    serie = pd.Series(a["fc"].to_numpy(), index=pd.to_timedelta(a["minuto"], unit="min"))
    mediana = serie.rolling(JANELA_LIMIAR, min_periods=MINIMO_AMOSTRAS_LIMIAR).median()
    acima = mediana[mediana >= limiar]
    return acima.index[0].total_seconds() / 60 if len(acima) else np.nan


def resumir_sessao(amostras: pd.DataFrame, inicio_ms: float, fim_ms: float, limiar: float) -> dict:
    """Calcula os indicadores de uma sessão a partir das medições."""
    duracao_min = (fim_ms - inicio_ms) / 60000
    a = amostras.assign(minuto=(amostras["t_ms"] - inicio_ms) / 60000)
    a = a[a["minuto"].between(0, duracao_min)]
    if len(a) < MINIMO_AMOSTRAS:
        return {"status_fc": "poucas_amostras", "n_amostras": len(a)}
    return {
        "status_fc": "ok",
        "n_amostras": len(a),
        "cobertura": min(_segundos_com_dado(a["minuto"]) / (duracao_min * 60), 1.0),
        "maior_buraco_s": float(a["minuto"].diff().max() * 60) if len(a) > 1 else np.nan,
        "fc_media": float(a["fc"].mean()),
        "fc_maxima": float(a["fc"].max()),
        "fc_minima": float(a["fc"].min()),
        **{nome: _media_janela(a, *janela) for nome, janela in JANELAS.items()},
        "deriva_bpm_min": calcular_deriva(a),
        "min_ate_limiar": minutos_ate_limiar(a, limiar),
        "min_ate_limiar_menos5": minutos_ate_limiar(a, limiar - DELTA_SENSIBILIDADE_BPM),
        "min_ate_limiar_mais5": minutos_ate_limiar(a, limiar + DELTA_SENSIBILIDADE_BPM),
    }


def fc_por_minuto(datauuid: str, amostras: pd.DataFrame, inicio_ms: float) -> pd.DataFrame:
    """Média por minuto, para gráficos e análises de perfil da sessão."""
    minuto = np.floor((amostras["t_ms"] - inicio_ms) / 60000).astype(int)
    saida = amostras.groupby(minuto)["fc"].agg(fc="mean", n="count").reset_index(names="minuto")
    return saida[saida["minuto"] >= 0].assign(datauuid=datauuid)


def carregar_limiar(caminho: Path = Path("data/config_local.json")) -> float:
    if not caminho.exists():
        raise FileNotFoundError(f'Crie {caminho} com o conteúdo {{"limiar_zona_4_bpm": <valor>}}')
    return float(json.loads(caminho.read_text(encoding="utf-8"))["limiar_zona_4_bpm"])


def validar_contra_csv(exercicio: pd.DataFrame, sessoes: pd.DataFrame) -> dict[str, int]:
    """Compara os JSONs com os resumos do CSV, que têm outra origem no export."""
    u = exercicio.merge(sessoes, on="datauuid")
    c = u[u["status_fc"].eq("ok") & u["mean_heart_rate"].notna()]
    return {
        "sessoes_comparadas": len(c),
        "maxima_divergente": int((c["fc_maxima"] - c["max_heart_rate"]).abs().gt(1).sum()),
        "minima_divergente": int((c["fc_minima"] - c["min_heart_rate"]).abs().gt(1).sum()),
        "media_divergente": int((c["fc_media"] - c["mean_heart_rate"]).abs().gt(TOLERANCIA_MEDIA_BPM).sum()),
        "ok_sem_media_no_csv": int((u["status_fc"].eq("ok") & u["mean_heart_rate"].isna()).sum()),
    }


def processar(exercicio: pd.DataFrame, arquivos: dict[str, Path], limiar: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna uma linha por sessão, inclusive sem FC, e a tabela por minuto."""
    sessoes, minutos = [], []
    for s in exercicio.itertuples():
        caminho = arquivos.get(s.datauuid)
        if caminho is None:
            sessoes.append({"datauuid": s.datauuid, "status_fc": "sem_arquivo", "n_amostras": 0})
            continue
        amostras = ler_amostras(caminho)
        if amostras.empty:
            sessoes.append({"datauuid": s.datauuid, "status_fc": "sem_fc", "n_amostras": 0})
            continue
        inicio_ms = s.inicio_utc.timestamp() * 1000
        sessoes.append({"datauuid": s.datauuid, **resumir_sessao(amostras, inicio_ms, s.fim_utc.timestamp() * 1000, limiar)})
        minutos.append(fc_por_minuto(s.datauuid, amostras, inicio_ms))
    por_minuto = pd.concat(minutos, ignore_index=True) if minutos else pd.DataFrame(columns=["minuto", "fc", "n", "datauuid"])
    return pd.DataFrame(sessoes), por_minuto


def executar(pasta: Path = Path("data/interim")) -> None:
    exercicio = pd.read_parquet(pasta / "exercicio.parquet")
    sessoes, por_minuto = processar(exercicio, encontrar_arquivos(localizar_export()), carregar_limiar())
    sessoes.to_parquet(pasta / "fc_sessao.parquet", index=False)
    por_minuto.to_parquet(pasta / "fc_minuto.parquet", index=False)
    # Só contagens na saída, nenhum valor de saúde.
    print(pd.crosstab(exercicio.merge(sessoes, on="datauuid")["exercise_type"], sessoes["status_fc"]).to_string())
    print("\nValidação contra o CSV:", validar_contra_csv(exercicio, sessoes))
    print("Linhas por minuto:", len(por_minuto))


if __name__ == "__main__":
    executar()
