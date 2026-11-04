"""Etapa 6: gera public_data/, a única pasta de dados que vai para o GitHub e para o app.

Arquivos real_*: agregados dos dados reais, sem datas, identificadores ou valores absolutos de saúde.
Arquivos sintetico_*: dados inventados, gerados sem ler os dados reais.

A verificação no fim bloqueia a publicação se encontrar algo fora dessas regras.

Uso: python -m src.publico.gerar
"""
from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis.hipoteses import preparar_diario
from src.etl.leitura import ler_bruto, ler_tabela, limpar_nomes, localizar_arquivo, localizar_export
from src.etl.tabelas import TABELAS
from src.publico.sintetico import gerar_diario, gerar_sessoes_fc, para_publicacao

PASTA_PUBLICA = Path("public_data")
MINIMO_N = 5
FAIXAS_TREINO = [-0.1, 0, 30, 60, np.inf]
ROTULOS_TREINO = ["Sem treino", "Até 30 min", "31 a 60 min", "Mais de 60 min"]
FORMATO_DATA = "%Y-%m-%d %H:%M:%S.%f"

PERGUNTAS_DIARIAS = {
    "H1": ("Mais treino reduz a VFC da noite seguinte?", "dp por 30 min de treino"),
    "H2": ("Mais treino aumenta a FC da noite seguinte?", "dp por 30 min de treino"),
    "H3": ("Mais treino muda o tempo dormido na noite seguinte?", "dp por 30 min de treino"),
    "H4": ("Dormir mais aumenta a VFC da noite seguinte?", "dp por 1 dp de sono"),
    "H5": ("Dormir mais tarde reduz a VFC da mesma noite?", "dp por 1 dp de horário"),
}
PERGUNTAS_ESTEIRA = {
    "H6": ("Dormir menos aumenta a FC na esteira?", "bpm por 1 dp de sono"),
    "H7": ("VFC mais baixa na noite anterior aumenta a FC na esteira?", "bpm por 1 dp de VFC"),
    "H8": ("FC mais alta na noite anterior aumenta a FC na esteira?", "bpm por 1 dp de FC noturna"),
    "H9": ("O tempo desde o despertar muda a FC na esteira?", "bpm por hora"),
    "H10": ("Mais treino no dia anterior aumenta a FC na esteira?", "bpm por 30 min de treino"),
}

# Regras da verificação
PADRAO_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
PADRAO_DATA = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")
PADRAO_EXPORT = re.compile(r"samsunghealth_", re.I)
COLUNAS_PROIBIDAS = {
    "datauuid", "dia", "inicio_local", "fim_local", "inicio_utc", "fim_utc", "sono_inicio_local", "sono_fim_local",
    "deviceuuid", "dispositivo", "comment", "location_data", "observacao",
}
COLUNAS_ABSOLUTAS = {
    "fc_media", "fc_maxima", "fc_minima", "fc_05_10", "fc_10_15", "fc_15_20", "fc_20_25", "fc_25_30", "fc_minuto_10",
    "rmssd_noite", "sdnn_noite", "fc_sono_media", "fc_sono_p10", "temperatura_pele", "respiracao", "spo2", "fc",
    "tempo_cama_min", "sono_total_min", "profundo_min", "rem_min", "eficiencia", "hora_dormir", "hora_acordar",
    "treino_min", "passos", "min_ate_limiar", "limiar_zona_4_bpm",
}


def _veredito(linha: pd.Series) -> str:
    if not linha["sustentada"]:
        return "Não sustentada"
    if linha["sinal_esperado"] != 0 and np.sign(linha["efeito"]) != linha["sinal_esperado"]:
        return "Cumpre os critérios, com sinal contrário"
    return "Sustentada"


def tabela_diarias(res: pd.DataFrame) -> pd.DataFrame:
    t = res.copy()
    t["pergunta"] = t["id"].map(lambda i: PERGUNTAS_DIARIAS[i][0])
    t["unidade"] = t["id"].map(lambda i: PERGUNTAS_DIARIAS[i][1])
    t["veredito"] = t.apply(_veredito, axis=1)
    colunas = ["id", "pergunta", "unidade", "sinal_esperado", "n", "efeito", "ic_inf", "ic_sup", "q", "boot_inf", "boot_sup", "efeito_sem_controle", "spearman", "veredito"]
    return t[colunas].round(3)


