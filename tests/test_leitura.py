"""Testes da etapa 1. Usam só CSVs sintéticos, então rodam sem os dados reais."""
import pandas as pd
import pytest

from src.etl.leitura import ErroDeEsquema, ler_bruto, ler_tabela, limpar_nomes, localizar_arquivo
from src.etl.tabelas import TABELAS

ARQUIVO = "com.samsung.shealth.exercise"
PREFIXO = "com.samsung.health.exercise."
SUFIXO = ".20261103165237.csv"


def valores_exercicio(**extras):
    base = {
        "datauuid": "sessao-1",
        "start_time": "2026-01-10 14:30:00.000",
        "end_time": "2026-01-10 15:00:00.000",
        "time_offset": "UTC-0300",
        "exercise_type": "15007",
        "duration": "1800000",
        "mean_heart_rate": "140",
        "max_heart_rate": "150",
        "min_heart_rate": "100",
        "count": "",
        "mean_cadence": "",
        "location_data": "",
        "update_time": "2026-01-10 15:01:00.000",
        "start_latitude": "-1.5",
        "comment": "texto pessoal",
    }
    return {**base, **extras}


def escrever(pasta, valores, arquivo=ARQUIVO, meta=None, virgula_final=True, prefixar=True):
    """Imita o formato do export: BOM, metadados, cabeçalho e vírgula final."""
    nomes = [f"{PREFIXO}{c}" if prefixar else c for c in valores]
    fim = "," if virgula_final else ""
    linhas = [f"{meta or arquivo},6315005,4", ",".join(nomes), ",".join(valores.values()) + fim]
    caminho = pasta / f"{arquivo}{SUFIXO}"
    caminho.write_bytes(("﻿" + "\n".join(linhas) + "\n").encode("utf-8"))
    return caminho


def test_virgula_final_nao_desloca_colunas(tmp_path):
    caminho = escrever(tmp_path, valores_exercicio())
    df = limpar_nomes(ler_bruto(caminho, ARQUIVO))
    assert df.loc[0, "datauuid"] == "sessao-1"
    assert df.loc[0, "mean_heart_rate"] == 140


def test_leitura_ingenua_do_pandas_desloca_colunas(tmp_path):
    """Documenta o problema: a leitura padrão não dá erro, mas erra o conteúdo."""
    caminho = escrever(tmp_path, valores_exercicio())
    df = limpar_nomes(pd.read_csv(caminho, encoding="utf-8-sig", skiprows=1))
    assert df["datauuid"].iloc[0] != "sessao-1"


def test_funciona_sem_virgula_final(tmp_path):
    caminho = escrever(tmp_path, valores_exercicio(), virgula_final=False)
    assert limpar_nomes(ler_bruto(caminho, ARQUIVO)).loc[0, "datauuid"] == "sessao-1"


@pytest.mark.parametrize("extra", ["campo_inesperado", "campo_inesperado,"])
def test_campo_alem_do_cabecalho_gera_erro(tmp_path, extra):
    """Cobre um campo a mais com conteúdo e dois campos a mais, que o pandas não acusa."""
    valores = valores_exercicio()
    caminho = tmp_path / f"{ARQUIVO}{SUFIXO}"
    caminho.write_text(
        f"{ARQUIVO},1,1\n{','.join(valores)}\n{','.join(valores.values())},{extra}\n",
        encoding="utf-8",
    )
    with pytest.raises(ErroDeEsquema):
        ler_bruto(caminho, ARQUIVO)


def test_nome_exato_nao_confunde_arquivos_parecidos(tmp_path):
    esperado = escrever(tmp_path, valores_exercicio())
    escrever(tmp_path, valores_exercicio(), arquivo=f"{ARQUIVO}.extension")
    assert localizar_arquivo(tmp_path, ARQUIVO) == esperado


def test_metadados_de_outro_arquivo_geram_erro(tmp_path):
    caminho = escrever(tmp_path, valores_exercicio(), meta="com.samsung.outra.tabela")
    with pytest.raises(ErroDeEsquema):
        ler_bruto(caminho, ARQUIVO)


def test_nomes_repetidos_sem_prefixo_geram_erro():
    df = pd.DataFrame(columns=["a.start_time", "b.start_time"])
    with pytest.raises(ErroDeEsquema):
        limpar_nomes(df)


def test_utc_vira_hora_local(tmp_path):
    escrever(tmp_path, valores_exercicio())
    df, _ = ler_tabela(tmp_path, "exercicio")
    assert df.loc[0, "inicio_local"] == pd.Timestamp("2026-01-10 11:30:00")
    assert df.loc[0, "inicio_utc"] == pd.Timestamp("2026-01-10 14:30:00", tz="UTC")


def test_data_de_1970_vira_nula_e_e_contada(tmp_path):
    escrever(tmp_path, valores_exercicio(start_time="1970-01-01 00:00:00.000"))
    df, resumo = ler_tabela(tmp_path, "exercicio")
    assert pd.isna(df.loc[0, "inicio_utc"])
    assert resumo.datas_invalidas == 1


def test_colunas_sensiveis_nao_entram(tmp_path):
    escrever(tmp_path, valores_exercicio(location_data="arquivo.json"))
    df, _ = ler_tabela(tmp_path, "exercicio")
    assert not {"location_data", "start_latitude", "comment"} & set(df.columns)
    assert bool(df.loc[0, "tem_gps"]) is True


def test_coluna_ausente_gera_erro(tmp_path):
    valores = valores_exercicio()
    del valores["mean_heart_rate"]
    escrever(tmp_path, valores)
    with pytest.raises(ErroDeEsquema):
        ler_tabela(tmp_path, "exercicio")


def test_catalogo_nao_inclui_arquivos_sensiveis():
    arquivos = " ".join(t.arquivo for t in TABELAS.values())
    for termo in ("social", "user_profile", "ecg", "weight", "height"):
        assert termo not in arquivos


def test_catalogo_nao_inclui_colunas_sensiveis_ou_vetadas():
    colunas = {c for t in TABELAS.values() for c in t.colunas}
    assert not {"start_latitude", "start_longitude", "comment", "title", "vo2_max", "mean_speed", "distance"} & colunas
