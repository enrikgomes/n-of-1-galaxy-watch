"""Testes da apresentação. O app só pode depender de public_data/."""
import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import demonstracao, graficos

P = Path("public_data")


@pytest.fixture(scope="module")
def app():
    return AppTest.from_file("app/streamlit_app.py", default_timeout=60).run()


def texto_da_pagina(app) -> str:
    partes = [e.value for colecao in (app.markdown, app.caption, app.title, app.header, app.subheader) for e in colecao]
    return "\n".join(partes)


def test_app_roda_sem_erros(app):
    assert not app.exception
    assert app.title


def test_app_mostra_todas_as_figuras_e_tabelas(app):
    legendas = [c.value for c in app.caption]
    for rotulo in [f"Figura {n}" for n in range(1, 8)] + ["Tabela 1", "Tabela 2"]:
        assert any(texto.startswith(rotulo) for texto in legendas), rotulo


def test_prototipo_nao_aparece_mais(app):
    assert "protótipo" not in texto_da_pagina(app).lower()


def test_dados_inventados_estao_rotulados(app):
    legendas = [c.value for c in app.caption]
    for figura in ("Figura 1", "Figura 7"):
        assert any(t.startswith(figura) and "inventados" in t for t in legendas)
    assert "dados são inventados" in texto_da_pagina(app)


@pytest.mark.parametrize("rotulo", ["Sem carga incerta", "Base estrita"])
def test_troca_de_base_funciona(rotulo):
    app = AppTest.from_file("app/streamlit_app.py", default_timeout=60).run()
    app.radio[0].set_value(rotulo).run()
    assert not app.exception


@pytest.mark.parametrize("rotulo", ["1 dia", "2 dias"])
def test_troca_de_atraso_da_matriz_funciona(rotulo):
    app = AppTest.from_file("app/streamlit_app.py", default_timeout=60).run()
    app.radio[1].set_value(rotulo).run()
    assert not app.exception


def test_demonstracao_reage_ao_atraso():
    app = AppTest.from_file("app/streamlit_app.py", default_timeout=60).run()
    legenda = lambda a: next(c.value for c in a.caption if c.value.startswith("Figura 7"))
    antes = legenda(app)
    app.slider[0].set_value(1).run()
    assert not app.exception
    assert legenda(app) != antes


def test_codigo_do_app_nao_le_dados_privados():
    for arquivo in Path("app").glob("*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"data/(raw|interim|processed)|/ \"data\"|read_parquet|samsunghealth|src\.", codigo), arquivo


def test_app_so_usa_arquivos_que_existem():
    codigo = Path("app/streamlit_app.py").read_text(encoding="utf-8")
    for nome in re.findall(r'ler\("([^"]+)"\)', codigo):
        assert (P / f"{nome}.csv").exists(), nome


def test_grafico_de_efeitos_tem_todas_as_hipoteses_e_vereditos():
    t = pd.read_csv(P / "real_hipoteses_diarias.csv")
    f = graficos.efeitos_diarios(t)
    assert sum(len(traco.x) for traco in f.data) == len(t)
    assert set(t["veredito"]) <= set(graficos.ESTILO_VEREDITO)


def test_veredito_nao_depende_so_da_cor():
    estilos = [(e["color"], e["symbol"]) for e in graficos.ESTILO_VEREDITO.values()]
    assert len(set(estilos)) == len(estilos)
    assert len({e["symbol"] for e in graficos.ESTILO_VEREDITO.values()}) >= 2


def test_dose_resposta_tem_dois_paineis_na_mesma_escala():
    f = graficos.dose_resposta(pd.read_csv(P / "real_dose_resposta.csv"))
    assert len(f.data) == 2
    assert f.layout.xaxis.range == f.layout.xaxis2.range


def test_numeros_usam_virgula_e_sinal_tipografico():
    assert graficos.br(-0.131) == "−0,13"
    assert graficos.br(0.194, 1, sinal=True) == "+0,2"
    assert graficos.br(10.2, 0, sinal=True) == "+10"


def test_eixos_tem_marcas_em_portugues():
    f = graficos.efeitos_diarios(pd.read_csv(P / "real_hipoteses_diarias.csv"))
    assert list(f.layout.xaxis.ticktext) == ["−0,4", "−0,2", "0", "+0,2", "+0,4"]


def test_rotulos_nao_ocupam_a_largura_dos_dados():
    t = pd.read_csv(P / "real_hipoteses_diarias.csv")
    for figura in (graficos.efeitos_diarios(t), graficos.dose_resposta(pd.read_csv(P / "real_dose_resposta.csv"))):
        assert figura.layout.yaxis.visible is False
        assert figura.layout.margin.l <= 24


def test_todas_as_linhas_tem_rotulo():
    t = pd.read_csv(P / "real_hipoteses_diarias.csv")
    textos = [a.text for a in graficos.efeitos_diarios(t).layout.annotations]
    assert all(rotulo in textos for rotulo in graficos.ROTULOS_DIARIAS.values())


def test_perfil_respeita_o_intervalo_de_minutos():
    f = graficos.perfil_sessao(pd.read_csv(P / "real_perfil_sessao.csv"))
    assert min(f.data[-1].x) == 5
    assert max(f.data[-1].x) == 29


def test_eixo_da_esteira_nao_tem_decimais():
    f = graficos.efeitos_esteira(pd.read_csv(P / "real_hipoteses_esteira.csv"), "todas")
    assert list(f.layout.xaxis.ticktext) == ["−12", "−8", "−4", "0", "+4"]


@pytest.mark.parametrize("base", ["todas", "sem_incerta", "base_estrita"])
def test_esteira_mostra_as_cinco_hipoteses_dentro_do_eixo(base):
    t = pd.read_csv(P / "real_hipoteses_esteira.csv")
    f = graficos.efeitos_esteira(t, base)
    assert len(f.data[0].x) == 5
    b = t[t["base"] == base]
    assert b["ic_inf"].min() >= f.layout.xaxis.range[0]
    assert b["ic_sup"].max() <= f.layout.xaxis.range[1]


def test_matriz_da_mesma_noite_e_simetrica():
    f = graficos.matriz_exploratoria(pd.read_csv(P / "real_matriz_exploratoria.csv"), 0)
    z = pd.DataFrame(f.data[0].z)
    pd.testing.assert_frame_equal(z, z.T, check_names=False)


@pytest.mark.parametrize("lag", [0, 1, 2])
def test_matriz_mostra_numero_so_nos_pares_com_q_baixo(lag):
    t = pd.read_csv(P / "real_matriz_exploratoria.csv")
    f = graficos.matriz_exploratoria(t, lag)
    cheios = sum(1 for linha in f.data[0].text for celula in linha if celula)
    destaque = int(((t["lag"] == lag) & (t["q"] < graficos.Q_DESTAQUE)).sum())
    assert cheios == (destaque * 2 if lag == 0 else destaque)


def test_demonstracao_mostra_efeito_so_no_atraso_de_um_dia():
    d = pd.read_csv(P / "sintetico_diario.csv")
    correlacoes = {a: demonstracao.resumo_por_atraso(d, a)[1] for a in range(4)}
    assert correlacoes[1] > 0.2
    assert all(abs(correlacoes[a]) < correlacoes[1] / 2 for a in (0, 2, 3))


def test_zscore_da_demonstracao_igual_ao_da_analise():
    from src.analysis.hipoteses import zscore_movel

    d = pd.read_csv(P / "sintetico_diario.csv")["rmssd_noite"]
    pd.testing.assert_series_equal(demonstracao.zscore_movel(d), zscore_movel(d))
