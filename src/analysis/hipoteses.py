"""Etapa 5: testa as hipóteses aprovadas em docs/HIPOTESES.md.

O método e os critérios seguem esse documento, escrito antes dos resultados.

Uso: python -m src.analysis.hipoteses
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.multitest import multipletests

JANELA_BASE = 28
MINIMO_BASE = 14
LAGS_NEWEY_WEST = 7
BLOCO_BOOTSTRAP = 7
SORTEIOS_BOOTSTRAP = 2000
SEMENTE = 20261103
Q_MAXIMO = 0.10
MINIMO_CASOS_CONTROLE = 2
Z_COLUNAS = ["rmssd_noite", "fc_sono_media", "sono_total_min", "hora_dormir"]
Z_MATRIZ = [
    "tempo_cama_min", "sono_total_min", "profundo_min", "rem_min", "eficiencia", "hora_dormir",
    "rmssd_noite", "fc_sono_media", "temperatura_pele", "respiracao", "spo2",
]


@dataclass(frozen=True)
class HipoteseDiaria:
    id: str
    y: str
    x: str
    lag_x: int
    sinal_esperado: int  # 0 = sem expectativa
    alternativa: str | None = None


HIPOTESES_DIARIAS = [
    HipoteseDiaria("H1", "z_rmssd_noite", "treino_30min", 1, -1, "limiar_30min"),
    HipoteseDiaria("H2", "z_fc_sono_media", "treino_30min", 1, 1, "limiar_30min"),
    HipoteseDiaria("H3", "z_sono_total_min", "treino_30min", 1, 0, "limiar_30min"),
    HipoteseDiaria("H4", "z_rmssd_noite", "z_sono_total_min", 1, 1),
    HipoteseDiaria("H5", "z_rmssd_noite", "z_hora_dormir", 0, -1),
]

# id: (coluna explicativa, sinal esperado)
HIPOTESES_ESTEIRA = {
    "H6": ("z_sono_total_min", -1),
    "H7": ("z_rmssd_noite", -1),
    "H8": ("z_fc_sono_media", 1),
    "H9": ("horas_desde_despertar", 0),
    "H10": ("treino_dia_anterior_30min", 1),
}


def zscore_movel(serie: pd.Series) -> pd.Series:
    """Desvio em relação aos 28 dias anteriores, sem incluir o próprio dia."""
    anterior = serie.shift(1).rolling(JANELA_BASE, min_periods=MINIMO_BASE)
    return (serie - anterior.mean()) / anterior.std()


def preparar_diario(diario: pd.DataFrame) -> pd.DataFrame:
    """Indexa por dia, confere o calendário e cria as variáveis das hipóteses."""
    d = diario.set_index("dia").sort_index()
    if not d.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all():
        raise ValueError("O calendário tem buracos; os lags ficariam errados.")
    for coluna in sorted(set(Z_COLUNAS) | set(Z_MATRIZ)):
        d[f"z_{coluna}"] = zscore_movel(d[coluna])
    # Dias parciais não têm a atividade completa.
    d["treino_30min"] = (d["treino_min"] / 30).where(~d["dia_parcial"])
    d["limiar_30min"] = (d["min_fc_acima_limiar"] / 30).where(~d["dia_parcial"])
    return d


def alinhar(d: pd.DataFrame, y: str, x: str, lag_x: int) -> pd.DataFrame:
    """Monta y(t), x(t-lag) e y(t-1) no calendário, mantendo os dias nulos."""
    return pd.DataFrame({"y": d[y], "x": d[x].shift(lag_x), "y_ant": d[y].shift(1)})


def ajustar_newey_west(dados: pd.DataFrame, controle: bool = True):
    colunas = ["x", "y_ant"] if controle else ["x"]
    c = dados[["y", *colunas]].dropna()
    return (
        sm.OLS(c["y"], sm.add_constant(c[colunas]))
        .fit(cov_type="HAC", cov_kwds={"maxlags": LAGS_NEWEY_WEST, "use_correction": True}),
        len(c),
    )


def bootstrap_blocos(dados: pd.DataFrame, sorteios: int = SORTEIOS_BOOTSTRAP, semente: int = SEMENTE) -> tuple[float, float]:
    """Intervalo de 95% de b, sorteando blocos de 7 dias seguidos do calendário."""
    gerador = np.random.default_rng(semente)
    matriz = dados[["y", "x", "y_ant"]].to_numpy(dtype=float)
    total = len(matriz)
    blocos = int(np.ceil(total / BLOCO_BOOTSTRAP))
    coeficientes = []
    for _ in range(sorteios):
        inicios = gerador.integers(0, total - BLOCO_BOOTSTRAP + 1, blocos)
        indices = (inicios[:, None] + np.arange(BLOCO_BOOTSTRAP)).ravel()[:total]
        amostra = matriz[indices]
        amostra = amostra[~np.isnan(amostra).any(axis=1)]
        if len(amostra) < 10:
            continue
        X = np.column_stack([np.ones(len(amostra)), amostra[:, 1], amostra[:, 2]])
        coeficientes.append(np.linalg.lstsq(X, amostra[:, 0], rcond=None)[0][1])
    return tuple(np.percentile(coeficientes, [2.5, 97.5]))


def avaliar_diarias(d: pd.DataFrame, sorteios: int = SORTEIOS_BOOTSTRAP) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica os critérios às hipóteses diárias e calcula a sensibilidade."""
    linhas, sensibilidade = [], []
    for h in HIPOTESES_DIARIAS:
        dados = alinhar(d, h.y, h.x, h.lag_x)
        modelo, n = ajustar_newey_west(dados)
        sem_controle, _ = ajustar_newey_west(dados, controle=False)
        c = dados[["x", "y"]].dropna()
        ic = modelo.conf_int().loc["x"]
        boot = bootstrap_blocos(dados, sorteios)
        linhas.append({
            "id": h.id, "resposta": h.y, "explicativa": h.x, "sinal_esperado": h.sinal_esperado, "n": n,
            "efeito": modelo.params["x"], "ic_inf": ic[0], "ic_sup": ic[1], "p": modelo.pvalues["x"],
            "boot_inf": boot[0], "boot_sup": boot[1],
            "efeito_sem_controle": sem_controle.params["x"], "spearman": stats.spearmanr(c["x"], c["y"]).statistic,
        })
        if h.alternativa:
            alt, n_alt = ajustar_newey_west(alinhar(d, h.y, h.alternativa, h.lag_x))
            ic_alt = alt.conf_int().loc["x"]
            sensibilidade.append({
                "id": h.id, "explicativa": h.alternativa, "n": n_alt, "efeito": alt.params["x"],
                "ic_inf": ic_alt[0], "ic_sup": ic_alt[1], "p": alt.pvalues["x"],
            })
    r = pd.DataFrame(linhas)
    r["q"] = multipletests(r["p"], method="fdr_bh")[1]
    r["boot_sem_zero"] = (r["boot_inf"] > 0) | (r["boot_sup"] < 0)
    r["mesmo_sinal"] = (np.sign(r["efeito"]) == np.sign(r["efeito_sem_controle"])) & (np.sign(r["efeito"]) == np.sign(r["spearman"]))
    r["sustentada"] = (r["q"] < Q_MAXIMO) & r["boot_sem_zero"] & r["mesmo_sinal"]
    return r, pd.DataFrame(sensibilidade)


