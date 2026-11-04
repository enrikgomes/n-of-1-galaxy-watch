# ETL: como os dados são tratados

Os dados brutos e processados ficam fora do repositório, em `data/`. Este documento descreve o tratamento e traz só contagens e exemplos com valores inventados.

## Etapa 1: leitura dos CSVs

**Entrada:** 53 CSVs do export do Samsung Health.
**Saída:** 12 tabelas limpas em `data/interim/`, no formato Parquet.
**Código:** [`src/etl/tabelas.py`](../src/etl/tabelas.py) define o que entra, e [`src/etl/leitura.py`](../src/etl/leitura.py) define como ler.

### Particularidades do formato

Um CSV do export tem esta aparência (valores inventados):

```text
com.samsung.shealth.exercise,6315005,4
routine_datauuid,com.samsung.health.exercise.start_time,com.samsung.health.exercise.duration
,2026-01-10 14:30:00.000,1800000,
```

| Particularidade | Consequência sem tratamento | Tratamento |
|---|---|---|
| BOM no início do arquivo | O início do arquivo é lido errado | Leitura com `utf-8-sig` |
| Linha de metadados antes do cabeçalho | Ela é lida como cabeçalho | A leitura começa nos dados e o cabeçalho é lido à parte |
| Um campo a mais em cada linha, por causa da vírgula final | As colunas se deslocam, sem erro | Coluna fantasma, que precisa estar vazia |
| Prefixo em só parte das colunas | Nomes longos e inconsistentes | Fica só o último trecho do nome, com erro se houver repetição |
| Prefixo diferente do nome do arquivo | Não dá para deduzir o nome das colunas | Mesma limpeza de nomes |
| Datas em UTC, com fuso em `time_offset` | Sono e treino caem na hora ou no dia errados | Colunas `_utc` e `_local` |
| Datas inválidas (1970) | Distorcem períodos e janelas móveis | Viram nulo e são contadas |
| Nomes de arquivo parecidos (`exercise` e `exercise.extension`) | Pode-se ler o arquivo errado | Exige o nome exato |

### O efeito do campo a mais

Com a leitura padrão do pandas (`pd.read_csv(arquivo, skiprows=1)`), a primeira coluna vira índice e cada dado fica sob o nome da coluna vizinha. O código roda sem erro. Nos 363 registros reais de exercício:

| Verificação | Leitura padrão | Leitor do projeto |
|---|---|---|
| `start_time` convertido em data | 0 de 363 | 363 de 363 |
| `exercise_type` com código válido | 0 de 363 | 363 de 363 |

O leitor também recusa o arquivo quando alguma linha foge do tamanho esperado. Isso evita outro deslocamento silencioso do pandas, que um teste encontrou durante o desenvolvimento.

### Privacidade por construção

O catálogo é uma lista de permissão: só é carregado o que está nele.

- **Arquivos fora do catálogo:** amigos, perfil, peso, altura e ECG, entre outros.
- **Colunas fora do catálogo:** coordenadas, comentários e títulos.
- **GPS:** vira apenas uma coluna verdadeiro/falso, `tem_gps`.
- **ID do aparelho:** é trocado por um código.
- **VO2, velocidade e distância do relógio:** ficam de fora, porque não valem nos treinos de esteira inclinada.

### Resultado

| Tabela | Linhas | Colunas originais | Colunas mantidas | Datas inválidas |
|---|---:|---:|---:|---:|
| `exercicio` | 363 | 75 | 13 | 0 |
| `sono` | 324 | 64 | 13 | 0 |
| `estagios_sono` | 28.454 | 13 | 7 | 0 |
| `vfc` | 2.693 | 13 | 6 | 2 |
| `fc_continua` | 5.327 | 21 | 9 | 0 |
| `recuperacao_fc` | 220 | 12 | 7 | 0 |
| `temperatura_pele` | 334 | 24 | 8 | 0 |
| `respiracao` | 335 | 20 | 7 | 0 |
| `spo2` | 335 | 24 | 8 | 0 |
| `vitalidade` | 271 | 69 | 10 | 0 |
| `passos_minuto` | 3.070 | 18 | 9 | 0 |
| `passos_dia` | 942 | 13 | 5 | 0 |

