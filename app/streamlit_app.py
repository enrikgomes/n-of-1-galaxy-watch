"""Apresentação do projeto. Lê somente public_data/, nunca os dados privados.

Uso: streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app import demonstracao, graficos  # noqa: E402
from app.graficos import br  # noqa: E402

BASES_ESTEIRA = {
    "Todas as sessões": "todas",
    "Sem carga incerta": "sem_incerta",
    "Base estrita": "base_estrita",
}
ATRASOS = {"Mesmo dia": 0, "1 dia": 1, "2 dias": 2}


@st.cache_data
def ler(nome: str) -> pd.DataFrame:
    return pd.read_csv(RAIZ / "public_data" / f"{nome}.csv")


def mostrar_grafico(figura) -> None:
    st.plotly_chart(figura, width="stretch", theme=None, config=graficos.CONFIG)


st.set_page_config(page_title="Um ano de dados do meu relógio", layout="centered")

diarias = ler("real_hipoteses_diarias").set_index("id", drop=False)
reais = ler("real_efeitos_unidade_real").set_index("id")
esteira = ler("real_hipoteses_esteira")
placebo = ler("real_placebo").set_index("id")
sensibilidade = ler("real_sensibilidade").set_index("id")
perfil = ler("real_perfil_sessao")
funil = ler("real_funil").set_index("etapa")["sessoes"]
matriz = ler("real_matriz_exploratoria")
leitura = ler("real_comparacao_leitura").set_index("leitura")
validacao = ler("real_validacao_alinhamento")

# Abertura
st.caption("ANÁLISE N-OF-1  ·  SONO, TREINO E FREQUÊNCIA CARDÍACA")
st.title("Um ano de dados do meu relógio, e o que eles não conseguem dizer")
st.markdown(
    "#### Testei dez hipóteses sobre sono, treino e frequência cardíaca (FC), registradas "
    "antes de ver os resultados. Duas se sustentaram, uma contrariou o que eu esperava, "
    "e as cinco sobre o treino na esteira ficaram sem resposta."
)
st.divider()

# A pergunta
st.header("A pergunta")
st.markdown(
    "Uso um Galaxy Watch 7 para dormir e para registrar meus treinos, quase sempre caminhada em esteira "
    "inclinada. Queria saber o que explica a resposta do meu coração: o sono da noite anterior, o treino "
    "do dia ou as duas coisas."
)
st.markdown(
    "Esta é uma análise **n-of-1**, feita com os dados de uma só pessoa. O que aparece aqui vale para mim, "
    "neste período, e não é orientação médica nem de treino. Como não tenho cinta peitoral para comparar, "
    "o projeto também não mede a precisão do relógio."
)
st.markdown(
    "Três termos aparecem o tempo todo:\n"
    "- **FC (frequência cardíaca):** batimentos por minuto (bpm).\n"
    "- **VFC (variabilidade da frequência cardíaca):** o quanto o intervalo entre os batimentos varia. "
    "Uso o RMSSD medido durante o sono.\n"
    "- **Desvio padrão (dp) móvel:** quanto um valor se afasta do meu normal nos 28 dias anteriores."
)

# Os dados
st.header("Os dados não vêm prontos")
st.markdown(
    "O export do Samsung Health traz 53 CSVs e mais de 16 mil JSONs. O problema mais traiçoeiro está nos "
    "CSVs: cada linha tem um campo a mais que o cabeçalho, por causa de uma vírgula no final. A leitura "
    "padrão do pandas não dá nenhum erro, mas usa a primeira coluna como índice e coloca cada dado "
    "sob o nome da coluna vizinha."
)
comparacao = pd.DataFrame({
    "Datas lidas corretamente": [f"{leitura.loc[n, 'start_time_valido']} de {leitura.loc[n, 'total']}" for n in leitura.index],
    "Tipos de exercício corretos": [f"{leitura.loc[n, 'exercise_type_valido']} de {leitura.loc[n, 'total']}" for n in leitura.index],
}, index=leitura.index.rename("Leitura"))
st.table(comparacao)
st.caption("Tabela 1. Resultado das duas leituras na tabela de exercícios.")
pico = validacao[validacao["deslocamento_dias"] == 0]["r"]
vizinhos = validacao[validacao["deslocamento_dias"] != 0]["r"]
st.markdown(
    "Depois vieram outras decisões, cada uma documentada no repositório: noites divididas em vários "
    "registros, horários em UTC, unidades diferentes no mesmo arquivo e a definição de a qual dia cada noite "
    f"pertence. Essa última foi validada nos próprios dados: meus cálculos noturnos têm correlação de "
    f"{br(pico.min())} ou mais com os valores da Samsung no mesmo dia, e no máximo {br(vizinhos.max())} "
    "com um dia de deslocamento."
)

st.subheader("A velocidade que o relógio não registra")
st.markdown(
    "O modo esteira do relógio não aceita inclinação, por isso registro esses treinos como máquina de escada. "
    "A FC continua válida, mas velocidade, distância e VO2 não. No histórico, não sei a velocidade de cada sessão."
)
st.markdown(
    "Seria tentador deduzir a velocidade pela FC: se ela sobe rápido, a esteira devia estar mais veloz. Mas usar "
    "essa dedução para explicar a própria FC é **circular**. Depois de uma noite ruim, a FC sobe, a sessão seria "
    "classificada como mais rápida, e o efeito do sono desapareceria na conta. Por isso, sinais na FC servem "
    "só para marcar uma sessão como **carga incerta**, e as análises rodam com e sem ela."
)
ilustracao = ler("sintetico_sessoes_fc")
mostrar_grafico(graficos.sessoes_ilustrativas(ilustracao))
st.caption(
    "Figura 1. Dados inventados, só para ilustrar. Uma troca de velocidade aparece como uma queda de FC no "
    "meio da sessão, um dos sinais usados para marcar a carga como incerta."
)
tabela_funil = pd.DataFrame({
    "Sessões": [
        funil["Todos os exercícios"],
        funil["Esteira inclinada"],
        funil["Com pelo menos 20 min"],
        funil["Marcadas: carga incerta (qualquer motivo)"],
        funil["Base estrita (sem nenhuma marcação)"],
    ],
}, index=[
    "Todos os exercícios registrados",
    "Esteira inclinada",
    "Com FC e pelo menos 20 min: a base da análise",
    "Dessas, com carga incerta",
    "Dessas, sem nenhuma marcação (base estrita)",
])
st.table(tabela_funil)
st.caption("Tabela 2. Como 363 exercícios viram 34 sessões de análise.")

# As regras
st.header("Antes dos resultados, as regras")
st.markdown(
    "Com muitas variáveis e muitos dias de atraso possíveis, sempre aparece alguma correlação forte "
    "por acaso. Por isso, escrevi as hipóteses e os critérios antes de calcular qualquer uma delas, "
    "e deixei o histórico do git como prova da ordem. Quem define o que conta como achado são "
    "os critérios, não o resultado que eu gostaria de ver."
)
st.markdown(
    "Para uma hipótese diária ser sustentada, ela precisa passar pela correção para múltiplos testes, ter um "
    "intervalo sem o zero em um bootstrap que respeita a autocorrelação e manter o sinal em verificações "
    "alternativas. Os scores da Samsung ficam de fora, porque são compostos justamente por parte dessas variáveis."
)

# Resultados
st.header("O que apareceu")
h2, h1 = reais.loc["H2"], reais.loc["H1"]
st.markdown(
    "Na noite seguinte a um treino, minha FC durante o sono sobe e minha VFC cai. Os efeitos são pequenos: "
    f"cerca de **{br(h2['efeito'], 1)} batimento por minuto** e **{br(abs(h1['efeito']), 1)} milissegundo** "
    "por 30 minutos de treino. O teste da VFC passou sem folga."
)
mostrar_grafico(graficos.efeitos_diarios(diarias))
st.caption(
    f"Figura 2. Efeito estimado e intervalo de 95% em {diarias['n'].iloc[0]} dias. As linhas de treino mostram "
    "o efeito por 30 minutos; as de sono e horário, por 1 desvio padrão."
)
with st.expander("Ver os números da Figura 2"):
    st.dataframe(
        diarias[["id", "pergunta", "unidade", "efeito", "ic_inf", "ic_sup", "q", "veredito"]],
        hide_index=True,
        width="stretch",
    )
st.markdown(
    "O treino de um dia acontece depois da noite que termina naquele dia, então não deveria explicá-la. "
    "Acrescentei esse teste placebo depois de ver os resultados, e ele não encontrou efeito: "
    f"{br(placebo.loc['H2', 'efeito'], sinal=True)} dp na FC e {br(placebo.loc['H1', 'efeito'], sinal=True)} dp "
    "na VFC, com intervalos que incluem o zero. Isso favorece os dois achados, mas não prova causa: um dia de "
    "treino pode trazer outras mudanças na rotina."
)

st.subheader("O resultado que contrariou a expectativa")
h4 = diarias.loc["H4"]
st.markdown(
    "O ponto vazado na Figura 2 merece atenção. Esperava que dormir mais aumentasse a VFC da noite seguinte, "
    f"e o coeficiente saiu negativo. Ele cumpre os critérios, mas cai para {br(h4['efeito_sem_controle'])} sem "
    "o controle da noite anterior, o que é compatível com um artefato do modelo. Reporto o resultado como "
    "está, sem concluir que dormir mais faz mal, e sem mudar os critérios depois de vê-lo."
)

st.subheader("Mas não parece ser questão de dose")
st.markdown(
    "O modelo supõe que cada 30 minutos somam o mesmo efeito. Ao separar os dias por faixa de treino, "
    "a diferença aparece entre treinar e não treinar, sem aumentar com a duração. Duração também não "
    "mede intensidade, e o grupo de até 30 minutos é pequeno. Por isso, os números por 30 minutos "
    "são um resumo do modelo, não uma dose comprovada."
)
mostrar_grafico(graficos.dose_resposta(ler("real_dose_resposta")))
st.caption("Figura 3. Média da noite seguinte e intervalo de 95%, por faixa de treino. Descritivo, sem controles.")

# O que não dá para saber
st.header("O que não dá para saber")
st.subheader("O sono muda a FC na esteira?")
st.markdown(
    "Era uma das perguntas que mais me interessavam, e os dados não respondem. Nenhuma das cinco hipóteses "
    "gerou sinal em qualquer base de sessões. **Isso não prova ausência de efeito:** são poucas sessões, "
    "os intervalos são largos, e a velocidade do histórico é desconhecida. Troque a base abaixo e repare "
    "como o sinal de alguns efeitos muda."
)
base_escolhida = st.radio("Base de sessões", list(BASES_ESTEIRA), horizontal=True)
base = BASES_ESTEIRA[base_escolhida]
sessoes_base = esteira[esteira["base"] == base]["n"]
mostrar_grafico(graficos.efeitos_esteira(esteira, base))
st.caption(
    f"Figura 4. Efeito na FC entre os minutos 10 e 15 da sessão, com intervalo de 95%, em {sessoes_base.min()} a "
    f"{sessoes_base.max()} sessões. Sono e noite por 1 desvio padrão; despertar por hora; treino por 30 minutos."
)
st.markdown(
    "As marcações usam a própria FC, então a base estrita tende a ter FC mais baixa por construção. Ela serve "
    "para testar a sensibilidade, não é uma versão mais verdadeira dos dados."
)

st.subheader("O coração sobe sozinho")
todas = perfil[(perfil["base"] == "Todas as sessões") & (perfil["minuto"] == 29)].iloc[0]
st.markdown(
    f"Parte da dificuldade está aqui. A FC continua subindo depois do aquecimento: em mediana, {br(todas['mediana'], 0)} "
    "batimentos por minuto entre os minutos 10 e 29. É um número do mesmo tamanho da diferença que "
    "estimei entre caminhar a 3,5 e a 4 km/h, com base em uma única sessão e na equação do ACSM. Sem saber a "
    "velocidade, comparar a FC de duas sessões é mais difícil do que parece."
)
mostrar_grafico(graficos.perfil_sessao(perfil))
st.caption(
    "Figura 5. Variação da FC em relação ao minuto 10, em até 34 sessões. A faixa cobre a metade central "
    "das sessões e se abre com o tempo; a troca de velocidade em parte delas é uma explicação possível."
)

# Exploração
st.header("Para explorar")
st.subheader("A matriz de correlações")
st.markdown(
    "Esta matriz traz os meus dados reais, mas **serve para gerar perguntas, não para confirmar achados**. "
    "Na mesma noite, boa parte é mecânica: o tempo na cama quase determina o tempo dormido. Só os pares que "
    "passam pela correção para múltiplos testes (q abaixo de 0,10) mostram o número."
)
atraso_rotulo = st.radio("Atraso entre as variáveis", list(ATRASOS), horizontal=True)
atraso_matriz = ATRASOS[atraso_rotulo]
mostrar_grafico(graficos.matriz_exploratoria(matriz, atraso_matriz))
st.caption(
    "Figura 6. Correlação de Spearman entre desvios em relação aos 28 dias anteriores. A variável do eixo "
    "horizontal vem antes da do eixo vertical quando há atraso."
)
with st.expander("Ver os pares destacados neste atraso"):
    destacados = matriz[(matriz["lag"] == atraso_matriz) & (matriz["q"] < graficos.Q_DESTAQUE)].sort_values("q")
    st.dataframe(
        pd.DataFrame({
            "Variável": destacados["x"].map(graficos.ROTULOS_MATRIZ),
            "Relacionada a": destacados["y"].map(graficos.ROTULOS_MATRIZ),
            "ρ": destacados["rho"],
            "q": destacados["q"],
            "Dias": destacados["n"],
        }),
        hide_index=True,
        width="stretch",
    )

st.subheader("Experimente: o atraso importa")
st.markdown(
    "**Atenção: estes dados são inventados.** Criei 360 dias em que o treino aumenta a FC noturna "
    "apenas no dia seguinte, com um efeito escolhido para ser fácil de ver. Mude o atraso e veja o efeito "
    "aparecer e sumir. Na análise real, o atraso errado esconderia o resultado do mesmo jeito."
)
atraso_demo = st.slider("Dias entre o treino e a noite", min_value=0, max_value=3, value=0)
sintetico = ler("sintetico_diario")
resumo, correlacao = demonstracao.resumo_por_atraso(sintetico, atraso_demo)
mostrar_grafico(graficos.demonstracao_atraso(resumo))
st.caption(f"Figura 7. Dados inventados. Correlação de Spearman neste atraso: {br(correlacao)}.")

# Encerramento
st.header("Privacidade")
st.markdown(
    "Em um n-of-1, agregar não anonimiza, porque o autor é conhecido. Por isso, dados brutos e processados "
    "nunca entram no repositório. Esta página lê apenas uma pasta com efeitos, contagens, variações relativas e "
    "dados inventados, sem datas nem valores absolutos de saúde. A geração dessa pasta é bloqueada "
    "automaticamente se encontrar datas, identificadores ou grupos com menos de 5 observações."
)
st.header("O que vem depois")
st.markdown(
    "Desde o fim de outubro, registro à mão a velocidade, a inclinação e o esforço percebido (RPE, na escala "
    "de Borg) de cada treino. Quando houver sessões suficientes, a parte 2 vai testar as perguntas da esteira "
    "com a carga conhecida, calcular o VO2 pela equação do ACSM e investigar o que explica o esforço que sinto."
)
st.divider()
st.caption(
    "O código, os testes, as hipóteses e o registro de cada decisão estão no repositório do projeto: "
    "docs/HIPOTESES.md, docs/RESULTADOS.md e docs/ETL.md."
)
