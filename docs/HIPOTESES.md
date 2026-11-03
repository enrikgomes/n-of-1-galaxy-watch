# Hipóteses da parte 1

Esta lista foi escrita e aprovada em 03/11/2026, antes de calcular qualquer relação entre as variáveis abaixo. Definir o teste antes de ver o resultado reduz o risco de escolher, depois, só o que pareceu interessante.

## O que já tinha sido visto

A independência não é total. Durante o ETL, foram vistos:

- a distribuição da FC na esteira, por mês e por marcação;
- a comparação entre a cadência e a FC na esteira, que não está nesta lista;
- correlações de validação entre valores da Samsung e os calculados no projeto.

Nenhuma das relações listadas aqui foi calculada.

## Hipóteses diárias

São as análises principais, com cerca de 260 dias cada.

| ID | Causa provável | Resposta | Sinal esperado | n | Efeito mínimo detectável (r) |
|---|---|---|---|---:|---:|
| H1 | Minutos de treino em D | RMSSD da noite que termina em D+1 | − | 269 | 0,17 |
| H2 | Minutos de treino em D | FC média da noite que termina em D+1 | + | 269 | 0,17 |
| H3 | Minutos de treino em D | Tempo dormido na noite que termina em D+1 | Sem expectativa | 269 | 0,17 |
| H4 | Tempo dormido na noite que termina em D | RMSSD da noite que termina em D+1 | + | 255 | 0,17 |
| H5 | Hora de dormir na noite que termina em D | RMSSD da mesma noite | − | 269 | 0,17 |

## Hipóteses da esteira

São exploratórias. A resposta é sempre a FC média entre os minutos 10 e 15 da sessão (`fc_10_15`).

| ID | Causa provável | Sinal esperado | n (todas / sem carga incerta / base estrita) | Efeito mínimo detectável (r) |
|---|---|---|---:|---:|
| H6 | Tempo dormido na noite anterior | − | 33 / 20 / 16 | 0,47 / 0,59 / 0,65 |
| H7 | RMSSD da noite anterior | − | 33 / 20 / 16 | 0,47 / 0,59 / 0,65 |
| H8 | FC média da noite anterior | + | 33 / 20 / 16 | 0,47 / 0,59 / 0,65 |
| H9 | Horas desde o despertar | Sem expectativa | 34 / 20 / 16 | 0,46 / 0,59 / 0,65 |
| H10 | Minutos de treino no dia anterior | + | 34 / 20 / 16 | 0,46 / 0,59 / 0,65 |

O efeito mínimo detectável é o menor |r| com 80% de poder e significância de 5%, sem considerar autocorrelação nem controles. Os valores reais são um pouco piores.

## Método

### Preparação

- **Linha de base móvel:** RMSSD, FC noturna, tempo dormido e hora de dormir viram z-score em relação aos 28 dias anteriores, sem incluir o próprio dia. É preciso ter pelo menos 14 valores nessa janela.
- **Treino:** fica em minutos, sem z-score, porque a maioria dos dias tem zero. Os efeitos são reportados por 30 min.

### Modelos

- **Diárias:** `y(t) = a + b·x + c·y(t−1) + erro`, por mínimos quadrados e com erros robustos à autocorrelação (Newey-West, 7 dias de lag). O termo `y(t−1)` controla o estado da noite anterior.
- **Esteira:** `fc_10_15 = a + b·x + c·ordem da sessão + d·pre_exercicio + erro`, com erros robustos HC3. O modelo fica pequeno porque há poucas sessões.

### Critérios definidos antes dos resultados

**Hipótese diária sustentada**, se todas estas condições valerem:

1. q abaixo de 0,10 na correção de Benjamini-Hochberg, entre as 5 hipóteses;
2. intervalo de 95% sem o zero também no bootstrap em blocos de 7 dias;
3. mesmo sinal sem o termo `y(t−1)` e na correlação de Spearman.

**Sinal exploratório na esteira**, se o intervalo de 95% não incluir o zero nas três bases e nos dois limiares alternativos. A esteira nunca gera conclusão: um sinal só vira hipótese para testar com as sessões futuras, que têm carga registrada e são independentes destas.

Um resultado que não cumpra os critérios é reportado como não sustentado, inclusive na apresentação final.

### Testes de sensibilidade

- **H1 a H3:** repetidas com `min_fc_acima_limiar` no lugar dos minutos de treino.
- **H6 a H10:** repetidas em todas as sessões, sem carga incerta, na base estrita e com o limiar 5 bpm abaixo e acima.

## O que fica de fora

- **Scores da Samsung:** nenhuma hipótese usa colunas `sam_`, para evitar a circularidade com os próprios insumos.
- **Passos:** refletem o tempo com o relógio no pulso, não a atividade do dia.
- **Velocidade e VO2:** não há registro no histórico, e a velocidade nunca é inferida da FC.
- **RPE:** fica para a parte 2.

## Análise exploratória

Uma matriz de correlações, com lags de 0 a 2 dias, será apresentada à parte e rotulada como exploratória. Ela serve para gerar perguntas, não para confirmar achados.

## Limites da interpretação

Os dados são observacionais e de uma só pessoa. Mesmo um resultado sustentado indica associação nesta pessoa e neste período. Fatores não medidos, como calor, cafeína, doença, álcool e estresse, podem explicar parte dos efeitos. Na esteira, a carga real do histórico é desconhecida e funciona como variável omitida.