As 2 datas inválidas de `vfc` são o início e o fim de um mesmo registro. Nenhuma linha é removida nesta etapa; as decisões de filtro ficam registradas nas etapas seguintes.

### Pendências para as próximas etapas

- `passos_dia` tem 3 linhas por dia, uma por `source_type`. Nos testes exploratórios, `-2` trouxe contagens coerentes, mas isso ainda será validado.
- `passos_minuto` tem registros de mais de um aparelho. Somá-los dobra os passos.
- Os blocos de 10 min de `passos_dia` seguem a hora local, não UTC.

## Etapa 2: FC por sessão

**Entrada:** `exercicio.parquet` e os JSONs `live_data` do export.
**Saída:** `fc_sessao.parquet`, com uma linha por sessão, e `fc_minuto.parquet`, com uma linha por minuto de cada sessão.
**Código:** [`src/etl/fc_sessao.py`](../src/etl/fc_sessao.py).

### Como os arquivos se ligam

O CSV funciona como índice: o `datauuid` de cada sessão dá nome ao arquivo com as medições daquela sessão. Cada arquivo é uma lista como esta (valores inventados):

```json
[
  {"start_time": 1700000000000, "heart_rate": 110.0},
  {"start_time": 1700000001000, "heart_rate": 111.0},
  {"start_time": 1700000001000, "calorie": 0.2}
]
```

### Tratamentos

| Particularidade | Consequência sem tratamento | Tratamento |
|---|---|---|
| Arquivos parecidos (`live_data` e `live_data_internal`) | Medições lidas da fonte errada | Sufixo exato do nome |
| Itens sem FC (só calorias) | Erro ou linhas vazias | Só valem itens com horário e FC |
| 498 instantes repetidos em 308 sessões | Instantes contados duas vezes | Uma medição por instante, com a média |
| Sessões sem FC | Sumiriam da tabela | Ficam, com o motivo em `status_fc` |
| Buracos na medição | Médias de janelas com pouco dado | Janela com menos de 50% dos segundos vira nulo |
| Saltos isolados do sensor | Falsa chegada ao limiar | Mediana dos 30 s anteriores |

Valores fora de 30–230 bpm e medições fora do horário da sessão também seriam descartados, mas não apareceram neste export.

### Indicadores por sessão

| Coluna | Definição |
|---|---|
| `status_fc` | `ok`, `sem_fc`, `sem_arquivo` ou `poucas_amostras` |
| `n_amostras`, `cobertura`, `maior_buraco_s` | Qualidade da medição |
| `fc_media`, `fc_maxima`, `fc_minima` | Resumo da sessão inteira |
| `fc_05_10` ... `fc_25_30` | FC média em janelas de 5 min |
| `fc_minuto_10` | FC média entre os minutos 9 e 11 |
| `deriva_bpm_min` | Inclinação da FC do minuto 10 ao fim, por mínimos quadrados; exige pelo menos 10 min nesse trecho |
| `min_ate_limiar` | Primeiro minuto em que a mediana dos 30 s anteriores atinge o limiar; nulo se não atingir |
| `min_ate_limiar_menos5`, `min_ate_limiar_mais5` | O mesmo, com o limiar 5 bpm abaixo e acima |

O limiar da zona 4 fica em `data/config_local.json`, fora do git, porque revela um dado pessoal de FC. `min_ate_limiar` serve para marcar sessões como carga incerta, nunca para inferir a velocidade.

### Validação

Os CSVs trazem resumos de FC de cada sessão, o que permite comparar as duas fontes nas 325 sessões com FC:

| Comparação | Resultado |
|---|---|
| FC máxima | Idêntica nas 325 |
| FC mínima | Idêntica nas 325 |
| FC média | Dentro da tolerância de 1,5 bpm nas 325 |

