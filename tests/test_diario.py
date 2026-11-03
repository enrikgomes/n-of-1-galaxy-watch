"""Testes da etapa 4. Usam só tabelas sintéticas."""
import numpy as np
import pandas as pd
import pytest

from src.etl.diario import (
    consolidar_noites,
    construir_diario,
    localizar_noite,
    resumir_atividade,
    resumir_fc_noturna,
    resumir_medida,
    resumir_vfc,
)


def ts(texto):
    return pd.Timestamp(texto, tz="UTC")


def registro(uuid, inicio, fim, latencia=600000.0, score=80.0):
    """Horários em UTC; a hora local é UTC-3."""
    i, f = ts(inicio), ts(fim)
    return {
        "datauuid": uuid, "inicio_utc": i, "fim_utc": f,
        "inicio_local": (i - pd.Timedelta(hours=3)).tz_localize(None),
        "fim_local": (f - pd.Timedelta(hours=3)).tz_localize(None),
        "sleep_latency": latencia, "sleep_score": score,
    }


def estagio(sleep_id, codigo, inicio, minutos):
    i = ts(inicio)
    return {"sleep_id": sleep_id, "stage": codigo, "inicio_utc": i, "fim_utc": i + pd.Timedelta(minutes=minutos)}


def noite_simples(uuid="n1", inicio="2026-01-10 05:00", fim="2026-01-10 12:00"):
    sono = pd.DataFrame([registro(uuid, inicio, fim)])
    estagios = pd.DataFrame([
        estagio(uuid, 40001, inicio, 20), estagio(uuid, 40002, inicio, 200),
        estagio(uuid, 40003, inicio, 80), estagio(uuid, 40004, inicio, 120),
    ])
    return sono, estagios


def ms(texto):
    return int(ts(texto).timestamp() * 1000)


def test_noite_pertence_ao_dia_do_despertar():
    b = consolidar_noites(*noite_simples(inicio="2026-01-10 02:00", fim="2026-01-10 10:00"))
    assert b.loc[0, "dia"] == pd.Timestamp("2026-01-10")


def test_dormir_antes_da_meia_noite_tambem_vale_o_despertar():
    # 22h local do dia 9 até 6h local do dia 10
    b = consolidar_noites(*noite_simples(inicio="2026-01-10 01:00", fim="2026-01-10 09:00"))
    assert b.loc[0, "inicio_local"].day == 9
    assert b.loc[0, "dia"] == pd.Timestamp("2026-01-10")


def test_fragmentos_proximos_viram_uma_noite():
    sono = pd.DataFrame([
        registro("a", "2026-01-10 05:00", "2026-01-10 08:00"),
        registro("b", "2026-01-10 08:30", "2026-01-10 12:00"),
    ])
    b = consolidar_noites(sono, pd.DataFrame([estagio("a", 40002, "2026-01-10 05:00", 180), estagio("b", 40002, "2026-01-10 08:30", 210)]))
    assert len(b) == 1
    assert b.loc[0, "fragmentos"] == 2
    assert b.loc[0, "tempo_cama_min"] == 390


def test_cochilo_nao_vira_sono_principal():
    sono = pd.DataFrame([
        registro("noite", "2026-01-10 05:00", "2026-01-10 12:00"),
        registro("cochilo", "2026-01-10 18:00", "2026-01-10 19:00"),
    ])
    est = pd.DataFrame([estagio("noite", 40002, "2026-01-10 05:00", 420), estagio("cochilo", 40002, "2026-01-10 18:00", 60)])
    b = consolidar_noites(sono, est)
    assert b["principal"].tolist() == [True, False]


def test_sono_curto_sozinho_nao_e_principal():
    b = consolidar_noites(*noite_simples(inicio="2026-01-10 05:00", fim="2026-01-10 06:00"))
    assert not b.loc[0, "principal"]


def test_estagios_e_eficiencia():
    b = consolidar_noites(*noite_simples()).iloc[0]
    assert (b["acordado_min"], b["leve_min"], b["profundo_min"], b["rem_min"]) == (20, 200, 80, 120)
    assert b["sono_total_min"] == 400
    assert b["eficiencia"] == pytest.approx(400 / 420 * 100)


