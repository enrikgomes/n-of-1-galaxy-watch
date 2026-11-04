"""Testes da etapa 6. A verificação de privacidade é testada com arquivos que deveriam ser bloqueados."""
import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analysis.hipoteses import avaliar_diarias, preparar_diario
from src.publico.gerar import (
    MINIMO_N,
    _veredito,
    dose_resposta,
    perfil_sessao,
    tabela_diarias,
    usuario_do_export,
    verificar,
)
from src.publico.sintetico import (
    EFEITO_TREINO_FC,
    gerar_diario,
    gerar_sessoes_fc,
    para_publicacao,
    reconstruir_diario,
)


def gravar(pasta, nome, texto):
    (pasta / nome).write_text(texto, encoding="utf-8")


def test_gerador_sintetico_nao_acessa_arquivos():
    """Garante que os dados sintéticos não dependem de nenhum dado real."""
    arvore = ast.parse(Path("src/publico/sintetico.py").read_text(encoding="utf-8"))
    chamadas = {n.func.attr for n in ast.walk(arvore) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not {"read_parquet", "read_csv", "read_text", "read_json"} & chamadas
    modulos = {a.name for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names}
    modulos |= {n.module for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)}
    assert modulos <= {"__future__", "numpy", "pandas"}


def test_sintetico_e_reprodutivel():
    pd.testing.assert_frame_equal(gerar_diario(), gerar_diario())


def test_sintetico_muda_com_a_semente():
    assert not gerar_diario(semente=1)["rmssd_noite"].equals(gerar_diario(semente=2)["rmssd_noite"])


def test_sintetico_passa_pela_mesma_analise_e_recupera_o_efeito():
    r, _ = avaliar_diarias(preparar_diario(gerar_diario()), sorteios=200)
    h2 = r.set_index("id").loc["H2"]
    assert h2["sustentada"]
    # O efeito inventado é de 1 bpm por 30 min, em uma série com desvio de cerca de 3 bpm.
    assert h2["efeito"] == pytest.approx(EFEITO_TREINO_FC / 3, abs=0.2)


def test_publicacao_troca_data_por_indice_e_volta():
    original = gerar_diario()
    publicado = para_publicacao(original)
    assert "dia" not in publicado
    assert reconstruir_diario(publicado)["dia"].equals(original["dia"])


def test_sessao_sintetica_com_troca_cai_depois_do_minuto_15():
    s = gerar_sessoes_fc()
    troca = s[s["sessao"].str.startswith("Troca")].set_index("minuto")["fc"]
    constante = s[s["sessao"] == "Velocidade constante"].set_index("minuto")["fc"]
    assert troca.loc[12:14].mean() - constante.loc[12:14].mean() > 5
    assert abs(troca.loc[20:].mean() - constante.loc[20:].mean()) < 2


@pytest.mark.parametrize("linha", [
    ({"id": "H", "efeito": 0.2, "sinal_esperado": 1, "sustentada": True}, "Sustentada"),
    ({"id": "H", "efeito": -0.2, "sinal_esperado": 1, "sustentada": True}, "Cumpre os critérios, com sinal contrário"),
    ({"id": "H", "efeito": 0.2, "sinal_esperado": 0, "sustentada": True}, "Sustentada"),
    ({"id": "H", "efeito": 0.2, "sinal_esperado": 1, "sustentada": False}, "Não sustentada"),
])
def test_veredito(linha):
    assert _veredito(pd.Series(linha[0])) == linha[1]


def test_dose_resposta_suprime_grupos_pequenos():
    d = preparar_diario(gerar_diario())
    d["treino_30min"] = 0.0
    d.iloc[100:102, d.columns.get_loc("treino_30min")] = 3.0
    t = dose_resposta(d)
    assert "Mais de 60 min" not in set(t["faixa_treino"])
    assert (t["n"] >= MINIMO_N).all()