Na média bruta do JSON, a diferença para o CSV nunca é negativa e fica sempre entre 0 e 0,99 bpm, o que indica que o CSV trunca o valor para inteiro. Por isso o projeto usa a média calculada a partir das medições.

### Resultado

| Situação | Sessões |
|---|---:|
| `ok` | 325 |
| `sem_fc` (todas caminhadas, código `1001`) | 37 |
| `sem_arquivo` (código `15003`) | 1 |
| **Total** | **363** |

As 48 sessões de esteira inclinada (`15007`) têm FC, 34 delas com 20 min ou mais.

### Pendências para as próximas etapas

- `min_ate_limiar` é calculado em todas as sessões, mas a marcação de carga incerta só vale para a esteira inclinada.
- A tabela `recuperacao_fc` ainda aponta para JSONs que não foram processados.

## Etapa 3: tabela de sessões

**Entrada:** `exercicio.parquet`, `fc_sessao.parquet` e `fc_minuto.parquet`.
**Saída:** `data/processed/sessoes.parquet`, com uma linha por sessão de esteira inclinada, e `funil_sessoes.parquet`, só com contagens.
**Código:** [`src/etl/sessoes.py`](../src/etl/sessoes.py).

### O problema da carga

O relógio não registra velocidade nem inclinação na esteira inclinada, e o registro manual só começou recentemente. Inferir a velocidade pela FC e depois usá-la para explicar a FC seria circular. Por isso:

- Velocidade, inclinação e RPE vêm só do registro manual. Sem registro, ficam nulos.
- O VO2 vem da equação do ACSM e exige velocidade e inclinação registradas.
- Sinais na FC só criam marcações de `carga_incerta`. Nenhum deles preenche a velocidade.
- Lembranças sobre o período também não viram dado de velocidade.

### Marcações

| Coluna | Significado |
|---|---|
| `incerta_limiar` | Atingiu o limiar da zona 4 antes do minuto 10 |
| `incerta_limiar_menos5`, `incerta_limiar_mais5` | A mesma regra, com o limiar 5 bpm abaixo e acima |
| `incerta_queda` | A FC média dos 3 min seguintes caiu 4 bpm ou mais em relação aos 3 min anteriores |
| `incerta_alta` | A mesma comparação, com alta de 8 bpm ou mais |
| `carga_incerta` | Pelo menos um dos motivos `incerta_limiar`, `incerta_queda` e `incerta_alta` |
| `pre_exercicio` | Outro exercício terminou até 15 min antes, sem contar caminhada |
| `pre_caminhada` | Uma caminhada terminou até 15 min antes |
| `buraco_fc` | Maior buraco na medição acima de 60 s |
| `base_estrita` | Sem carga incerta, outro exercício antes ou buraco na medição |

Quedas e altas são medidas a partir do minuto 8, para não confundir o aquecimento com mudança de carga. O corte de 4 bpm vem da distribuição: as sessões formam um grupo sem queda relevante e outro com 4 bpm ou mais. O corte de 8 bpm é menos seguro, porque as altas não têm separação natural.

Esses sinais não distinguem troca de velocidade de pausa, desaceleração ou sensor. Uma carga registrada prevalece sobre todos eles.

### Filtros e motivos

| Filtro | Motivo |
|---|---|
| Código `15007` | É a esteira inclinada, registrada como máquina de escada |
| Com FC | É a variável principal da análise |
| Pelo menos 20 min | Sessões mais curtas não têm os trechos finais |

### Funil

| Etapa | Sessões |
|---|---:|
| Todos os exercícios | 363 |
| Esteira inclinada | 48 |
| Com FC | 48 |
| Com pelo menos 20 min | 34 |

Marcações dentro das 34 sessões, que podem se sobrepor:

