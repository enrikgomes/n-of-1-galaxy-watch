"""Testes da etapa 2. Usam só séries de FC sintéticas."""
import json

import numpy as np
import pandas as pd
import pytest

from src.etl.fc_sessao import (
    SUFIXO_ARQUIVO,
    calcular_deriva,
    carregar_limiar,
    encontrar_arquivos,
    fc_por_minuto,
    ler_amostras,
    minutos_ate_limiar,
    processar,
    resumir_sessao,
    validar_contra_csv,
)

INICIO = pd.Timestamp("2026-01-10 14:00:00", tz="UTC")
INICIO_MS = INICIO.timestamp() * 1000


def serie(minutos=30, fc=lambda m: 120.0, passo_s=1):
    """Gera medições a cada passo_s segundos, com a FC em função do minuto."""
    t = np.arange(0, minutos * 60, passo_s)
    return pd.DataFrame({"t_ms": INICIO_MS + t * 1000.0, "fc": [float(fc(s / 60)) for s in t]})


def fim_ms(minutos=30):
    return INICIO_MS + minutos * 60000


def gravar(pasta, nome, conteudo):
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")
    return caminho


def test_ignora_itens_sem_fc(tmp_path):
    c = gravar(tmp_path, "a.json", [{"start_time": 1000, "calorie": 5.0}, {"start_time": 2000, "heart_rate": 100.0}])
    assert ler_amostras(c)["fc"].tolist() == [100.0]


def test_tempo_repetido_vira_media(tmp_path):
    c = gravar(tmp_path, "a.json", [{"start_time": 1000, "heart_rate": 100.0}, {"start_time": 1000, "heart_rate": 110.0}])
    assert ler_amostras(c)["fc"].tolist() == [105.0]


def test_remove_valores_impossiveis_e_ordena(tmp_path):
    c = gravar(tmp_path, "a.json", [
        {"start_time": 3000, "heart_rate": 120.0},
        {"start_time": 2000, "heart_rate": 0.0},
        {"start_time": 1000, "heart_rate": 110.0},
        {"start_time": 4000, "heart_rate": 300.0},
    ])
    assert ler_amostras(c)["fc"].tolist() == [110.0, 120.0]


def test_janelas_medem_o_trecho_certo():
    r = resumir_sessao(serie(fc=lambda m: 100.0 if m < 15 else 150.0), INICIO_MS, fim_ms(), 200)
    assert r["fc_10_15"] == pytest.approx(100)
    assert r["fc_20_25"] == pytest.approx(150)


def test_sessao_curta_nao_preenche_janela_tardia():
    r = resumir_sessao(serie(minutos=20), INICIO_MS, fim_ms(20), 200)
    assert not np.isnan(r["fc_15_20"])
    assert np.isnan(r["fc_25_30"])


def test_janela_com_pouco_dado_fica_nula():
    a = serie()
    a = a[~((a["t_ms"] - INICIO_MS) / 60000).between(10, 14.5)]
    r = resumir_sessao(a, INICIO_MS, fim_ms(), 200)
    assert np.isnan(r["fc_10_15"])


def test_deriva_recupera_inclinacao_conhecida():
    a = serie(fc=lambda m: 120 + 0.5 * m).assign(minuto=lambda d: (d["t_ms"] - INICIO_MS) / 60000)
    assert calcular_deriva(a) == pytest.approx(0.5)


def test_deriva_nula_em_sessao_curta():
    a = serie(minutos=15).assign(minuto=lambda d: (d["t_ms"] - INICIO_MS) / 60000)
    assert np.isnan(calcular_deriva(a))


def test_limiar_marca_o_cruzamento_sustentado():
    a = serie(fc=lambda m: 100.0 if m < 8 else 160.0).assign(minuto=lambda d: (d["t_ms"] - INICIO_MS) / 60000)
    assert minutos_ate_limiar(a, 150) == pytest.approx(8.25, abs=0.05)


