# Um ano de dados do meu relógio, e o que eles não conseguem dizer

Análise n-of-1 com dados de um Galaxy Watch 7: o que explica a minha resposta cardíaca? Testei dez hipóteses sobre sono, treino e frequência cardíaca (FC), registradas no git antes de calcular os resultados.

**Apresentação:** o link entra aqui depois da publicação no Streamlit. Para rodar no seu computador, veja [Como reproduzir](#como-reproduzir).

> Os dados são observacionais e de uma só pessoa. Os resultados indicam associação, nesta pessoa e neste período. Não são orientação médica nem de treino.

## Resultados

**Hipóteses diárias**, com 267 dias. VFC é a variabilidade da frequência cardíaca, medida pelo RMSSD durante o sono.

| Hipótese | Efeito (IC de 95%) | Veredito |
|---|---|---|
| Treino → FC da noite seguinte | +0,19 dp por 30 min (0,07 a 0,32) | **Sustentada** |
| Treino → VFC da noite seguinte | −0,13 dp por 30 min (−0,25 a −0,01) | **Sustentada**, no limite |
| Sono → VFC da noite seguinte | −0,12 dp por 1 dp de sono (−0,23 a −0,01) | **Cumpre os critérios**, com sinal contrário e frágil |
| Treino → tempo dormido na noite seguinte | −0,03 dp por 30 min (−0,17 a 0,10) | Não sustentada |
| Dormir mais tarde → VFC da mesma noite | +0,04 dp por 1 dp de horário (−0,08 a 0,15) | Não sustentada |

"dp" é o desvio padrão em relação aos 28 dias anteriores.

- **Efeito pequeno:** cerca de 0,6 bpm e 1 ms por 30 minutos de treino.
- **Sem dose clara:** a diferença parece estar entre treinar e não treinar, sem crescer com a duração.
- **Resultado que contrariou a expectativa:** esperava que dormir mais aumentasse a VFC da noite seguinte. O efeito negativo quase some sem o controle da noite anterior, então não concluo que dormir mais reduz a VFC.
- **Placebo:** o treino de um dia não explica a noite anterior a ele. Esse teste foi feito depois dos resultados e está declarado como tal.

**Hipóteses da esteira**, com 33 ou 34 sessões: nenhuma gerou sinal. Com poucas sessões e sem saber a velocidade do histórico, isso não prova ausência de efeito.

Os detalhes estão em [docs/RESULTADOS.md](docs/RESULTADOS.md).

## Decisões que definem o projeto

- **Hipóteses antes dos resultados:** a lista e os critérios em [docs/HIPOTESES.md](docs/HIPOTESES.md) foram commitados antes de qualquer cálculo. O histórico do git mostra a ordem.
- **Sem circularidade:** o relógio não registra a velocidade na esteira inclinada, e ela nunca é inferida da FC. Sinais na FC só marcam a sessão como "carga incerta", e as análises rodam com e sem essas sessões.
- **Variáveis brutas:** os scores da Samsung são compostos e ficam fora das hipóteses.
- **Autocorrelação:** linha de base móvel de 28 dias, erros de Newey-West, bootstrap em blocos e correção para múltiplos testes.
- **Nada é imputado:** dias sem dado continuam na tabela, com valores nulos, para que um lag de 1 linha seja sempre 1 dia.

## ETL

```text
data/raw/        Export do Samsung Health: 53 CSVs e mais de 16 mil JSONs
    | leitura.py    Corrige o formato e aplica a lista de permissão
data/interim/    12 tabelas limpas
    | fc_sessao.py  Transforma os JSONs em indicadores de FC por sessão
    | sessoes.py    Filtra a esteira e cria as marcações
    | diario.py     Consolida as noites e monta o calendário
data/processed/  Tabelas de análise
    | hipoteses.py  Testa as hipóteses
    | gerar.py      Agrega, gera dados sintéticos e verifica a privacidade
public_data/     A única pasta de dados do repositório
    | streamlit_app.py
Apresentação
```

O principal problema do formato: cada linha dos CSVs tem um campo a mais que o cabeçalho. A leitura padrão do pandas não dá erro, mas desloca todas as colunas.

| Verificação, em 363 exercícios | Leitura padrão | Leitor do projeto |
|---|---:|---:|
| Datas lidas corretamente | 0 | 363 |
| Tipos de exercício corretos | 0 | 363 |

O tratamento completo e as validações estão em [docs/ETL.md](docs/ETL.md).

## Privacidade

Em um n-of-1, agregar não anonimiza, porque o autor é conhecido. Por isso:

- Dados brutos e processados **nunca** entram no git.
- A leitura usa uma lista de permissão: GPS, amigos, perfil e ECG nem são carregados.
- O repositório e o app só usam [public_data/](public_data/README.md), com efeitos, contagens, variações relativas e dados inventados.
- A geração dessa pasta é bloqueada se encontrar datas, identificadores, nome de usuário, valores absolutos de saúde ou grupos com menos de 5 observações.
- Os dados sintéticos partem de valores inventados, e um teste confirma que o gerador não lê nenhum arquivo.

## Estrutura

```text
app/          Apresentação em Streamlit
docs/         Hipóteses, resultados e registro do ETL
public_data/  Agregados reais e dados sintéticos
scripts/      Backup local
src/          ETL, análise e geração dos dados públicos
tests/        Testes sobre dados sintéticos e públicos
```

## Como reproduzir

Para rodar a apresentação e os testes, basta clonar o repositório. Os dados privados não são necessários.

```bash
pip install -r requirements.txt
```

```bash
python -m pytest
```

```bash
streamlit run app/streamlit_app.py
```

Para refazer a análise, é preciso um export próprio do Samsung Health em `data/raw/` e o arquivo `data/config_local.json`, com o limiar de zona: `{"limiar_zona_4_bpm": <valor>}`. O código espera os mesmos tipos de treino deste projeto, então outro export pode exigir ajustes.

```bash
python -m src.etl.leitura
```

```bash
python -m src.etl.fc_sessao
```

```bash
python -m src.etl.sessoes
```

```bash
python -m src.etl.diario
```

```bash
python -m src.analysis.hipoteses
```

```bash
python -m src.publico.gerar
```

## Limites

- **Uma pessoa, dados observacionais:** calor, cafeína, doença, álcool e estresse não foram medidos.
- **Sem aparelho de referência:** o projeto não mede a precisão do relógio.
- **Carga desconhecida no histórico:** ela é uma variável omitida nas análises da esteira.

## Próximos passos

A parte 2 vai usar o registro manual de velocidade, inclinação e esforço percebido (RPE, na escala de Borg) para testar de novo as perguntas da esteira, calcular o VO2 pela equação do ACSM e investigar o que explica o esforço percebido.

---

Desenvolvido com apoio do [Claude Code](https://claude.com/claude-code).