| Marcação | Sessões |
|---|---:|
| Carga registrada | 0 |
| Limiar da zona 4 (5 bpm abaixo / 5 bpm acima) | 9 (12 / 4) |
| Queda de FC | 10 |
| Alta de FC | 7 |
| **Carga incerta, por qualquer motivo** | **14** |
| Outro exercício antes | 5 |
| Buraco na medição | 3 |
| **Base estrita** | **16** |

A base estrita tem 16 sessões nos três valores de limiar.

### Limites

- **Seleção pela variável resposta:** as marcações usam a própria FC. Por isso a base estrita tende a ter FC mais baixa por construção e não é uma versão mais verdadeira dos dados. Serve como teste de sensibilidade.
- **Concentração no tempo:** 12 das 16 sessões da base estrita são de outubro, e 7 das 10 sessões de setembro estão marcadas como carga incerta. Comparar as duas bases também compara períodos diferentes.
- **Amostra pequena:** com 34 sessões, a análise de esteira é exploratória.

### Pendências para as próximas etapas

- O registro manual ainda não foi lido; ele entra na parte 2, pelo parâmetro `carga` de `construir_sessoes`.
- A cadência fica de fora até haver mais sessões com velocidade registrada para validá-la.

## Etapa 4: tabela diária

**Entrada:** tabelas de `data/interim/` e os JSONs de VFC e de FC contínua.
**Saída:** `data/processed/diario.parquet`, com uma linha por dia do calendário.
**Código:** [`src/etl/diario.py`](../src/etl/diario.py).

### A qual dia cada noite pertence

A noite pertence ao **dia em que você acorda**. Isso define a ordem no tempo dentro de cada dia D:

```text
noite que termina em D  ->  treinos de D  ->  noite que termina em D+1
```

- O sono de D antecede o treino de D, sem precisar de lag na tabela.
- O treino de D afeta o sono de D+1.

As 34 sessões de esteira começam depois do despertar daquele dia, de 0,8 a 7,9 h depois.

O calendário não tem buracos: dias sem dado ficam com linha nula. Assim, deslocar 1 linha é sempre deslocar 1 dia, o que não aconteceria se esses dias fossem removidos.

### Do registro à noite

| Particularidade | Consequência sem tratamento | Tratamento |
|---|---|---|
| Uma noite dividida em mais de um registro (12 noites) | Metade da noite é tratada como cochilo | Registros a até 2 h um do outro viram uma noite |
| Cochilos e sonos curtos | Contados como a noite | Sono principal: o maior bloco do dia, com pelo menos 3 h; o resto vai para `cochilo_min` |
| Estágios em códigos numéricos | Significado desconhecido | Mapeamento conferido nos dados (abaixo) |
| Unidades diferentes (`sleep_duration` em minutos, `sleep_latency` em milissegundos) | Valores errados por um fator de 60 mil | Conversão explícita |
| Hora de dormir cruza a meia-noite | 23h e 0h ficam a 23 h de distância | Horas a partir da meia-noite do dia: 23h vira −1 |

### Medidas noturnas

| Coluna | Origem | Cálculo |
|---|---|---|
| `rmssd_noite`, `sdnn_noite` | Blocos de 30 s nos JSONs de VFC | Mediana dos blocos dentro da noite |
| `fc_sono_media`, `fc_sono_p10` | Medições por minuto nos JSONs de FC contínua | Média e percentil 10 dentro da noite |
| `temperatura_pele`, `respiracao`, `spo2` | Um valor por período nos CSVs | Valor do período cujo ponto central cai na noite |

A mediana protege a VFC de blocos com artefato. Noites com cobertura abaixo de 50% ficariam nulas, mas isso não ocorreu: a cobertura típica é de 96% ou mais.

### Atividade

Minutos por dia em `esteira_inclinada_min`, `esteira_plana_min`, `musculacao_min`, `caminhada_min` e `outros_min`, mais `treino_min`, que não conta caminhada. `min_fc_acima_limiar` conta os minutos de exercício com FC no limiar ou acima.

### Scores e valores da Samsung

