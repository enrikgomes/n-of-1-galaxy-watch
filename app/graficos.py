"""Gráficos da apresentação, todos em um só estilo.

Marcas finas, grade discreta e rótulos diretos. A cor nunca é o único sinal: o veredito
também aparece no formato do ponto e na legenda.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

TINTA = "#1f2328"
TINTA_SECUNDARIA = "#5c6168"
GRADE = "#e6e3da"
FUNDO = "#fbfaf7"
DESTAQUE = "#a8322a"
DESTAQUE_CLARO = "rgba(168, 50, 42, 0.14)"
NEUTRO = "#6f7680"
FONTE = '"Source Serif 4", "Source Serif Pro", Georgia, serif'

CONFIG = {"displayModeBar": False, "scrollZoom": False}

ROTULOS_DIARIAS = {
    "H2": "Treino → FC da noite seguinte",
    "H1": "Treino → VFC da noite seguinte",
    "H4": "Sono → VFC da noite seguinte",
    "H3": "Treino → tempo dormido",
    "H5": "Dormir tarde → VFC da mesma noite",
}
ESTILO_VEREDITO = {
    "Sustentada": {"color": DESTAQUE, "symbol": "circle"},
    "Cumpre os critérios, com sinal contrário": {"color": DESTAQUE, "symbol": "circle-open"},
    "Não sustentada": {"color": NEUTRO, "symbol": "circle"},
}
ORDEM_FAIXAS = ["Sem treino", "Até 30 min", "31 a 60 min", "Mais de 60 min"]
ROTULOS_ESTEIRA = {
    "H6": "Tempo dormido na noite anterior",
    "H7": "VFC da noite anterior",
    "H8": "FC do sono da noite anterior",
    "H9": "Horas desde o despertar",
    "H10": "Treino no dia anterior",
}
ROTULOS_MATRIZ = {
    "treino_min": "Treino",
    "tempo_cama_min": "Tempo na cama",
    "sono_total_min": "Tempo dormido",
    "profundo_min": "Sono profundo",
    "rem_min": "Sono REM",
    "eficiencia": "Eficiência do sono",
    "hora_dormir": "Hora de dormir",
    "rmssd_noite": "VFC",
    "fc_sono_media": "FC no sono",
    "temperatura_pele": "Temperatura da pele",
    "respiracao": "Respiração",
    "spo2": "Oxigenação (SpO2)",
}
ESCALA_DIVERGENTE = [[0, "#2a6fb0"], [0.5, "#f1efe9"], [1, DESTAQUE]]
Q_DESTAQUE = 0.10


def br(valor: float, casas: int = 2, sinal: bool = False) -> str:
    """Número com vírgula decimal e sinal de menos tipográfico."""
    texto = f"{valor:{'+' if sinal else ''}.{casas}f}".replace(".", ",").replace("-", "−")
    return texto


def _marcas_eixo(valores: list[float], casas: int = 1) -> dict:
    """Marcas fixas no eixo, em português e com sinal, para não depender do formato automático."""
    return {
        "tickmode": "array",
        "tickvals": valores,
        "ticktext": ["0" if v == 0 else br(v, casas, sinal=True) for v in valores],
    }


def _estilizar(figura: go.Figure, altura: int) -> go.Figure:
    figura.update_layout(
        height=altura,
        font={"family": FONTE, "size": 14, "color": TINTA},
        paper_bgcolor=FUNDO,
        plot_bgcolor=FUNDO,
        margin={"l": 24, "r": 16, "t": 16, "b": 8},
        hoverlabel={"bgcolor": FUNDO, "font": {"family": FONTE, "color": TINTA}},
    )
    figura.update_xaxes(showgrid=True, gridcolor=GRADE, zeroline=False, ticks="", linecolor=GRADE, automargin=True, tickfont={"color": TINTA_SECUNDARIA})
    figura.update_yaxes(showgrid=False, zeroline=False, ticks="", linecolor=GRADE, tickfont={"color": TINTA}, automargin=True)
    return figura


def _rotulos_acima(figura: go.Figure, rotulos: list[str], linha: int | None = None) -> None:
    """Escreve cada rótulo acima da sua linha, para os dados usarem toda a largura no celular."""
    total = len(rotulos)
    grade = {"row": linha, "col": 1} if linha else {}
    for indice, rotulo in enumerate(rotulos):
        figura.add_annotation(
            text=rotulo, x=0, y=total - 1 - indice, xref="x domain", showarrow=False, xanchor="left", yanchor="bottom",
            yshift=7, align="left", bgcolor=FUNDO, font={"family": FONTE, "size": 14, "color": TINTA}, **grade,
        )
    figura.update_yaxes(visible=False, range=[-0.5, total - 0.2], **grade)


def efeitos_diarios(tabela: pd.DataFrame) -> go.Figure:
    """Efeito e intervalo de 95% das hipóteses diárias."""
    ordem = list(ROTULOS_DIARIAS)
    t = tabela.assign(
        rotulo=tabela["id"].map(ROTULOS_DIARIAS),
        linha=tabela["id"].map({id_h: len(ordem) - 1 - i for i, id_h in enumerate(ordem)}),
    )
    figura = go.Figure()
    for veredito, estilo in ESTILO_VEREDITO.items():
        g = t[t["veredito"] == veredito]
        figura.add_trace(go.Scatter(
            x=g["efeito"], y=g["linha"], mode="markers", name=veredito,
            marker={"size": 11, "color": estilo["color"], "symbol": estilo["symbol"], "line": {"width": 2, "color": estilo["color"]}},
            error_x={"type": "data", "symmetric": False, "array": g["ic_sup"] - g["efeito"], "arrayminus": g["efeito"] - g["ic_inf"], "color": estilo["color"], "thickness": 2, "width": 0},
            customdata=[
                [l.rotulo, br(l.efeito, sinal=True), l.unidade, br(l.ic_inf), br(l.ic_sup), br(l.q, 3)]
                for l in g.itertuples()
            ],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} %{customdata[2]}<br>IC de 95%: %{customdata[3]} a %{customdata[4]}<br>q = %{customdata[5]}<extra></extra>",
        ))
    figura.add_vline(x=0, line_width=1, line_color=TINTA_SECUNDARIA)
    _estilizar(figura, 430)
    _rotulos_acima(figura, [ROTULOS_DIARIAS[i] for i in ordem])
    figura.update_xaxes(title={"text": "Efeito, em desvios padrão da resposta", "font": {"color": TINTA_SECUNDARIA}}, range=[-0.4, 0.4], **_marcas_eixo([-0.4, -0.2, 0, 0.2, 0.4]))
    figura.update_layout(legend={"orientation": "h", "x": 0, "xanchor": "left", "y": 1.02, "yanchor": "bottom", "title": ""}, margin={"t": 72})
    return figura


def dose_resposta(tabela: pd.DataFrame) -> go.Figure:
    """Média da noite seguinte por faixa de treino, em dois painéis com a mesma escala."""
    respostas = ["FC da noite seguinte", "VFC da noite seguinte"]
    figura = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
        subplot_titles=[f"<b>{r}</b>" for r in respostas],
    )
    figura.update_annotations(font={"family": FONTE, "size": 15, "color": TINTA}, xanchor="left", x=0)
    for numero, resposta in enumerate(respostas, start=1):
        g = tabela[tabela["resposta"] == resposta].set_index("faixa_treino").reindex(ORDEM_FAIXAS)
        rotulos = [f"{faixa} ({int(n)} dias)" for faixa, n in zip(g.index, g["n"])]
        figura.add_trace(go.Scatter(
            x=g["media_dp"], y=list(range(len(g) - 1, -1, -1)), mode="markers", showlegend=False,
            marker={"size": 10, "color": DESTAQUE},
            error_x={"type": "data", "symmetric": False, "array": g["ic_sup"] - g["media_dp"], "arrayminus": g["media_dp"] - g["ic_inf"], "color": DESTAQUE, "thickness": 2, "width": 0},
            customdata=[
                [rotulo, br(media, sinal=True), br(inf), br(sup)]
                for rotulo, media, inf, sup in zip(rotulos, g["media_dp"], g["ic_inf"], g["ic_sup"])
            ],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} dp<br>IC de 95%: %{customdata[2]} a %{customdata[3]}<extra></extra>",
        ), row=numero, col=1)
        figura.add_vline(x=0, line_width=1, line_color=TINTA_SECUNDARIA, row=numero, col=1)
        _rotulos_acima(figura, rotulos, linha=numero)
    _estilizar(figura, 560)
    figura.update_yaxes(visible=False)
    figura.update_xaxes(range=[-1.0, 1.5], **_marcas_eixo([-1, -0.5, 0, 0.5, 1, 1.5]))
    figura.update_xaxes(title={"text": "Desvios padrão", "font": {"color": TINTA_SECUNDARIA}}, row=2, col=1)
    figura.update_layout(margin={"t": 32})
    return figura


def efeitos_esteira(tabela: pd.DataFrame, base: str) -> go.Figure:
    """Efeito e intervalo de 95% das hipóteses da esteira, em uma base de sessões."""
    ordem = list(ROTULOS_ESTEIRA)
    t = tabela[tabela["base"] == base].set_index("id").reindex(ordem)
    figura = go.Figure(go.Scatter(
        x=t["efeito"], y=list(range(len(t) - 1, -1, -1)), mode="markers", showlegend=False,
        marker={"size": 11, "color": NEUTRO},
        error_x={"type": "data", "symmetric": False, "array": t["ic_sup"] - t["efeito"], "arrayminus": t["efeito"] - t["ic_inf"], "color": NEUTRO, "thickness": 2, "width": 0},
        customdata=[
            [ROTULOS_ESTEIRA[l.Index], br(l.efeito, 1, True), l.unidade, br(l.ic_inf, 1), br(l.ic_sup, 1), l.n]
            for l in t.itertuples()
        ],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} %{customdata[2]}<br>IC de 95%: %{customdata[3]} a %{customdata[4]}<br>%{customdata[5]} sessões<extra></extra>",
    ))
    figura.add_vline(x=0, line_width=1, line_color=TINTA_SECUNDARIA)
    _estilizar(figura, 400)
    _rotulos_acima(figura, [ROTULOS_ESTEIRA[i] for i in ordem])
    figura.update_xaxes(title={"text": "Efeito na FC da esteira (bpm)", "font": {"color": TINTA_SECUNDARIA}}, range=[-12.5, 6.5], **_marcas_eixo([-12, -8, -4, 0, 4], casas=0))
    return figura


def matriz_exploratoria(tabela: pd.DataFrame, lag: int) -> go.Figure:
    """Correlações de Spearman. Só os pares com q abaixo de 0,10 mostram o número."""
    t = tabela[tabela["lag"] == lag]
    if lag == 0:
        espelho = t.rename(columns={"x": "y", "y": "x"})
        t = pd.concat([t, espelho], ignore_index=True)
    nomes = list(ROTULOS_MATRIZ)
    rho = t.pivot(index="y", columns="x", values="rho").reindex(index=nomes, columns=nomes)
    q = t.pivot(index="y", columns="x", values="q").reindex(index=nomes, columns=nomes)
    rotulos = [ROTULOS_MATRIZ[n] for n in nomes]
    texto = rho.where(q < Q_DESTAQUE).map(lambda v: "" if pd.isna(v) else br(v, 2).replace("0,", ",", 1))
    dica = [
        [
            "" if pd.isna(rho.iloc[i, j]) else f"ρ = {br(rho.iloc[i, j])}<br>q = {br(q.iloc[i, j], 3)}"
            for j in range(len(nomes))
        ]
        for i in range(len(nomes))
    ]
    figura = go.Figure(go.Heatmap(
        z=rho.to_numpy(), x=rotulos, y=rotulos, zmin=-1, zmax=1, zmid=0, colorscale=ESCALA_DIVERGENTE,
        xgap=2, ygap=2, text=texto.to_numpy(), texttemplate="%{text}", textfont={"family": FONTE, "size": 10},
        customdata=dica, hoverongaps=False,
        hovertemplate="<b>%{x}</b> → <b>%{y}</b><br>%{customdata}<extra></extra>",
        colorbar={"thickness": 8, "len": 0.6, "outlinewidth": 0, "tickvals": [-1, 0, 1], "ticktext": ["−1", "0", "+1"], "title": {"text": "ρ", "side": "top"}},
    ))
    _estilizar(figura, 600)
    figura.update_xaxes(showgrid=False, tickangle=-45, tickfont={"color": TINTA, "size": 12}, side="bottom", title={"text": f"Variável {lag} dia(s) antes" if lag else "Mesma noite ou dia", "font": {"color": TINTA_SECUNDARIA}})
    figura.update_yaxes(autorange="reversed", tickfont={"size": 12})
    return figura


def sessoes_ilustrativas(tabela: pd.DataFrame) -> go.Figure:
    """Duas sessões inventadas. A troca de velocidade também se distingue pela linha tracejada."""
    figura = go.Figure()
    for sessao, estilo in (("Velocidade constante", {"color": TINTA, "dash": "solid"}), ("Troca de velocidade no minuto 15", {"color": NEUTRO, "dash": "dash"})):
        g = tabela[tabela["sessao"] == sessao]
        figura.add_trace(go.Scatter(
            x=g["minuto"], y=g["fc"], mode="lines", name=sessao, line={"width": 2, **estilo},
            hovertemplate=sessao + "<br>Minuto %{x}: %{y:.0f} bpm (inventado)<extra></extra>",
        ))
    _estilizar(figura, 340)
    figura.add_vline(x=15, line_width=1, line_dash="dot", line_color=TINTA_SECUNDARIA)
    figura.update_xaxes(title={"text": "Minuto da sessão", "font": {"color": TINTA_SECUNDARIA}}, showgrid=False)
    figura.update_yaxes(title={"text": "FC inventada (bpm)", "font": {"color": TINTA_SECUNDARIA}}, showgrid=True, gridcolor=GRADE, tickfont={"color": TINTA_SECUNDARIA})
    figura.update_layout(legend={"orientation": "h", "x": 0, "xanchor": "left", "y": 1.02, "yanchor": "bottom", "title": ""}, margin={"t": 52})
    return figura


def demonstracao_atraso(tabela: pd.DataFrame) -> go.Figure:
    """Média da FC noturna inventada por duração do treino, com o atraso escolhido."""
    figura = go.Figure(go.Scatter(
        x=tabela["media"], y=list(range(len(tabela) - 1, -1, -1)), mode="markers", showlegend=False,
        marker={"size": 11, "color": NEUTRO},
        error_x={"type": "data", "symmetric": False, "array": tabela["ic_sup"] - tabela["media"], "arrayminus": tabela["media"] - tabela["ic_inf"], "color": NEUTRO, "thickness": 2, "width": 0},
        customdata=[[l.treino, br(l.media, sinal=True), l.n] for l in tabela.itertuples()],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} dp (inventado)<br>%{customdata[2]} dias<extra></extra>",
    ))
    figura.add_vline(x=0, line_width=1, line_color=TINTA_SECUNDARIA)
    _estilizar(figura, 300)
    _rotulos_acima(figura, list(tabela["treino"]))
    figura.update_xaxes(title={"text": "FC noturna inventada, em desvios padrão", "font": {"color": TINTA_SECUNDARIA}}, range=[-1.0, 1.0], **_marcas_eixo([-1, -0.5, 0, 0.5, 1]))
    return figura


def perfil_sessao(tabela: pd.DataFrame, base: str = "Todas as sessões", inicio: int = 5, fim: int = 29) -> go.Figure:
    """Variação mediana da FC, com a faixa entre os quartis."""
    g = tabela[(tabela["base"] == base) & tabela["minuto"].between(inicio, fim)]
    figura = go.Figure()
    figura.add_trace(go.Scatter(x=g["minuto"], y=g["p75"], mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False))
    figura.add_trace(go.Scatter(x=g["minuto"], y=g["p25"], mode="lines", line={"width": 0}, fill="tonexty", fillcolor=DESTAQUE_CLARO, hoverinfo="skip", showlegend=False))
    figura.add_trace(go.Scatter(
        x=g["minuto"], y=g["mediana"], mode="lines", line={"width": 2, "color": DESTAQUE}, showlegend=False,
        customdata=[[br(l.mediana, 1, True), br(l.p25, 1, True), br(l.p75, 1, True), l.n] for l in g.itertuples()],
        hovertemplate="<b>Minuto %{x}</b><br>Mediana: %{customdata[0]} bpm<br>Metade das sessões: %{customdata[1]} a %{customdata[2]} bpm<br>%{customdata[3]} sessões<extra></extra>",
    ))
    figura.add_hline(y=0, line_width=1, line_color=TINTA_SECUNDARIA)
    ultimo = g.iloc[-1]
    figura.add_annotation(
        x=ultimo["minuto"], y=ultimo["mediana"], text=f"{br(ultimo['mediana'], 0, sinal=True)} bpm", showarrow=False,
        xanchor="right", yanchor="bottom", yshift=8, font={"family": FONTE, "size": 14, "color": TINTA},
    )
    _estilizar(figura, 320)
    figura.update_xaxes(title={"text": "Minuto da sessão", "font": {"color": TINTA_SECUNDARIA}}, showgrid=False)
    figura.update_yaxes(title={"text": "Variação (bpm)", "font": {"color": TINTA_SECUNDARIA}}, showgrid=True, gridcolor=GRADE, tickfont={"color": TINTA_SECUNDARIA})
    return figura
