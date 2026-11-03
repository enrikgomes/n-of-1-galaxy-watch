"""Testes da etapa 3. Usam só tabelas sintéticas."""
import numpy as np
import pandas as pd
import pytest

from src.etl.sessoes import construir_funil, construir_sessoes, medir_mudancas, vo2_acsm


def exercicio(*linhas):
    """Cada linha: (id, tipo, início, duração em min)."""
    registros = []
    for uuid, tipo, inicio, dur in linhas:
        t0 = pd.Timestamp(inicio, tz="UTC")
        registros.append({
            "datauuid": uuid, "exercise_type": tipo, "duration": dur * 60000,
            "inicio_utc": t0, "fim_utc": t0 + pd.Timedelta(minutes=dur),
            "inicio_local": (t0 - pd.Timedelta(hours=3)).tz_localize(None),
            "fim_local": (t0 + pd.Timedelta(minutes=dur) - pd.Timedelta(hours=3)).tz_localize(None),
            "mean_heart_rate": 140, "max_heart_rate": 150, "min_heart_rate": 100,
            "count": np.nan, "mean_cadence": np.nan, "tem_gps": False,
        })
    return pd.DataFrame(registros)


def fc_sessao(ids, limiar=None, buraco=5.0, status="ok"):
    limiar = limiar or {}
    return pd.DataFrame({
        "datauuid": ids, "status_fc": status, "maior_buraco_s": buraco,
        "min_ate_limiar": [limiar.get(i, np.nan) for i in ids],
        "min_ate_limiar_menos5": [limiar.get(i, np.nan) for i in ids],
        "min_ate_limiar_mais5": [limiar.get(i, np.nan) for i in ids],
    })


def fc_minuto(uuid, valores):
    return pd.DataFrame({"datauuid": uuid, "minuto": range(len(valores)), "fc": valores, "n": 60})


ESTAVEL = [120.0] * 30
UM = exercicio(("a", 15007, "2026-01-10 14:00:00", 30))


def construir(ex=UM, fc=None, minutos=None, **kw):
    fc = fc_sessao(list(ex["datauuid"])) if fc is None else fc
    minutos = fc_minuto("a", ESTAVEL) if minutos is None else minutos
    return construir_sessoes(ex, fc, minutos, **kw)


def test_vo2_confere_com_a_equacao_do_acsm():
    assert vo2_acsm(3.5, 10) == pytest.approx(19.83, abs=0.01)
    assert vo2_acsm(4.0, 10) == pytest.approx(22.17, abs=0.01)


def test_filtra_tipo_duracao_e_status():
    ex = exercicio(
        ("a", 15007, "2026-01-10 14:00:00", 30),
        ("curta", 15007, "2026-01-11 14:00:00", 10),
        ("plana", 15005, "2026-01-12 14:00:00", 30),
        ("semfc", 15007, "2026-01-13 14:00:00", 30),
    )
    fc = fc_sessao(list(ex["datauuid"]), status=["ok", "ok", "ok", "sem_fc"])
    assert construir(ex, fc)["datauuid"].tolist() == ["a"]


def test_sem_registro_carga_e_rpe_ficam_nulos():
    s = construir().iloc[0]
    for coluna in ("velocidade_kmh", "inclinacao_pct", "rpe_imediato", "rpe_30min", "vo2_acsm"):
        assert pd.isna(s[coluna])
    assert not s["carga_registrada"]


def test_limiar_nunca_preenche_velocidade():
    fc = fc_sessao(["a"], limiar={"a": 5.0})
    s = construir(fc=fc).iloc[0]
    assert s["incerta_limiar"] and s["carga_incerta"]
    assert pd.isna(s["velocidade_kmh"]) and pd.isna(s["vo2_acsm"])


def test_regra_so_vale_antes_do_minuto_limite():
    assert not construir(fc=fc_sessao(["a"], limiar={"a": 10.0})).iloc[0]["incerta_limiar"]
    assert construir(fc=fc_sessao(["a"], limiar={"a": 9.9})).iloc[0]["incerta_limiar"]