def tabela_esteira(res: pd.DataFrame) -> pd.DataFrame:
    t = res.copy()
    t["pergunta"] = t["id"].map(lambda i: PERGUNTAS_ESTEIRA[i][0])
    t["unidade"] = t["id"].map(lambda i: PERGUNTAS_ESTEIRA[i][1])
    return t[["id", "pergunta", "unidade", "sinal_esperado", "base", "n", "efeito", "ic_inf", "ic_sup", "sinal_exploratorio"]].round(2)


def dose_resposta(d: pd.DataFrame) -> pd.DataFrame:
    """Média da noite seguinte por faixa de treino. Descritivo: sem controles nem ajuste por autocorrelação."""
    faixa = pd.cut(d["treino_30min"].shift(1) * 30, FAIXAS_TREINO, labels=ROTULOS_TREINO)
    linhas = []
    for coluna, resposta in (("z_fc_sono_media", "FC da noite seguinte"), ("z_rmssd_noite", "VFC da noite seguinte")):
        grupos = d[coluna].groupby(faixa, observed=False).agg(["count", "mean", "sem"])
        for rotulo, g in grupos.iterrows():
            if g["count"] >= MINIMO_N:
                linhas.append({
                    "resposta": resposta, "faixa_treino": rotulo, "n": int(g["count"]), "media_dp": g["mean"],
                    "ic_inf": g["mean"] - 1.96 * g["sem"], "ic_sup": g["mean"] + 1.96 * g["sem"],
                })
    return pd.DataFrame(linhas).round(3)


def perfil_sessao(fc_minuto: pd.DataFrame, sessoes: pd.DataFrame) -> pd.DataFrame:
    """Variação da FC em relação aos minutos 9 e 10 de cada sessão. Não revela o valor absoluto."""
    m = fc_minuto[fc_minuto["n"] >= 30].merge(sessoes[["datauuid", "carga_incerta"]], on="datauuid")
    ref = m[m["minuto"].isin([9, 10])].groupby("datauuid")["fc"].mean().rename("ref")
    m = m.merge(ref, on="datauuid")
    m["variacao"] = m["fc"] - m["ref"]
    partes = []
    for base, recorte in (("Todas as sessões", m), ("Sem carga incerta", m[~m["carga_incerta"]])):
        g = recorte.groupby("minuto")["variacao"]
        t = g.agg(n="count", mediana="median", p25=lambda x: x.quantile(0.25), p75=lambda x: x.quantile(0.75)).reset_index()
        partes.append(t.assign(base=base))
    p = pd.concat(partes, ignore_index=True)
    return p[(p["n"] >= MINIMO_N) & (p["minuto"] <= 30)].round(2)[["base", "minuto", "n", "mediana", "p25", "p75"]]


def tabela_leitura(raiz: Path) -> pd.DataFrame:
    linhas = [asdict(ler_tabela(raiz, nome)[1]) for nome in TABELAS]
    return pd.DataFrame(linhas).drop(columns="ids_repetidos")


def comparacao_leitura(raiz: Path) -> pd.DataFrame:
    """Quantas linhas cada leitura acerta. Mostra o deslocamento sem revelar nenhum valor."""
    nome = "com.samsung.shealth.exercise"
    caminho = localizar_arquivo(raiz, nome)
    ingenua = limpar_nomes(pd.read_csv(caminho, encoding="utf-8-sig", skiprows=1, low_memory=False))
    correta = limpar_nomes(ler_bruto(caminho, nome))
    validos = set(correta["exercise_type"].dropna().unique())

    def contar(df: pd.DataFrame) -> dict:
        return {
            "start_time_valido": int(pd.to_datetime(df["start_time"], format=FORMATO_DATA, errors="coerce").notna().sum()),
            "exercise_type_valido": int(pd.to_numeric(df["exercise_type"], errors="coerce").isin(validos).sum()),
            "total": len(df),
        }

    return pd.DataFrame([{"leitura": "Padrão do pandas", **contar(ingenua)}, {"leitura": "Leitor do projeto", **contar(correta)}])


def validacao_alinhamento(d: pd.DataFrame) -> pd.DataFrame:
    """Correlação entre valores da Samsung e os calculados no projeto, com deslocamento em dias."""
    linhas = []
    for rotulo, a, b in (
        ("FC de repouso da Samsung x FC média na noite", "sam_fc_repouso", "fc_sono_media"),
        ("VFC da Samsung x RMSSD noturno", "sam_vfc", "rmssd_noite"),
    ):
        for desloc in (-1, 0, 1):
            linhas.append({"comparacao": rotulo, "deslocamento_dias": desloc, "r": d[a].corr(d[b].shift(desloc))})
    return pd.DataFrame(linhas).round(3)