def test_noite_sem_estagios_fica_nula():
    sono = pd.DataFrame([registro("a", "2026-01-10 05:00", "2026-01-10 12:00"), registro("b", "2026-01-12 05:00", "2026-01-12 12:00")])
    b = consolidar_noites(sono, pd.DataFrame([estagio("a", 40002, "2026-01-10 05:00", 420)]))
    assert pd.isna(b.loc[1, "sono_total_min"]) and pd.isna(b.loc[1, "eficiencia"])


def test_localizar_noite_respeita_limites():
    noites = consolidar_noites(*noite_simples())
    t = np.array([ms("2026-01-10 04:59"), ms("2026-01-10 05:00"), ms("2026-01-10 12:00"), ms("2026-01-10 12:01")])
    assert localizar_noite(t, noites).tolist() == [-1, 0, 0, -1]


def vfc_noite(n, rmssd=50.0):
    t = ms("2026-01-10 05:00") + np.arange(n) * 30000
    return pd.DataFrame({"t_ms": t, "rmssd": rmssd, "sdnn": rmssd * 1.2})


def test_vfc_usa_mediana_e_resiste_a_artefato():
    a = vfc_noite(840)
    a.loc[:40, "rmssd"] = 300.0
    r = resumir_vfc(a, consolidar_noites(*noite_simples()))
    assert r.loc[0, "rmssd_noite"] == 50


def test_vfc_ignora_blocos_fora_da_noite():
    fora = pd.DataFrame({"t_ms": [ms("2026-01-10 15:00")], "rmssd": [500.0], "sdnn": [500.0]})
    r = resumir_vfc(pd.concat([vfc_noite(840), fora]).sort_values("t_ms"), consolidar_noites(*noite_simples()))
    assert r.loc[0, "rmssd_noite"] == 50
    assert r.loc[0, "cobertura_vfc"] == 1


def test_vfc_com_pouca_cobertura_fica_nula():
    r = resumir_vfc(vfc_noite(100), consolidar_noites(*noite_simples()))
    assert np.isnan(r.loc[0, "rmssd_noite"])
    assert r.loc[0, "cobertura_vfc"] == pytest.approx(50 / 420)


def test_fc_noturna_calcula_percentil():
    t = ms("2026-01-10 05:00") + np.arange(420) * 60000
    fc = pd.DataFrame({"t_ms": t, "fc": np.linspace(50, 70, 420)})
    r = resumir_fc_noturna(fc, consolidar_noites(*noite_simples()))
    assert r.loc[0, "fc_sono_media"] == pytest.approx(60)
    assert r.loc[0, "fc_sono_p10"] == pytest.approx(52)


def test_medida_liga_pelo_ponto_central():
    noites = consolidar_noites(*noite_simples())
    t = pd.DataFrame({
        "inicio_utc": [ts("2026-01-10 05:30"), ts("2026-01-11 05:30")],
        "fim_utc": [ts("2026-01-10 11:30"), ts("2026-01-11 11:30")],
        "temperature": [34.0, 40.0],
    })
    s = resumir_medida(t, "temperature", "temp", noites)
    assert s.to_dict() == {0: 34.0}


def atividade_exemplo():
    inicio = pd.Timestamp("2026-01-10 11:00")
    ex = pd.DataFrame({
        "datauuid": ["a", "b", "c"],
        "exercise_type": [15007, 1001, 15003],
        "inicio_local": [inicio, inicio + pd.Timedelta(hours=1), inicio + pd.Timedelta(hours=2)],
        "duration": [30 * 60000, 10 * 60000, 15 * 60000],
    })
    minutos = pd.DataFrame({"datauuid": ["a"] * 3 + ["b"], "minuto": [0, 1, 2, 0], "fc": [150.0, 160.0, 170.0, 165.0], "n": 60})
    return ex, minutos


def test_atividade_separa_caminhada_de_treino():
    a = resumir_atividade(*atividade_exemplo(), limiar=155).iloc[0]
    assert a["esteira_inclinada_min"] == 30
    assert a["caminhada_min"] == 10
    assert a["outros_min"] == 15
    assert a["treino_min"] == 45
    assert a["min_fc_acima_limiar"] == 3