def avaliar_placebo(d: pd.DataFrame) -> pd.DataFrame:
    """Checagem posterior aos resultados: o treino de D vem depois da noite que termina em D.

    Portanto, não deveria explicá-la. Um efeito aqui indicaria confusão de fatores.
    """
    linhas = []
    for id_h, y in (("H1", "z_rmssd_noite"), ("H2", "z_fc_sono_media")):
        modelo, n = ajustar_newey_west(alinhar(d, y, "treino_30min", 0))
        ic = modelo.conf_int().loc["x"]
        linhas.append({"id": id_h, "n": n, "efeito": modelo.params["x"], "ic_inf": ic[0], "ic_sup": ic[1], "p": modelo.pvalues["x"]})
    return pd.DataFrame(linhas)


def preparar_sessoes(sessoes: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """Liga cada sessão à noite anterior e ao treino do dia anterior."""
    colunas = [f"z_{c}" for c in ("sono_total_min", "rmssd_noite", "fc_sono_media")]
    s = sessoes.sort_values("inicio_local", ignore_index=True).merge(
        d[[*colunas, "sono_fim_local"]].reset_index(), on="dia", how="left", validate="one_to_one"
    )
    s["treino_dia_anterior_30min"] = s["dia"].map(d["treino_30min"].shift(1))
    s["horas_desde_despertar"] = (s["inicio_local"] - s["sono_fim_local"]).dt.total_seconds() / 3600
    s["ordem"] = np.arange(len(s), dtype=float)
    return s


def bases_esteira(s: pd.DataFrame) -> dict[str, pd.Series]:
    """As bases definidas nos critérios. Queda e alta valem em todas as versões do limiar."""
    outros = s["incerta_queda"] | s["incerta_alta"]
    return {
        "todas": pd.Series(True, index=s.index),
        "sem_incerta": ~s["carga_incerta"],
        "base_estrita": s["base_estrita"],
        "sem_incerta_limiar_menos5": ~(s["incerta_limiar_menos5"] | outros),
        "sem_incerta_limiar_mais5": ~(s["incerta_limiar_mais5"] | outros),
    }


def ajustar_esteira(s: pd.DataFrame, x: str) -> dict:
    """fc_10_15 ~ x + ordem + pre_exercicio, com erros HC3."""
    c = s[["fc_10_15", x, "ordem", "pre_exercicio"]].dropna().astype(float)
    colunas = [x, "ordem"]
    # Com 0 ou 1 caso, pre_exercicio é constante ou isola uma única sessão, e o HC3 fica indefinido.
    usa_pre = c["pre_exercicio"].sum() >= MINIMO_CASOS_CONTROLE
    if usa_pre:
        colunas.append("pre_exercicio")
    modelo = sm.OLS(c["fc_10_15"], sm.add_constant(c[colunas])).fit(cov_type="HC3", use_t=True)
    ic = modelo.conf_int().loc[x]
    return {
        "n": len(c), "efeito": modelo.params[x], "ic_inf": ic[0], "ic_sup": ic[1], "p": modelo.pvalues[x],
        "usa_pre_exercicio": usa_pre, "spearman": stats.spearmanr(c[x], c["fc_10_15"]).statistic,
    }


def avaliar_esteira(s: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for id_h, (x, sinal) in HIPOTESES_ESTEIRA.items():
        for base, mascara in bases_esteira(s).items():
            linhas.append({"id": id_h, "explicativa": x, "sinal_esperado": sinal, "base": base, **ajustar_esteira(s[mascara], x)})
    r = pd.DataFrame(linhas)
    r["ic_sem_zero"] = (r["ic_inf"] > 0) | (r["ic_sup"] < 0)
    # Sinal exploratório: intervalo sem o zero e mesmo sinal em todas as bases.
    resumo = r.groupby("id").agg(todas_sem_zero=("ic_sem_zero", "all"), sinais=("efeito", lambda e: np.sign(e).nunique()))
    r["sinal_exploratorio"] = r["id"].map(resumo["todas_sem_zero"] & resumo["sinais"].eq(1))
    return r


def _autocorrelacao(serie: pd.Series) -> float:
    pares = pd.DataFrame({"a": serie, "b": serie.shift(1)}).dropna()
    return float(pares["a"].corr(pares["b"])) if len(pares) > 3 else 0.0


def matriz_exploratoria(d: pd.DataFrame, lags: tuple[int, ...] = (0, 1, 2)) -> pd.DataFrame:
    """Correlação de Spearman entre pares, com lags. Só gera perguntas; não confirma achados."""
    series = {c: d[f"z_{c}"] for c in Z_MATRIZ}
    series["treino_min"] = d["treino_30min"] * 30
    nomes = list(series)
    r1 = {n: _autocorrelacao(s) for n, s in series.items()}
    linhas = []
    for lag in lags:
        for i, x in enumerate(nomes):
            for j, y in enumerate(nomes):
                if x == y or (lag == 0 and j <= i):
                    continue
                c = pd.DataFrame({"x": series[x].shift(lag), "y": series[y]}).dropna()
                if len(c) < 10:
                    continue
                rho = stats.spearmanr(c["x"], c["y"]).statistic
                # Amostra efetiva menor, para compensar a autocorrelação das duas séries.
                produto = r1[x] * r1[y]
                n_ef = max(len(c) * (1 - produto) / (1 + produto), 3.0)
                t = rho * np.sqrt((n_ef - 2) / max(1 - rho**2, 1e-12))
                linhas.append({
                    "x": x, "y": y, "lag": lag, "rho": rho, "n": len(c), "n_efetivo": n_ef,
                    "p": 2 * stats.t.sf(abs(t), n_ef - 2),
                })
    m = pd.DataFrame(linhas)
    m["q"] = multipletests(m["p"], method="fdr_bh")[1]
    return m


def executar(pasta: Path = Path("data/processed")) -> dict[str, pd.DataFrame]:
    d = preparar_diario(pd.read_parquet(pasta / "diario.parquet"))
    diarias, sensibilidade = avaliar_diarias(d)
    esteira = avaliar_esteira(preparar_sessoes(pd.read_parquet(pasta / "sessoes.parquet"), d))
    matriz = matriz_exploratoria(d)
    saida = {
        "res_diarias": diarias,
        "res_sensibilidade": sensibilidade,
        "res_placebo": avaliar_placebo(d),
        "res_esteira": esteira,
        "res_exploratoria": matriz,
    }
    for nome, tabela in saida.items():
        tabela.to_parquet(pasta / f"{nome}.parquet", index=False)
    return saida


if __name__ == "__main__":
    pd.set_option("display.width", 220, "display.max_columns", None)
    r = executar()
    print(r["res_diarias"].round(3).to_string(index=False))
    print("\nSensibilidade\n", r["res_sensibilidade"].round(3).to_string(index=False))
    print("\nPlacebo\n", r["res_placebo"].round(3).to_string(index=False))
    print("\nEsteira\n", r["res_esteira"].round(3).to_string(index=False))
    m = r["res_exploratoria"]
    print("\nExploratória: pares:", len(m), "| q<0,10:", int((m["q"] < Q_MAXIMO).sum()))
    print(m[m["q"] < Q_MAXIMO].sort_values("q").head(30).round(3).to_string(index=False))
