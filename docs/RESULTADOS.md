# Resultados da parte 1

As hipóteses, o método e os critérios estão em [HIPOTESES.md](HIPOTESES.md) e foram registrados no git antes destes resultados. Os dados são observacionais e de uma só pessoa: tudo aqui indica associação, nesta pessoa e neste período, não causa.

Código: [`src/analysis/hipoteses.py`](../src/analysis/hipoteses.py).

## Resumo

| ID | Pergunta | Esperado | Efeito (IC de 95%) | q | Veredito |
|---|---|---|---|---:|---|
| H2 | Treino → FC da noite seguinte | + | +0,19 dp por 30 min (0,07 a 0,32) | 0,013 | **Sustentada** |
| H1 | Treino → RMSSD da noite seguinte | − | −0,13 dp por 30 min (−0,25 a −0,01) | 0,064 | **Sustentada**, no limite |
| H4 | Sono → RMSSD da noite seguinte | + | −0,12 dp por 1 dp de sono (−0,23 a −0,01) | 0,064 | **Cumpre os critérios, com sinal contrário e frágil** |
| H3 | Treino → tempo dormido na noite seguinte | Sem expectativa | −0,03 dp por 30 min (−0,17 a 0,10) | 0,623 | Não sustentada |
| H5 | Dormir mais tarde → RMSSD da mesma noite | − | +0,04 dp por 1 dp de horário (−0,08 a 0,15) | 0,623 | Não sustentada |

"dp" é o desvio padrão em relação aos 28 dias anteriores. Cada modelo diário usou 267 dias.

Nenhuma das cinco hipóteses da esteira gerou sinal exploratório.

## Hipóteses diárias

### H2: mais treino, FC noturna mais alta

É o resultado mais sólido. Ele cumpre todos os critérios, e o teste com minutos de FC acima do limiar vai na mesma direção, com intervalo sem o zero. O tamanho é pequeno: cerca de **0,6 bpm por 30 min de treino** (0,2 a 0,9).

### H1: mais treino, VFC noturna mais baixa

Cumpre os critérios, mas sem folga: o intervalo do bootstrap termina em −0,009. O efeito é de cerca de **1 ms de RMSSD por 30 min de treino**. No teste com minutos de FC acima do limiar, o sinal se mantém, mas o intervalo inclui o zero (−1,14 a 0,73).

### H4: o resultado que contrariou a expectativa

Esperávamos que dormir mais aumentasse o RMSSD da noite seguinte. O coeficiente saiu negativo, e pelos critérios definidos a hipótese é reportada como cumprida, mas a leitura correta é de **fragilidade**:

- Sem o controle `y(t−1)`, o efeito praticamente some: −0,04 (−0,16 a 0,09).
- A correlação simples entre as duas variáveis é de só −0,04.
- O efeito só aparece ao controlar o RMSSD da noite anterior, que tem correlação de +0,22 com o sono dessa mesma noite.

Isso é compatível com um artefato do controle, e não há base aqui para dizer que dormir mais reduz a VFC. Os critérios não incluíam o sinal esperado, e não foram alterados depois de ver o resultado. Eles poderiam ter exigido um efeito estável sem o controle.

### O efeito não parece crescer com a dose

Os modelos de H1 e H2 supõem que cada 30 min a mais somam o mesmo efeito. A média da noite seguinte por faixa de treino não confirma isso. A tabela é descritiva, sem controles, e foi calculada depois dos resultados:

| Treino no dia | Dias | FC da noite seguinte (dp) | VFC da noite seguinte (dp) |
|---|---:|---:|---:|
| Sem treino | 159 | −0,14 (−0,32 a 0,03) | +0,11 (−0,05 a 0,28) |
| Até 30 min | 14 | +0,74 (0,15 a 1,33) | −0,21 (−0,78 a 0,35) |
| 31 a 60 min | 79 | +0,20 (−0,06 a 0,47) | −0,16 (−0,42 a 0,10) |
| Mais de 60 min | 29 | +0,16 (−0,19 a 0,51) | −0,07 (−0,42 a 0,28) |

A diferença parece estar entre treinar e não treinar, sem aumento claro com a duração. Por isso, "0,6 bpm por 30 min" e "1 ms por 30 min" devem ser lidos como resumos do modelo linear, não como uma dose comprovada. Os grupos são desiguais, e a duração não mede a intensidade: uma sessão curta pode ser mais intensa que uma longa.