def diario_exemplo(ultimo="2026-01-13"):
    sono = pd.DataFrame([registro("n1", "2026-01-10 05:00", "2026-01-10 12:00"), registro("n3", "2026-01-12 05:00", "2026-01-12 12:00")])
    est = pd.DataFrame([estagio("n1", 40002, "2026-01-10 05:00", 420), estagio("n3", 40002, "2026-01-12 05:00", 420)])
    vfc = pd.DataFrame({"t_ms": ms("2026-01-10 05:00") + np.arange(840) * 30000, "rmssd": 50.0, "sdnn": 60.0})
    fc = pd.DataFrame({"t_ms": ms("2026-01-10 05:00") + np.arange(420) * 60000, "fc": 55.0})
    medidas = {"temperatura_pele": (pd.DataFrame({"inicio_utc": [ts("2026-01-10 05:00")], "fim_utc": [ts("2026-01-10 12:00")], "temperature": [34.0]}), "temperature")}
    atividade = resumir_atividade(*atividade_exemplo(), limiar=155)
    passos = pd.DataFrame({"dia": pd.to_datetime(["2026-01-10"] * 3), "source_type": [-2, 0, 108], "count": [5000, 3000, 2000]})
    vit = pd.DataFrame({"dia": pd.to_datetime(["2026-01-10"]), "sleep_score": [80.0], "shr_value": [60.0], "shrv_value": [70.0], "shr_score": [80.0], "shrv_score": [80.0], "activity_score": [50.0], "total_score": [70.0]})
    return construir_diario(sono, est, vfc, fc, medidas, atividade, passos, vit, pd.Timestamp(ultimo))


def test_calendario_nao_tem_buracos():
    d = diario_exemplo()
    assert d["dia"].diff().dropna().eq(pd.Timedelta(days=1)).all()
    assert len(d) == 4


def test_dia_sem_sono_fica_nulo_sem_imputacao():
    d = diario_exemplo().set_index("dia").loc["2026-01-11"]
    assert not d["tem_sono"]
    assert pd.isna(d["tempo_cama_min"]) and pd.isna(d["rmssd_noite"]) and pd.isna(d["temperatura_pele"])


def test_dia_sem_exercicio_tem_zero_minutos():
    d = diario_exemplo().set_index("dia").loc["2026-01-11"]
    assert d["treino_min"] == 0


def test_passos_usam_a_fonte_combinada():
    assert diario_exemplo().set_index("dia").loc["2026-01-10", "passos"] == 5000


def test_primeiro_e_ultimo_dia_sao_parciais():
    assert diario_exemplo()["dia_parcial"].tolist() == [True, False, False, True]


def test_scores_ficam_identificados_como_samsung():
    colunas = diario_exemplo().columns
    for c in ("sam_score_sono", "sam_score_energia", "sam_vfc", "sam_fc_repouso"):
        assert c in colunas
    for c in ("sleep_score", "total_score", "shr_value", "shrv_value"):
        assert c not in colunas


def test_hora_de_dormir_antes_da_meia_noite_e_negativa():
    # 22h local do dia 9 e despertar às 6h local do dia 10
    sono = pd.DataFrame([registro("n", "2026-01-10 01:00", "2026-01-10 09:00")])
    est = pd.DataFrame([estagio("n", 40002, "2026-01-10 01:00", 480)])
    vazia = pd.DataFrame({"t_ms": pd.Series(dtype="int64"), "rmssd": pd.Series(dtype="float64"), "sdnn": pd.Series(dtype="float64")})
    fc = pd.DataFrame({"t_ms": pd.Series(dtype="int64"), "fc": pd.Series(dtype="float64")})
    atividade = resumir_atividade(*atividade_exemplo(), limiar=155)
    passos = pd.DataFrame({"dia": pd.to_datetime(["2026-01-10"]), "source_type": [-2], "count": [1]})
    vit = pd.DataFrame({"dia": pd.to_datetime(["2026-01-10"]), "sleep_score": [1.0], "shr_value": [1.0], "shrv_value": [1.0], "shr_score": [1.0], "shrv_score": [1.0], "activity_score": [1.0], "total_score": [1.0]})
    d = construir_diario(sono, est, vazia, fc, {}, atividade, passos, vit, pd.Timestamp("2026-01-10")).iloc[0]
    assert d["hora_dormir"] == -2
    assert d["hora_acordar"] == 6
