"""Etapa 1 do ETL: transforma os CSVs do Samsung Health em tabelas limpas.

Particularidades do export tratadas aqui:
  1. BOM no início do arquivo.
  2. Uma linha de metadados antes do cabeçalho.
  3. Um campo a mais em cada linha, por causa de uma vírgula final. Sem tratamento,
     o pandas usa a primeira coluna como índice e desloca todas as outras.
  4. Prefixos em só parte das colunas (com.samsung.health.exercise.start_time).
  5. Datas em UTC, com o fuso em outra coluna (time_offset).
  6. Datas inválidas, como 1970-01-01.

Uso: python -m src.etl.leitura
"""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from src.etl.tabelas import TABELAS

FORMATO_DATA = "%Y-%m-%d %H:%M:%S.%f"
DATA_MINIMA = pd.Timestamp("2000-01-01", tz="UTC")
COLUNA_FANTASMA = "__campo_extra__"
PERIODOS = {"start_time": "inicio", "end_time": "fim"}


class ErroDeEsquema(ValueError):
    """O arquivo não tem a estrutura esperada. Melhor parar do que seguir com dados errados."""


@dataclass
class ResumoLeitura:
    tabela: str
    linhas: int
    colunas_originais: int
    colunas_mantidas: int
    datas_invalidas: int
    ids_repetidos: int


def localizar_export(raiz_dados: Path = Path("data/raw")) -> Path:
    """Retorna a pasta de export mais recente; o nome termina com data e hora."""
    pastas = sorted(raiz_dados.glob("samsunghealth_*"))
    if not pastas:
        raise FileNotFoundError(f"Nenhum export encontrado em {raiz_dados}")
    return pastas[-1]


def localizar_arquivo(raiz: Path, arquivo: str) -> Path:
    """Exige o nome exato, para 'exercise' não casar com 'exercise.extension'."""
    padrao = re.compile(rf"^{re.escape(arquivo)}\.\d{{14}}\.csv$")
    achados = [p for p in raiz.glob("*.csv") if padrao.match(p.name)]
    if len(achados) != 1:
        raise ErroDeEsquema(f"Esperava 1 arquivo para {arquivo}, encontrei {len(achados)}")
    return achados[0]


def ler_bruto(caminho: Path, arquivo: str) -> pd.DataFrame:
    """Lê o CSV, resolvendo BOM, linha de metadados e vírgula final."""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.reader(f)
        metadados = next(leitor)
        cabecalho = next(leitor)
        tamanhos = {len(linha) for linha in leitor if linha}
    if not metadados or metadados[0] != arquivo:
        raise ErroDeEsquema(f"{caminho.name}: a primeira linha não identifica {arquivo}")

    # Com campos demais, o pandas usaria as primeiras colunas como índice, sem dar erro.
    # Por isso cada linha é contada antes: só vale o tamanho do cabeçalho, com ou sem a vírgula final.
    inesperados = tamanhos - {len(cabecalho), len(cabecalho) + 1}
    if inesperados:
        raise ErroDeEsquema(f"{caminho.name}: linhas com {sorted(inesperados)} campos; cabeçalho tem {len(cabecalho)}")

    # A coluna fantasma recebe o campo vazio criado pela vírgula final.
    df = pd.read_csv(
        caminho,
        encoding="utf-8-sig",
        skiprows=2,
        header=None,
        names=[*cabecalho, COLUNA_FANTASMA],
        low_memory=False,
    )
    # Se ela tiver algum valor, as colunas estão desalinhadas.
    if df[COLUNA_FANTASMA].notna().any():
        raise ErroDeEsquema(f"{caminho.name}: há dados além do cabeçalho; colunas desalinhadas")
    return df.drop(columns=COLUNA_FANTASMA)