def test_carga_registrada_prevalece_sobre_sinais_de_fc():
    fc = fc_sessao(["a"], limiar={"a": 5.0})
    carga = pd.DataFrame({"datauuid": ["a"], "velocidade_kmh": [4.0], "inclinacao_pct": [10.0], "rpe_imediato": [6.0], "rpe_30min": [np.nan]})
    s = construir(fc=fc, carga=carga).iloc[0]
    assert s["carga_registrada"] and not s["carga_incerta"]
    assert s["vo2_acsm"] == pytest.approx(22.17, abs=0.01)
    assert pd.isna(s["rpe_30min"])


def test_inclinacao_ausente_nao_gera_vo2():
    carga = pd.DataFrame({"datauuid": ["a"], "velocidade_kmh": [4.0], "inclinacao_pct": [np.nan], "rpe_imediato": [np.nan], "rpe_30min": [np.nan]})
    s = construir(carga=carga).iloc[0]
    assert pd.isna(s["vo2_acsm"]) and not s["carga_registrada"]


def test_queda_detecta_reducao_no_meio_da_sessao():
    valores = [150.0] * 15 + [140.0] * 15
    m = medir_mudancas(fc_minuto("a", valores)).iloc[0]
    assert m["queda_fc_bpm"] == pytest.approx(10)
    assert m["minuto_queda"] in (14, 15)


def test_aquecimento_nao_conta_como_alta():
    valores = list(np.linspace(100, 145, 8)) + [145.0] * 22
    assert medir_mudancas(fc_minuto("a", valores)).iloc[0]["alta_fc_bpm"] < 1


def test_deriva_gradual_nao_marca_queda_nem_alta():
    valores = [120 + 0.5 * m for m in range(30)]
    s = construir(minutos=fc_minuto("a", valores)).iloc[0]
    assert not s["incerta_queda"] and not s["incerta_alta"]


def test_minuto_com_poucas_amostras_e_ignorado():
    m = fc_minuto("a", ESTAVEL + [60.0])
    m.loc[m["minuto"] == 30, "n"] = 3
    assert medir_mudancas(m).iloc[0]["queda_fc_bpm"] == 0


def test_exercicio_anterior_marca_pre_exercicio():
    ex = exercicio(("m", 15002, "2026-01-10 13:00:00", 50), ("a", 15007, "2026-01-10 13:55:00", 30))
    s = construir(ex, fc_sessao(["m", "a"])).iloc[0]
    assert s["pre_exercicio"] and not s["pre_caminhada"] and s["tipo_anterior"] == 15002
    assert not s["base_estrita"]


def test_caminhada_anterior_fica_separada():
    ex = exercicio(("c", 1001, "2026-01-10 13:45:00", 10), ("a", 15007, "2026-01-10 14:00:00", 30))
    s = construir(ex, fc_sessao(["c", "a"])).iloc[0]
    assert s["pre_caminhada"] and not s["pre_exercicio"] and s["base_estrita"]


def test_exercicio_distante_nao_marca():
    ex = exercicio(("m", 15002, "2026-01-10 10:00:00", 50), ("a", 15007, "2026-01-10 14:00:00", 30))
    s = construir(ex, fc_sessao(["m", "a"])).iloc[0]
    assert not s["pre_exercicio"] and not s["pre_caminhada"]


def test_hora_e_dia_usam_horario_local():
    ex = exercicio(("a", 15007, "2026-01-11 01:00:00", 30))
    s = construir(ex).iloc[0]
    assert s["dia"] == pd.Timestamp("2026-01-10")
    assert s["hora_local"] == 22


def test_buraco_sai_da_base_estrita():
    s = construir(fc=fc_sessao(["a"], buraco=120.0)).iloc[0]
    assert s["buraco_fc"] and not s["base_estrita"]


def test_funil_conta_cada_filtro():
    ex = exercicio(
        ("a", 15007, "2026-01-10 14:00:00", 30),
        ("curta", 15007, "2026-01-11 14:00:00", 10),
        ("c", 1001, "2026-01-12 14:00:00", 10),
    )
    fc = fc_sessao(list(ex["datauuid"]))
    s = construir_sessoes(ex, fc, fc_minuto("a", ESTAVEL))
    f = construir_funil(ex, fc, s).set_index("etapa")["sessoes"]
    assert f["Todos os exercícios"] == 3
    assert f["Esteira inclinada"] == 2
    assert f["Com pelo menos 20 min"] == 1
    assert f["Base estrita (sem nenhuma marcação)"] == 1