def test_salto_isolado_nao_conta_como_limiar():
    a = serie().assign(minuto=lambda d: (d["t_ms"] - INICIO_MS) / 60000)
    a.loc[300:305, "fc"] = 190.0
    assert np.isnan(minutos_ate_limiar(a, 150))


def test_sensibilidade_do_limiar_usa_valores_vizinhos():
    r = resumir_sessao(serie(fc=lambda m: 148.0 if m < 10 else 153.0), INICIO_MS, fim_ms(), 150)
    assert r["min_ate_limiar_menos5"] < 1
    assert 10 < r["min_ate_limiar"] < 11
    assert np.isnan(r["min_ate_limiar_mais5"])


def test_poucas_amostras_tem_status_proprio():
    r = resumir_sessao(serie(minutos=1, passo_s=30), INICIO_MS, fim_ms(1), 150)
    assert r["status_fc"] == "poucas_amostras"
    assert "fc_media" not in r


def test_amostras_fora_da_sessao_sao_ignoradas():
    a = pd.concat([serie(minutos=20), pd.DataFrame({"t_ms": [fim_ms(20) + 60000], "fc": [200.0]})])
    assert resumir_sessao(a, INICIO_MS, fim_ms(20), 250)["fc_maxima"] == 120


def test_por_minuto_agrega_medicoes():
    m = fc_por_minuto("x", serie(minutos=2, fc=lambda t: 100.0 if t < 1 else 110.0), INICIO_MS)
    assert m["fc"].tolist() == [100.0, 110.0]
    assert m["n"].tolist() == [60, 60]


def test_arquivos_internal_nao_sao_usados(tmp_path):
    pasta = tmp_path / "jsons" / "com.samsung.shealth.exercise" / "a"
    gravar(pasta, f"id1{SUFIXO_ARQUIVO}", [])
    gravar(pasta, "id2.live_data_internal.json", [])
    assert list(encontrar_arquivos(tmp_path)) == ["id1"]


def test_processar_registra_todas_as_sessoes(tmp_path):
    medicoes = [{"start_time": int(INICIO_MS + s * 1000), "heart_rate": 120.0} for s in range(600)]
    com_fc = gravar(tmp_path, f"a{SUFIXO_ARQUIVO}", medicoes)
    sem_fc = gravar(tmp_path, f"b{SUFIXO_ARQUIVO}", [{"start_time": 1, "calorie": 1.0}])
    ex = pd.DataFrame({
        "datauuid": ["a", "b", "c"],
        "inicio_utc": [INICIO] * 3,
        "fim_utc": [INICIO + pd.Timedelta(minutes=10)] * 3,
    })
    sessoes, minutos = processar(ex, {"a": com_fc, "b": sem_fc}, 150)
    assert sessoes["status_fc"].tolist() == ["ok", "sem_fc", "sem_arquivo"]
    assert set(minutos["datauuid"]) == {"a"}


def test_validacao_aponta_divergencia_com_o_csv():
    ex = pd.DataFrame({"datauuid": ["a", "b"], "mean_heart_rate": [120, 120], "max_heart_rate": [150, 150], "min_heart_rate": [100, 100]})
    s = pd.DataFrame({"datauuid": ["a", "b"], "status_fc": ["ok", "ok"], "fc_media": [121.2, 130.0], "fc_maxima": [150.0, 150.0], "fc_minima": [100.0, 100.0]})
    v = validar_contra_csv(ex, s)
    assert v["sessoes_comparadas"] == 2
    assert v["media_divergente"] == 1
    assert v["maxima_divergente"] == 0


def test_limiar_exige_configuracao_local(tmp_path):
    with pytest.raises(FileNotFoundError):
        carregar_limiar(tmp_path / "ausente.json")
    c = gravar(tmp_path, "config.json", {"limiar_zona_4_bpm": 123})
    assert carregar_limiar(c) == 123