Todos ficam em colunas com prefixo `sam_`, separados das variáveis calculadas no projeto. Nenhum substitui uma variável bruta.

O `sleep_duration` de `vitalidade` foi retirado da análise: a faixa dele é bem mais estreita que a da duração real das noites, e a correlação com ela é só de 0,41. Ele não representa a duração daquela noite.

### Validações

| Verificação | Resultado |
|---|---|
| Código `40004` x `total_rem_duration` | r = 1,000 (é REM) |
| Código `40002` x `total_light_duration` | r = 1,000 (é sono leve) |
| Eficiência calculada com `40001` como acordado x eficiência da Samsung | r = 0,991 (`40001` é acordado e, por eliminação, `40003` é sono profundo) |
| `sam_fc_repouso` x `fc_sono_media`, mesmo dia | r = 0,979; 0,489 e 0,499 com 1 dia de deslocamento |
| `sam_vfc` x `rmssd_noite`, mesmo dia | r = 0,972; 0,397 e 0,401 com 1 dia de deslocamento |
| Soma dos minutos de exercício x CSV de exercícios | Idêntica |
| Fonte de passos `-2` | Fica entre a maior das outras fontes e a soma delas; todos os 30 dias com esteira de 25 min ou mais têm pelo menos 2 mil passos |

As correlações com deslocamento mostram que a regra do dia do despertar está certa: elas têm um pico nítido no mesmo dia.

### Cobertura

| Situação | Dias |
|---|---:|
| Calendário | 352 |
| Com sono principal | 309 |
| Com estágios e medidas noturnas | 308 |
| Com valores `sam_` | 271 |

### Limites

- **Uso do relógio:** ele é usado para dormir e para registrar atividades, raramente no resto do dia. Por isso, zero minuto de treino significa que não houve treino. Já os passos refletem o tempo com o relógio no pulso, e 103 dias têm menos de 200 passos. Eles não medem a atividade diária e não entram nas hipóteses. Caminhadas feitas sem o relógio também não aparecem em `caminhada_min`.
- **Faltas não aleatórias:** os 43 dias sem sono se concentram de abril a junho, em sequências de até 10 dias.
- **Dias parciais:** o primeiro e o último dia têm `dia_parcial`, porque a atividade e os passos não estão completos.
- **Circularidade:** `sam_fc_repouso` quase repete `fc_sono_media`, e `sam_vfc` quase repete `rmssd_noite`. Correlacioná-los entre si, ou um score com seus insumos, não diz nada novo.
- **`is_outlier` da respiração:** 68% dos registros têm valor 1 e as medianas são quase iguais. O significado não está claro, por isso a coluna não filtra nada.

## Etapa 5: hipóteses

As análises estão descritas em [HIPOTESES.md](HIPOTESES.md) e [RESULTADOS.md](RESULTADOS.md).

## Etapa 6: dados públicos

**Saída:** `public_data/`, a única pasta de dados do repositório, descrita em [seu README](../public_data/README.md).
**Código:** [`src/publico/gerar.py`](../src/publico/gerar.py) e [`src/publico/sintetico.py`](../src/publico/sintetico.py).

- **Agregados reais:** só efeitos, contagens e variações relativas. Grupos com menos de 5 observações são suprimidos.
- **Dados sintéticos:** gerados a partir de valores inventados. Um teste confirma que o gerador não lê nenhum arquivo.
- **Verificação:** ao final da geração, uma checagem procura datas, identificadores, nome de usuário, colunas proibidas e grupos pequenos. Se achar algum, a publicação é bloqueada.

## Como reproduzir

```bash
python -m pytest
python -m src.etl.leitura
python -m src.etl.fc_sessao
python -m src.etl.sessoes
python -m src.etl.diario
python -m src.analysis.hipoteses
python -m src.publico.gerar
```

Os testes usam só dados sintéticos, então rodam sem os dados reais. Os outros comandos exigem o export em `data/raw/`, e `fc_sessao` também exige `data/config_local.json`.