def test_dose_resposta_olha_a_noite_seguinte():
    d = preparar_diario(gerar_diario())
    d["treino_30min"] = 0.0
    d["z_fc_sono_media"] = 0.0
    d.iloc[100:120, d.columns.get_loc("treino_30min")] = 3.0
    d.iloc[101:121, d.columns.get_loc("z_fc_sono_media")] = 5.0
    t = dose_resposta(d).set_index(["resposta", "faixa_treino"])
    assert t.loc[("FC da noite seguinte", "Mais de 60 min"), "media_dp"] == 5


def minutos_de(uuid, valores):
    return pd.DataFrame({"datauuid": uuid, "minuto": range(len(valores)), "fc": valores, "n": 60})


def test_perfil_nao_revela_valor_absoluto():
    m = pd.concat([minutos_de(f"s{i}", [100.0 + i * 5] * 30) for i in range(6)])
    s = pd.DataFrame({"datauuid": [f"s{i}" for i in range(6)], "carga_incerta": False})
    p = perfil_sessao(m, s)
    assert (p["mediana"] == 0).all()
    assert "fc" not in p


def test_perfil_suprime_minutos_com_poucas_sessoes():
    m = pd.concat([minutos_de("a", [100.0] * 30), minutos_de("b", [100.0] * 20)])
    s = pd.DataFrame({"datauuid": ["a", "b"], "carga_incerta": False})
    assert perfil_sessao(m, s).empty


def test_tabela_diarias_arredonda_e_nao_tem_coluna_de_dados():
    r, _ = avaliar_diarias(preparar_diario(gerar_diario()), sorteios=50)
    t = tabela_diarias(r)
    assert set(t["id"]) == {"H1", "H2", "H3", "H4", "H5"}
    assert t["efeito"].equals(t["efeito"].round(3))


def test_verificacao_aceita_pasta_limpa(tmp_path):
    gravar(tmp_path, "real_ok.csv", "id,n,efeito\nH1,267,0.1\n")
    gravar(tmp_path, "sintetico_ok.csv", "dia_indice,fc\n0,60\n")
    gravar(tmp_path, "README.md", "texto")
    assert verificar(tmp_path) == []


@pytest.mark.parametrize("nome, texto, trecho", [
    ("real_a.csv", "id\nea5930c2-328d-448a-a3ac-86821602573c\n", "identificador"),
    ("real_a.csv", "quando\n2026-11-03\n", "data"),
    ("sintetico_a.csv", "quando\n2026-11-03\n", "data"),
    ("real_a.csv", "origem\nsamsunghealth_x\n", "nome de usuário"),
    ("real_a.csv", "datauuid,n\nx,10\n", "colunas proibidas"),
    ("sintetico_a.csv", "inicio_local\nx\n", "colunas proibidas"),
    ("real_a.csv", "rmssd_noite\n60\n", "valores absolutos"),
    ("real_a.csv", "id,n\nH,3\n", "menos de"),
    ("dados.csv", "a\n1\n", "fora do padrão"),
    ("real_a.parquet", "a", "fora do padrão"),
])
def test_verificacao_bloqueia(tmp_path, nome, texto, trecho):
    gravar(tmp_path, nome, texto)
    assert any(trecho in p for p in verificar(tmp_path))


def test_verificacao_bloqueia_usuario_informado(tmp_path):
    gravar(tmp_path, "real_a.csv", "origem\nFulano123\n")
    assert verificar(tmp_path) == []
    assert any("usuário" in p for p in verificar(tmp_path, ("fulano123",)))


def test_usuario_vem_do_nome_da_pasta():
    assert usuario_do_export(Path("data/raw/samsunghealth_fulano_20260101000000")) == "fulano"


def test_sintetico_pode_ter_valores_absolutos(tmp_path):
    gravar(tmp_path, "sintetico_a.csv", "rmssd_noite\n60\n")
    assert verificar(tmp_path) == []
