"""Etapa 4 do ETL: monta a tabela diária de sono, medidas noturnas e atividade.

Cada dia D reúne, nesta ordem no tempo:
    noite que termina em D  ->  treinos de D  ->  noite que termina em D+1

Assim, o sono em D antecede o treino em D, e o treino em D antecede o sono em D+1.
A tabela tem todos os dias do calendário; dias sem dado ficam nulos, para que um
lag de 1 linha seja sempre 1 dia.

Uso: python -m src.etl.diario
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.etl.fc_sessao import FC_MAXIMA, FC_MINIMA, carregar_limiar
from src.etl.leitura import localizar_export

GAP_FRAGMENTOS_MIN = 120
SONO_PRINCIPAL_MIN = 180
COBERTURA_MINIMA = 0.5
BLOCO_VFC_MIN = 0.5
ESTAGIOS = {40001: "acordado_min", 40002: "leve_min", 40003: "profundo_min", 40004: "rem_min"}
GRUPOS_EXERCICIO = {15007: "esteira_inclinada", 15005: "esteira_plana", 15002: "musculacao", 1001: "caminhada"}
SEM_TREINO = {"caminhada"}
PASSOS_COMBINADOS = -2


def consolidar_noites(sono: pd.DataFrame, estagios: pd.DataFrame) -> pd.DataFrame:
    """Une fragmentos separados por até 2 h e escolhe o sono principal de cada dia."""
    s = sono.sort_values("inicio_utc", ignore_index=True)
    s["duracao"] = (s["fim_utc"] - s["inicio_utc"]).dt.total_seconds() / 60
    intervalo = (s["inicio_utc"] - s["fim_utc"].shift()).dt.total_seconds() / 60
    s["bloco"] = (intervalo > GAP_FRAGMENTOS_MIN).cumsum()

    blocos = s.groupby("bloco").agg(
        inicio_utc=("inicio_utc", "first"),
        fim_utc=("fim_utc", "last"),
        inicio_local=("inicio_local", "first"),
        fim_local=("fim_local", "last"),
        tempo_cama_min=("duracao", "sum"),
        fragmentos=("datauuid", "size"),
        latencia_ms=("sleep_latency", "first"),
    )
    maior = s.loc[s.groupby("bloco")["duracao"].idxmax()].set_index("bloco")
    blocos["sam_score_sono"] = maior["sleep_score"]
    blocos["latencia_min"] = blocos.pop("latencia_ms") / 60000
    blocos["dia"] = blocos["fim_local"].dt.normalize()

    # Soma os minutos de cada estágio. Bloco sem estágios fica nulo, não zero.
    e = estagios.merge(s[["datauuid", "bloco"]], left_on="sleep_id", right_on="datauuid", suffixes=("", "_sono"))
    e["minutos"] = (e["fim_utc"] - e["inicio_utc"]).dt.total_seconds() / 60
    somas = e.pivot_table(index="bloco", columns="stage", values="minutos", aggfunc="sum", fill_value=0.0)
    somas = somas.rename(columns=ESTAGIOS).reindex(columns=list(ESTAGIOS.values()))
    blocos = blocos.join(somas)
    blocos["sono_total_min"] = blocos[["leve_min", "profundo_min", "rem_min"]].sum(axis=1, min_count=3)
    blocos["eficiencia"] = blocos["sono_total_min"] / blocos["tempo_cama_min"] * 100

    aptos = blocos[blocos["tempo_cama_min"] >= SONO_PRINCIPAL_MIN]
    principais = aptos.groupby("dia")["tempo_cama_min"].idxmax()
    blocos["principal"] = blocos.index.isin(principais)
    return blocos.reset_index()


def _ms(serie: pd.Series) -> np.ndarray:
    return serie.dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ms]").astype("int64").to_numpy()


def localizar_noite(t_ms: np.ndarray, noites: pd.DataFrame) -> np.ndarray:
    """Para cada instante, retorna o índice da noite que o contém, ou -1 se nenhuma."""
    inicio, fim = _ms(noites["inicio_utc"]), _ms(noites["fim_utc"])
    pos = np.searchsorted(inicio, t_ms, side="right") - 1
    dentro = (pos >= 0) & (t_ms <= fim[np.clip(pos, 0, len(fim) - 1)])
    return np.where(dentro, pos, -1)


def resumir_vfc(amostras: pd.DataFrame, noites: pd.DataFrame) -> pd.DataFrame:
    """Mediana noturna de RMSSD e SDNN. A mediana resiste a blocos de 30 s com artefato."""
    pos = localizar_noite(amostras["t_ms"].to_numpy(), noites)
    a = amostras[pos >= 0].assign(pos=pos[pos >= 0])
    r = a.groupby("pos").agg(rmssd_noite=("rmssd", "median"), sdnn_noite=("sdnn", "median"), n=("rmssd", "size"))
    r["cobertura_vfc"] = (r.pop("n") * BLOCO_VFC_MIN / noites["tempo_cama_min"].to_numpy()[r.index]).clip(upper=1)
    r.loc[r["cobertura_vfc"] < COBERTURA_MINIMA, ["rmssd_noite", "sdnn_noite"]] = np.nan
    return r


def resumir_fc_noturna(amostras: pd.DataFrame, noites: pd.DataFrame) -> pd.DataFrame:
    """FC média e percentil 10 na noite. O percentil 10 aproxima a FC de repouso sem usar score."""
    pos = localizar_noite(amostras["t_ms"].to_numpy(), noites)
    a = amostras[pos >= 0].assign(pos=pos[pos >= 0])
    r = a.groupby("pos")["fc"].agg(fc_sono_media="mean", fc_sono_p10=lambda x: x.quantile(0.10), n="size")
    r["cobertura_fc"] = (r.pop("n") / noites["tempo_cama_min"].to_numpy()[r.index]).clip(upper=1)
    r.loc[r["cobertura_fc"] < COBERTURA_MINIMA, ["fc_sono_media", "fc_sono_p10"]] = np.nan
    return r


def resumir_medida(tabela: pd.DataFrame, coluna: str, nome: str, noites: pd.DataFrame) -> pd.Series:
    """Liga cada medida à noite que contém seu ponto central. Mais de uma vira média."""
    t = tabela.dropna(subset=["inicio_utc", "fim_utc"])
    meio = t["inicio_utc"] + (t["fim_utc"] - t["inicio_utc"]) / 2
    pos = localizar_noite(_ms(meio), noites)
    return t.loc[pos >= 0, coluna].groupby(pos[pos >= 0]).mean().rename(nome)


def resumir_atividade(exercicio: pd.DataFrame, fc_minuto: pd.DataFrame, limiar: float) -> pd.DataFrame:
    """Minutos por tipo de exercício em cada dia, mais os minutos com FC no limiar ou acima."""
    e = exercicio.assign(
        dia=exercicio["inicio_local"].dt.normalize(),
        grupo=exercicio["exercise_type"].map(GRUPOS_EXERCICIO).fillna("outros"),
        minutos=exercicio["duration"] / 60000,
    )
    por_grupo = e.pivot_table(index="dia", columns="grupo", values="minutos", aggfunc="sum", fill_value=0.0)
    grupos = [*GRUPOS_EXERCICIO.values(), "outros"]
    por_grupo = por_grupo.reindex(columns=grupos, fill_value=0.0)
    treino = por_grupo.drop(columns=list(SEM_TREINO)).sum(axis=1).rename("treino_min")
    por_grupo = por_grupo.add_suffix("_min")

    altos = fc_minuto[fc_minuto["fc"] >= limiar].merge(e[["datauuid", "dia"]], on="datauuid")
    min_altos = altos.groupby("dia").size().rename("min_fc_acima_limiar").astype(float)
    return por_grupo.join(treino).join(min_altos).fillna({"min_fc_acima_limiar": 0.0})


def construir_diario(
    sono: pd.DataFrame,
    estagios: pd.DataFrame,
    amostras_vfc: pd.DataFrame,
    amostras_fc: pd.DataFrame,
    medidas: dict[str, tuple[pd.DataFrame, str]],
    atividade: pd.DataFrame,
    passos: pd.DataFrame,
    vitalidade: pd.DataFrame,
    ultimo_dia: pd.Timestamp,
) -> pd.DataFrame:
    blocos = consolidar_noites(sono, estagios)
    noites = blocos[blocos["principal"]].sort_values("inicio_utc", ignore_index=True)

    n = noites.join(resumir_vfc(amostras_vfc, noites)).join(resumir_fc_noturna(amostras_fc, noites))
    for nome, (tabela, coluna) in medidas.items():
        n = n.join(resumir_medida(tabela, coluna, nome, noites))
    # Hora de dormir em horas a partir da meia-noite: 23h vira -1, para não saltar de 23 para 0.
    meia_noite = n["dia"]
    n["hora_dormir"] = (n["inicio_local"] - meia_noite).dt.total_seconds() / 3600
    n["hora_acordar"] = (n["fim_local"] - meia_noite).dt.total_seconds() / 3600
    n = n.rename(columns={"inicio_local": "sono_inicio_local", "fim_local": "sono_fim_local"})
    n = n.drop(columns=["bloco", "principal", "inicio_utc", "fim_utc"]).set_index("dia")

    cochilos = blocos[~blocos["principal"]].groupby("dia")["tempo_cama_min"].sum().rename("cochilo_min")

    vit = vitalidade.set_index("dia")
    composto = pd.DataFrame({
        "sam_score_sono_energia": vit["sleep_score"],
        "sam_fc_repouso": vit["shr_value"],
        "sam_vfc": vit["shrv_value"],
        "sam_score_fc": vit["shr_score"],
        "sam_score_vfc": vit["shrv_score"],
        "sam_score_atividade": vit["activity_score"],
        "sam_score_energia": vit["total_score"],
    })
    p = passos[passos["source_type"] == PASSOS_COMBINADOS].set_index("dia")["count"].rename("passos")

    calendario = pd.date_range(n.index.min(), ultimo_dia, freq="D", name="dia")
    d = pd.DataFrame(index=calendario).join(n).join(cochilos).join(atividade).join(p).join(composto)
    d["tem_sono"] = d["tempo_cama_min"].notna()
    d["cochilo_min"] = d["cochilo_min"].fillna(0.0)
    for coluna in atividade.columns:
        d[coluna] = d[coluna].fillna(0.0)
    # Primeiro e último dia não são completos: o primeiro começa no meio e o último termina no export.
    d["dia_parcial"] = d.index.isin([calendario[0], calendario[-1]])
    return d.reset_index()


def _indice_json(pasta: Path) -> dict[str, Path]:
    return {p.name: p for p in pasta.rglob("*.json")}


def ler_blocos_json(tabela: pd.DataFrame, pasta: Path, chaves: dict[str, str]) -> pd.DataFrame:
    """Lê os JSONs apontados por binning_data em uma tabela: instante + colunas pedidas."""
    indice = _indice_json(pasta)
    linhas = []
    for nome in tabela["binning_data"].dropna():
        caminho = indice.get(nome)
        if caminho is None:
            continue
        for item in json.loads(caminho.read_text(encoding="utf-8")):
            if item.get("start_time") is not None and all(item.get(k) is not None for k in chaves):
                linhas.append((item["start_time"], *[item[k] for k in chaves]))
    return (
        pd.DataFrame(linhas, columns=["t_ms", *chaves.values()], dtype="float64")
        .astype({"t_ms": "int64"})
        .sort_values("t_ms", ignore_index=True)
    )


def executar(entrada: Path = Path("data/interim"), saida: Path = Path("data/processed")) -> pd.DataFrame:
    ler = lambda nome: pd.read_parquet(entrada / f"{nome}.parquet")
    raiz = localizar_export() / "jsons"
    amostras_vfc = ler_blocos_json(ler("vfc"), raiz / "com.samsung.health.hrv", {"rmssd": "rmssd", "sdnn": "sdnn"})
    amostras_fc = ler_blocos_json(
        ler("fc_continua"), raiz / "com.samsung.shealth.tracker.heart_rate", {"heart_rate": "fc"}
    )
    amostras_fc = amostras_fc[amostras_fc["fc"].between(FC_MINIMA, FC_MAXIMA)]
    exercicio = ler("exercicio")
    medidas = {
        "temperatura_pele": (ler("temperatura_pele"), "temperature"),
        "respiracao": (ler("respiracao"), "average"),
        "spo2": (ler("spo2"), "spo2"),
    }
    atividade = resumir_atividade(exercicio, ler("fc_minuto"), carregar_limiar())
    ultimo_dia = ler("sono")["fim_local"].max().normalize()
    diario = construir_diario(
        ler("sono"), ler("estagios_sono"), amostras_vfc, amostras_fc, medidas,
        atividade, ler("passos_dia"), ler("vitalidade"), ultimo_dia,
    )
    saida.mkdir(parents=True, exist_ok=True)
    diario.to_parquet(saida / "diario.parquet", index=False)
    # Só contagens na saída.
    return diario.notna().sum().rename("dias_com_dado").to_frame().assign(dias=len(diario))


if __name__ == "__main__":
    print(executar().to_string())