### H3 e H5

Não há evidência de associação. Com cerca de 267 dias, isso torna improváveis efeitos grandes, mas não exclui efeitos pequenos.

## Hipóteses da esteira

Nenhuma hipótese teve intervalo sem o zero em qualquer das cinco bases: todas as sessões, sem carga incerta, base estrita e limiar 5 bpm abaixo e acima.

| ID | Explicativa | Unidade | Todas (n) | Sem carga incerta (n) | Base estrita (n) |
|---|---|---|---|---|---|
| H6 | Tempo dormido | bpm por 1 dp | +1,0 (−3,3 a 5,2; 33) | +1,0 (−2,1 a 4,1; 20) | +1,4 (−2,0 a 4,8; 16) |
| H7 | RMSSD | bpm por 1 dp | +1,2 (−1,5 a 3,9; 33) | −1,2 (−4,3 a 1,9; 20) | −1,1 (−4,2 a 2,0; 16) |
| H8 | FC noturna | bpm por 1 dp | −2,1 (−4,5 a 0,2; 33) | 0,0 (−3,3 a 3,2; 20) | +0,5 (−3,2 a 4,3; 16) |
| H9 | Horas desde o despertar | bpm por hora | −0,6 (−3,1 a 1,8; 34) | −1,0 (−2,8 a 0,7; 20) | −1,3 (−3,1 a 0,6; 16) |
| H10 | Treino do dia anterior | bpm por 30 min | −1,3 (−7,1 a 4,6; 34) | −4,2 (−9,6 a 1,2; 20) | −4,5 (−11,8 a 2,9; 16) |

**Isso não prova ausência de efeito.** Os intervalos são largos: em H10, por exemplo, eles chegam a efeitos maiores que a diferença de cerca de 10 bpm estimada entre 3,5 e 4 km/h. A carga real do histórico é desconhecida, e o sinal de H7 muda conforme a base. As sessões futuras, com carga registrada, permitem um teste melhor.

## Checagem posterior aos resultados

Este teste placebo **não estava na lista**. O treino de um dia acontece depois da noite que termina naquele dia, então não deveria explicá-la.

| Resposta | Efeito do treino de D na noite que termina em D (IC de 95%) | p |
|---|---|---:|
| RMSSD | +0,04 (−0,11 a 0,19) | 0,635 |
| FC noturna | −0,06 (−0,20 a 0,08) | 0,401 |

Não há efeito, o que favorece H1 e H2. O teste não descarta outros fatores: um dia de treino pode vir com outras mudanças na rotina.

## Matriz exploratória

São 330 pares, com lags de 0 a 2 dias e correlação de Spearman, com amostra efetiva ajustada pela autocorrelação. 40 pares ficaram com q abaixo de 0,10: 22 da mesma noite, 13 com lag de 1 dia e 5 com lag de 2 dias.

- **Mesma noite:** boa parte é mecânica. O tempo na cama, por exemplo, quase determina o tempo dormido. Esses pares não trazem descoberta.
- **Perguntas para o futuro:** treinar em um dia se associa a dormir mais cedo na noite seguinte (ρ = −0,19). Dormir mais tarde se associa a FC menor na noite seguinte (ρ = −0,25).

Esses pares foram escolhidos depois de ver os dados, por isso só servem como perguntas para testar depois.

## Detalhes de execução

Decisões tomadas ao implementar, que o documento de hipóteses não especificava:

- **Amostra:** os modelos diários têm 267 dias, e não os 255 a 269 da lista, porque a contagem anterior não exigia o valor de `y(t−1)`.
- **Dias faltantes:** o Newey-West trata as linhas restantes como consecutivas. O bootstrap sorteia blocos do calendário e não tem esse limite.
- **`pre_exercicio`:** sai do modelo da esteira quando a base tem menos de 2 sessões com a marcação, porque o erro HC3 fica indefinido.
- **Intervalos na esteira:** usam a distribuição t, mais adequada a amostras pequenas.
- **Limiares alternativos:** os resultados com o limiar 5 bpm acima coincidem com os da base sem carga incerta, porque as marcações de queda e alta já cobrem as sessões afetadas.

## Como reproduzir

```bash
python -m src.analysis.hipoteses
```

O comando exige as tabelas de `data/processed/`. Os testes em `tests/test_hipoteses.py` verificam em dados sintéticos se o método recupera efeitos conhecidos e controla falsos positivos.
