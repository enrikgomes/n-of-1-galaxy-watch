# Dados públicos

Esta é a única pasta de dados do repositório. Os dados brutos e processados ficam fora do git.

O prefixo do arquivo indica a origem:

- **`real_`**: agregados calculados a partir dos dados reais.
- **`sintetico_`**: dados inventados, gerados sem ler os dados reais. Servem para demonstrar o método e não dizem nada sobre a pessoa do projeto.

## Regras dos arquivos `real_`

O comando `python -m src.publico.gerar` bloqueia a publicação se um arquivo:

- tiver datas, identificadores ou nome de usuário;
- tiver colunas com valores absolutos de saúde;
- tiver um grupo com menos de 5 observações.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `real_hipoteses_diarias.csv` | Efeitos, intervalos e veredito de H1 a H5 |
| `real_hipoteses_esteira.csv` | Efeitos de H6 a H10 em cada base de sessões |
| `real_sensibilidade.csv` | H1 a H3 com minutos de FC acima do limiar |
| `real_placebo.csv` | Teste placebo, posterior aos resultados |
| `real_dose_resposta.csv` | Média da noite seguinte por faixa de treino, em desvios padrão; descritivo |
| `real_perfil_sessao.csv` | Variação da FC ao longo da sessão, em relação aos minutos 9 e 10 |
| `real_matriz_exploratoria.csv` | Correlações com lags de 0 a 2 dias; só exploratório |
| `real_funil.csv` | Sessões em cada filtro e marcação |
| `real_leitura.csv` | Linhas e colunas de cada tabela na leitura dos CSVs |
| `real_comparacao_leitura.csv` | Linhas corretas na leitura padrão e no leitor do projeto |
| `real_validacao_alinhamento.csv` | Correlações que validam o alinhamento das noites |
| `sintetico_diario.csv` | 360 dias inventados, com as colunas usadas na análise |
| `sintetico_sessoes_fc.csv` | Duas sessões inventadas, minuto a minuto |

## Cuidados de leitura

- Em `real_perfil_sessao.csv`, a base "Sem carga incerta" exclui sessões com queda de FC. Por isso, a subida ao longo da sessão tende a parecer maior nela.
- Os dados sintéticos têm efeitos escolhidos para serem fáceis de ver, de 1 bpm e −3 ms por 30 min de treino. Eles não são estimativas reais.