def limpar_nomes(df: pd.DataFrame) -> pd.DataFrame:
    """Remove prefixos: com.samsung.health.exercise.start_time vira start_time."""
    nomes = [c.rsplit(".", 1)[-1] for c in df.columns]
    repetidos = sorted({n for n in nomes if nomes.count(n) > 1})
    if repetidos:
        raise ErroDeEsquema(f"Colunas repetidas sem o prefixo: {repetidos}")
    return df.set_axis(nomes, axis=1)


def _offset_para_timedelta(offset: pd.Series) -> pd.Series:
    """Converte 'UTC-0300' em -3 horas. Formato desconhecido vira nulo."""
    partes = offset.astype("string").str.extract(r"^UTC([+-])(\d{2})(\d{2})$")
    sinal = partes[0].map({"+": 1, "-": -1}).astype("Float64")
    minutos = partes[1].astype("Float64") * 60 + partes[2].astype("Float64")
    return pd.to_timedelta((sinal * minutos).astype("float64"), unit="min")


def converter_datas(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Cria colunas em UTC e em hora local. Retorna também o total de datas inválidas."""
    df = df.copy()
    invalidas = 0
    for original, novo in PERIODOS.items():
        if original not in df:
            continue
        utc = pd.to_datetime(df[original], format=FORMATO_DATA, errors="coerce", utc=True)
        utc = utc.where(utc >= DATA_MINIMA)  # 1970 e similares viram nulo
        invalidas += int(utc.isna().sum())
        df[f"{novo}_utc"] = utc
        df[f"{novo}_local"] = (utc + _offset_para_timedelta(df["time_offset"])).dt.tz_localize(None)
        df = df.drop(columns=original)
    if "day_time" in df:
        dia = pd.to_datetime(df["day_time"], format=FORMATO_DATA, errors="coerce")
        invalidas += int(dia.isna().sum())
        df["dia"] = dia.dt.normalize()
        df = df.drop(columns="day_time")
    return df.drop(columns="time_offset", errors="ignore"), invalidas


def proteger_identificadores(df: pd.DataFrame) -> pd.DataFrame:
    """Guarda só se havia GPS e troca o ID do aparelho por um código."""
    df = df.copy()
    if "location_data" in df:
        df["tem_gps"] = df["location_data"].notna()
        df = df.drop(columns="location_data")
    if "deviceuuid" in df:
        df["dispositivo"] = df["deviceuuid"].map(lambda u: hashlib.sha256(str(u).encode()).hexdigest()[:8])
        df = df.drop(columns="deviceuuid")
    return df


def ler_tabela(raiz: Path, nome: str) -> tuple[pd.DataFrame, ResumoLeitura]:
    """Executa a leitura completa de uma tabela do catálogo."""
    tabela = TABELAS[nome]
    bruto = limpar_nomes(ler_bruto(localizar_arquivo(raiz, tabela.arquivo), tabela.arquivo))

    faltando = [c for c in tabela.colunas if c not in bruto.columns]
    if faltando:
        raise ErroDeEsquema(f"{nome}: colunas ausentes {faltando}; o esquema pode ter mudado")

    df = proteger_identificadores(bruto[list(tabela.colunas)])
    df, invalidas = converter_datas(df)
    resumo = ResumoLeitura(
        tabela=nome,
        linhas=len(df),
        colunas_originais=bruto.shape[1],
        colunas_mantidas=df.shape[1],
        datas_invalidas=invalidas,
        ids_repetidos=int(df["datauuid"].duplicated().sum()),
    )
    return df, resumo


def executar(destino: Path = Path("data/interim")) -> pd.DataFrame:
    """Lê todas as tabelas, salva em Parquet e retorna o relatório, só com contagens."""
    raiz = localizar_export()
    destino.mkdir(parents=True, exist_ok=True)
    resumos = []
    for nome in TABELAS:
        df, resumo = ler_tabela(raiz, nome)
        df.to_parquet(destino / f"{nome}.parquet", index=False)
        resumos.append(asdict(resumo))
    return pd.DataFrame(resumos)


if __name__ == "__main__":
    print(executar().to_string(index=False))