def tabelas_reais() -> dict[str, pd.DataFrame]:
    p = Path("data/processed")
    i = Path("data/interim")
    ler = lambda pasta, nome: pd.read_parquet(pasta / f"{nome}.parquet")
    d = preparar_diario(ler(p, "diario"))
    raiz = localizar_export()
    matriz = ler(p, "res_exploratoria")
    return {
        "real_hipoteses_diarias": tabela_diarias(ler(p, "res_diarias")),
        "real_hipoteses_esteira": tabela_esteira(ler(p, "res_esteira")),
        "real_sensibilidade": ler(p, "res_sensibilidade").round(3),
        "real_placebo": ler(p, "res_placebo").round(3),
        "real_matriz_exploratoria": matriz[["x", "y", "lag", "rho", "n", "q"]].round(3),
        "real_dose_resposta": dose_resposta(d),
        "real_perfil_sessao": perfil_sessao(ler(i, "fc_minuto"), ler(p, "sessoes")),
        "real_funil": ler(p, "funil_sessoes"),
        "real_leitura": tabela_leitura(raiz),
        "real_comparacao_leitura": comparacao_leitura(raiz),
        "real_validacao_alinhamento": validacao_alinhamento(d),
    }


def tabelas_sinteticas() -> dict[str, pd.DataFrame]:
    return {
        "sintetico_diario": para_publicacao(gerar_diario()),
        "sintetico_sessoes_fc": gerar_sessoes_fc().round(1),
    }


def usuario_do_export(raiz: Path) -> str:
    """O nome da pasta traz o usuário. Ele é lido na hora para não ficar escrito no código público."""
    return raiz.name.split("_")[1]


def verificar(pasta: Path, termos_proibidos: tuple[str, ...] = ()) -> list[str]:
    """Retorna os problemas encontrados. Lista vazia significa que a pasta pode ser publicada."""
    problemas = []
    for arquivo in sorted(pasta.glob("*")):
        if arquivo.name == "README.md":
            continue
        if arquivo.suffix != ".csv" or not arquivo.name.startswith(("real_", "sintetico_")):
            problemas.append(f"{arquivo.name}: arquivo fora do padrão real_*.csv ou sintetico_*.csv")
            continue
        texto = arquivo.read_text(encoding="utf-8")
        for padrao, descricao in ((PADRAO_UUID, "identificador"), (PADRAO_DATA, "data"), (PADRAO_EXPORT, "nome de usuário")):
            if padrao.search(texto):
                problemas.append(f"{arquivo.name}: contém {descricao}")
        if any(termo.lower() in texto.lower() for termo in termos_proibidos):
            problemas.append(f"{arquivo.name}: contém nome de usuário")
        tabela = pd.read_csv(arquivo)
        proibidas = sorted(COLUNAS_PROIBIDAS & set(tabela.columns))
        if proibidas:
            problemas.append(f"{arquivo.name}: colunas proibidas {proibidas}")
        if arquivo.name.startswith("real_"):
            absolutas = sorted(COLUNAS_ABSOLUTAS & set(tabela.columns))
            if absolutas:
                problemas.append(f"{arquivo.name}: valores absolutos de saúde {absolutas}")
            if "n" in tabela and (tabela["n"] < MINIMO_N).any():
                problemas.append(f"{arquivo.name}: grupo com menos de {MINIMO_N} observações")
    return problemas


def executar(pasta: Path = PASTA_PUBLICA) -> dict[str, pd.DataFrame]:
    pasta.mkdir(exist_ok=True)
    tabelas = {**tabelas_reais(), **tabelas_sinteticas()}
    for nome, tabela in tabelas.items():
        tabela.to_csv(pasta / f"{nome}.csv", index=False, encoding="utf-8")
    problemas = verificar(pasta, (usuario_do_export(localizar_export()),))
    if problemas:
        raise ValueError("Publicação bloqueada:\n" + "\n".join(problemas))
    return tabelas


if __name__ == "__main__":
    for nome, tabela in executar().items():
        print(f"{nome}: {tabela.shape[0]} linhas, {tabela.shape[1]} colunas")
    print("Verificação concluída sem problemas.")
