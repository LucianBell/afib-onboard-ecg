# Registro de decisões e desvios

Cada entrada: data, decisão, motivo. Decisões que dependem de resultados de validação
são marcadas como **pendente** até a etapa correspondente.

## Etapa 1 — estrutura e ambiente (2026-11-03)

- **D1. Ambiente.** Conda env `afib-onboard` com Python 3.12, versões fixadas em `requirements.lock`
  (`pip freeze`). O Python do conda base é 3.14 e não tinha a pilha científica instalada; 3.12 tem
  rodas estáveis para todas as dependências (LightGBM, ONNX Runtime, wfdb) e roda no Raspberry Pi OS.
- **D2. Semente global** `20261114` em `configs/default.yaml`.
- **D3. Licença do código MIT.** Os dados não são redistribuídos. Ambas as bases são CC BY 4.0, que
  permite trabalho derivado com atribuição (ver `DATA.md`).

## Etapa 2 — dados e auditoria (2026-11-03)

- **D4. Versões.** Chapman `ecg-arrhythmia` 1.0.0 (única versão) e PTB-XL 1.0.3 (a mais recente na
  PhysioNet em 2026-11-03). Bases completas, sem subconjunto: disco (318 GB livres) e RAM (7,5 GB)
  bastam, desde que só a derivação I seja mantida em cache.
- **D5. Integridade.** Os zips são conferidos pelo tamanho esperado (servidor) e cada arquivo
  extraído contra o `SHA256SUMS.txt` distribuído pela PhysioNet. Os hashes dos zips vão para
  `results/audit/data_manifest.json`.
- **D6. Unidades.** A conversão para mV usa ganho e baseline de cada cabeçalho WFDB
  (`(d - baseline) / adc_gain`). O Anexo A do TCC não é usado. A auditoria confere empiricamente a
  escala pela amplitude do QRS (seção 4 de `data_audit.md`).
- **D7. Dicionários de rótulos lidos dos arquivos.** `ConditionNames_SNOMED-CT.csv` (Chapman) e
  `scp_statements.csv` (PTB-XL). O config lista só acrônimos, e `check_config_acronyms` falha se
  algum não existir no dicionário. Observação: no arquivo da Chapman alguns códigos SNOMED repetem
  entre acrônimos (`195101003` = SAAWR e WAVN; `164909002` = LBBB/LBBBB/LFBBB; `164865005` = MI e
  variantes; `698252002` = IDC/IVB). Por isso o mapeamento é código → lista de acrônimos.
- **D8. Regras de agrupamento** (`src/labels.py::assign_group`, com testes em `tests/test_labels.py`):
  - um registro precisa de exatamente um ritmo primário; sem ritmo → `SEM_RITMO` (excluído);
  - AFIB + outro ritmo primário → `CONFLITO`; AFIB + bloqueio AV/PR longo → `CONFLITO`, porque
    intervalo PR não existe em AFIB; AFIB + ectopia → `AFIB`; AFIB + pré-excitação → `FORA_DE_TREINO`;
  - ritmo sinusal com ectopia (APB/VPB/PVC/PAC/bigeminismo…), bloqueio AV (inclui `PRIE`/`LPR`,
    PR prolongado, por coerência com 1AVB) ou pré-excitação → `FORA_DE_TREINO`, conforme o briefing
    (seção 5). Ficam para o teste de estresse (experimento G);
  - `BIGU`/`TRIGU` do PTB-XL (enunciados de "ritmo" no `scp_statements.csv`) são tratados como ectopia,
    pois descrevem bigeminismo/trigeminismo sobre um ritmo de base; sem ritmo de base, mas com
    ectopia/bloqueio AV → `FORA_DE_TREINO`;
  - SR+SB → `SINUS_BRADY`; SR+ST → `SINUS_TACHY`; SB+ST → `CONFLITO`;
  - `SINUS_NORMAL`: Chapman = SR sem nenhum outro diagnóstico; PTB-XL = SR + `NORM` com
    probabilidade 100 e nenhum outro enunciado (mesmo critério de NORM do TCC);
  - `SINUS_OUTRO` (novo, fora da tabela do briefing): SR com achados não rítmicos (ex.: alteração de
    onda T, desvio de eixo, bloqueio de ramo).
  - `SINUS_ARRITMIA` (novo): arritmia/irregularidade sinusal (`SA` na Chapman, `SARRH` no PTB-XL).
    É sinusal, mas tem RR irregular, um confundidor direto para AFIB. Fica em grupo próprio.
- **D9. Resolvido em 2026-11-03:** `SINUS_OUTRO` entra nos negativos (usuário mandou seguir sem objeção à
  recomendação abaixo). Texto original: definir se `SINUS_OUTRO` entra nos negativos do treino.
  Recomendação: incluir, porque os positivos de AFIB também carregam achados morfológicos. Treinar
  só com sinusal "limpo" ensinaria o modelo que morfologia anormal = AFIB. `SINUS_NORMAL` continua
  como subgrupo de relato. `SINUS_ARRITMIA` entra como negativo de estresse no teste.
- **D10. Faixa etária "próxima à de astronautas"** = 30–55 anos, escolha operacional para a análise
  de subgrupos (não é dado oficial da NASA).
- **D11. Medida de amplitude da auditoria:** mediana, sobre janelas de 1 s, do pico-a-pico após
  passa-alta Butterworth de 0,5 Hz (ordem 2, `sosfiltfilt`). Serve só para conferir escala; não faz
  parte do pré-processamento do modelo.

## Etapa 2 — achados da auditoria e ajustes de desenho (2026-11-03)

- **D12. A Chapman tem duas fontes.** Shaoxing = JS00001–JS10646 (10.247 registros presentes) e Ningbo =
  JS10647 em diante (34.905). O cabeçalho não informa a origem. A fronteira foi inferida e conferida contra as
  contagens por fonte das tabelas do CinC 2021: 93 de 94 códigos idênticos. Ver `data_audit.md` §2.1. A coluna
  `source` do índice usa `chapman_source()`.
- **D13. Desvio do briefing (experimento A): só Shaoxing.** O briefing pede "AFIB vs. sinusal dentro da
  Chapman, tudo da mesma fonte". Como Ningbo tem zero AFIB, usar a Chapman inteira faria a fonte prever o
  rótulo. O experimento A usa só Shaoxing (1.779 AFIB, 6.669 sinusais). Ningbo entra apenas: (i) no
  experimento C, como teste de assinatura de fonte (sinusal Shaoxing vs. sinusal Ningbo); (ii) como conjunto
  extra de falso AFIB em bradi/taqui sinusal (experimento E), sempre relatado à parte.
- **D14. "Flutter" de Ningbo excluído.** O código de flutter em Ningbo tem forte indício de ser AFIB
  (12 de 12 cópias idênticas de AFIB de Shaoxing). Fica fora de treino e teste principais. O teste de flutter
  (experimento G) usa só o flutter de Shaoxing e o `AFLT` do PTB-XL. Uma análise de sensibilidade opcional
  pode tratá-lo como grupo "rótulo duvidoso".
- **D15. Sem afirmação sobre TV/FV.** Os rótulos de TV/FV existem só em Ningbo, via dicionário complementar,
  e a "TV paroxística" coincide com SVT de Shaoxing em 21 de 26 cópias. Não serão usados para afirmar
  detecção. O PTB-XL não tem ritmo ventricular.
- **D16. Duplicatas.** Remover duplicatas exatas (hash do sinal) antes de qualquer divisão, mantendo uma
  cópia por hash e preferindo a de Shaoxing. Se as cópias tiverem grupos diferentes, vale o rótulo de
  Shaoxing (ver D14).
- **D17. Dicionário complementar.** Tabelas `dx_mapping_scored/unscored.csv` do PhysioNet/CinC Challenge
  2021 (BSD-2-Clause), fixadas no commit `e2a75fc`, com hash em `data_manifest.json`. Só resolvem códigos
  ausentes do dicionário oficial. Os 43 códigos desconhecidos foram todos resolvidos.
- **D18. Idade.** PTB-XL 300 → 90 ("≥ 90", anonimização). Ningbo 0 → ausente: são 247 registros com 0 e
  nenhum com 1–3 anos. Regra em `src.data.clean_age`.
- **D19. Divisão sem paciente na Chapman.** Não há identificador de paciente, então a divisão de Shaoxing é
  por registro, após a deduplicação (D16). É uma limitação declarada: registros diferentes de um mesmo
  paciente podem cair em treino e teste. O PTB-XL usa `strat_fold`, que respeita paciente.

## Etapas 3 e 4 — pré-processamento, atributos, SQI e baseline (2026-11-03)

- **D20. Ordem do pré-processamento (desvio do briefing).** O briefing lista notch → passa-banda →
  reamostragem. Aqui a reamostragem 500 → 250 Hz (`resample_poly`, com anti-aliasing) vem primeiro, e o recorte
  de 2.400 amostras vem antes dos filtros. Assim o caminho de treino e o do aparelho, que já entrega janelas de
  2.400 amostras a 250 Hz, executam exatamente a mesma função (`preprocess_window`). Os filtros seguem o
  briefing: notch 50 Hz (Q = 30) e Butterworth 0,05–30 Hz de ordem 4 em SOS com `sosfiltfilt`.
  Normalização: mediana zero e escala robusta (p99 − p1) = 1, por janela. Não há escalonamento global.
- **D21. Recorte central** para atributos e avaliação. O registro tem 2.500 amostras a 250 Hz e a janela 2.400,
  então o recorte aleatório desloca no máximo 0,4 s e não acrescenta diversidade aos atributos. Aleatório só no
  treino da CNN.
- **D22. LOESS e interpolação cúbica do TCC (ablação opcional): não feitos nesta etapa.** O passa-banda de
  30 Hz já suaviza, e os atributos principais (RR) dependem só do QRS. Fica registrado como não testado.
- **D23. Detector de QRS** (`src/qrs.py`): Pan-Tompkins simplificado, só numpy/scipy. Validação em dados reais
  (`results/qrs_validation.json`, 150 registros por grupo e fonte): contra o XQRS do wfdb, sensibilidade ≥ 0,992
  e PPV ≥ 0,982 em todos os grupos, inclusive AFIB. A comparação começa no 1º batimento do XQRS, porque antes
  disso quase todas as discordâncias eram o período de aprendizado dele. A FC estimada bate com o rótulo em
  98–99,5% das bradi e taquicardias.
- **D24. SQI inicial** (`src/sqi.py`, limiares em `configs/default.yaml`): linha plana, saturação, número de
  batimentos, FC plausível, concordância entre dois detectores (bSQI) e curtose. Reprova 3–5% das janelas
  clínicas, sem diferença relevante entre AFIB e sinusal (`results/qrs_validation.json`). Os limiares serão
  calibrados no experimento F com ruído controlado. Até lá, ficam como valores iniciais.
- **D25. Baseline RR**: escore = nRMSSD (RMSSD / RR médio), sem treino. O limiar de decisão é escolhido na
  validação pela mesma regra dos modelos (especificidade ≥ 0,98), para a comparação ser justa.
- **D26. Janelas reprovadas pelo SQI ficam fora do treino e da avaliação principal**, porque no sistema elas
  viram `SINAL_RUIM` antes do modelo. A taxa de reprovação por classe é relatada, e as métricas sem o filtro
  de SQI são relatadas como análise secundária.

## Etapa 5 — experimento A (2026-11-03)

- **D27. Protocolo pré-registrado** (`configs/default.yaml`, seção `experiment_a`, commitado em `a03d09a`
  antes de qualquer treino):
  - dados: só Shaoxing (D13), positivos AFIB, negativos SINUS_NORMAL/OUTRO/BRADY/TACHY;
  - divisão 70/15/15 estratificada por grupo, com a semente global, depois da deduplicação (D16);
  - candidatos em ordem de simplicidade definida a priori: logreg < random_forest < lightgbm < cnn;
  - escolha pelo modelo mais simples com AUPRC de validação a no máximo **0,010** do melhor;
  - limiar: menor valor com especificidade ≥ 0,98 na validação, também para o baseline;
  - calibração Platt ajustada na validação.
- **D28. Ajuste de hiperparâmetros** por validação cruzada estratificada de 5 dobras no treino (AUPRC), em
  grades pequenas (`src/models.py::GRIDS`). A CNN (24.097 parâmetros) não passou por CV, pelo custo: usa
  parada antecipada em 10% do treino, sem tocar a validação, com recorte aleatório e ruído leve.
- **D29. Escolha (fase dev, antes do teste):** regressão logística. AUPRC de validação: logreg 0,9997,
  LightGBM 0,9997, RF 0,9980, CNN 0,9966. Na CV do treino a logística também ficou dentro da margem
  (0,9955 contra 0,9996 do LightGBM). `results/expA/selection.json` e `split.csv` são commitados antes de
  `exp_a.py test`, que se recusa a rodar sem isso e grava a trava `TEST_OPENED.json`.
- **D30. Limitação do desenho A (importante para interpretar números altos):** os negativos excluem por
  construção os confundidores mais difíceis (ectopia frequente, arritmia sinusal, flutter, bloqueios),
  que vão para os experimentos E e G. O teste A mede AFIB contra sinusal "limpo" de mesma fonte. Não é o
  desempenho em uso real.
- **D31. Incidente na abertura do teste (registro de transparência).** A primeira execução de
  `exp_a.py test` (02:31:39, commit `782757e`) calculou todas as métricas e quebrou ao gravar o JSON (chave
  em tupla num campo auxiliar). A trava já tinha sido gravada e as métricas impressas não foram guardadas.
  Corrigi só a serialização, sem tocar em modelos, limiares, divisão ou escolha, e reexecutei com
  `--force` às 02:32:42. Os dois registros estão em `TEST_OPENED.json`, com o mesmo hash de
  `selection.json`. O cálculo é determinístico (artefatos salvos, bootstrap com semente fixa), então a
  segunda execução reproduz a primeira. Nenhuma decisão foi tomada entre as duas.
- **D32. Leitura do resultado do teste A.** Os quatro modelos de ML ficaram empatados dentro dos ICs
  (AUPRC 0,997–1,000), em teto de desempenho. A escolha da logística, pela regra pré-registrada, se
  mantém. Contra o baseline RR, o ganho aparece no ranking (AUPRC 0,999 vs. 0,965). No ponto de operação,
  o McNemar não mostra diferença significativa (9 vs. 4 discordâncias, p = 0,27). O experimento D faz a
  comparação formal com bootstrap pareado.

## Etapa 6 — experimentos B a I (2026-11-03)

Regras fixadas e commitadas antes de rodar: `d1047fe` (INCERTO, N de M, SNR, TCC) e `473513c` (calibração
do SQI). Todos os resultados estão em `results/exp{B..I}/`, gerados por `make experiments`.

- **D33. INCERTO e votos.** O estado `INCERTO` vale quando a entrada está fora do padrão (Mahalanobis nos
  atributos imputados e padronizados, Ledoit-Wolf ajustado no treino de Shaoxing, limiar = quantil 99,5% da
  validação) ou quando a confiança é baixa (limiar ≤ prob < 0,50). Só janelas no estado `AFIB` votam na
  regra N de M. Ambas as regras foram definidas antes de rodar G e H.
- **D34. B, validação externa.** O modelo de Shaoxing, sem retreino, foi aplicado ao PTB-XL inteiro. A
  sensibilidade se mantém (1,000 → 0,990), mas a especificidade cai de 0,988 para 0,958 e o AUROC de 0,9998
  para 0,9968. O PPV cai de 0,956 para 0,677, em parte porque a prevalência é menor. No sentido inverso, o
  modelo treinado no PTB-XL generaliza bem para Shaoxing (AUROC 0,9995). Entre os candidatos de ML, a
  logística é a melhor externamente e a CNN a pior em AUROC: a escolha do modelo mais simples se sustentou.
- **D35. D, comparação com o baseline.** Em ranking, a logística é melhor nos dois testes (bootstrap pareado:
  ΔAUROC +0,005 em A e +0,011 em B; ΔAUPRC +0,034 e +0,178; todos com IC acima de 0). No ponto de operação
  transferido de Shaoxing, porém, **no PTB-XL o baseline erra menos** (621 contra 689 erros; McNemar
  p = 0,003), porque a especificidade da logística cai mais. O limiar da logística (prob ≥ 0,0105) foi
  escolhido em Shaoxing, onde a separação é quase perfeita, e não transfere bem.
- **D36. C, confusão de fonte.** Com as unidades corretas e a mesma filtragem, a assinatura de base é
  moderada: os normais de Shaoxing e PTB-XL se separam com AUROC 0,86 pelos atributos de ritmo e 0,77 pelos
  descritores do sinal. Shaoxing contra Ningbo dá AUROC ≈ 0,50. Com a escala descrita no TCC (÷10³ contra
  ÷10), **só a amplitude separa as bases com AUROC 1,000**. Hipótese não testada: parte da separação pelos
  atributos de ritmo vem de convenções de rótulo de FC (18% dos "normais" do PTB-XL estão abaixo de 60 bpm,
  experimento E). No desenho do TCC, nossa logística não explora a fonte (AUROC alto também nos testes de
  mesma fonte). O modelo com descritores perde especificidade quando os negativos passam a ser de Shaoxing
  (0,896 → 0,786). C não incluiu CNN.
- **D37. F, calibração do SQI.** O SQI inicial quase não filtrava ruído muscular e movimento de eletrodo.
  Calibrei na validação com regra fixada antes (`473513c`): rejeição limpa ≤ 5% por classe e máxima
  especificidade sob ruído. Resultado: concordância entre detectores ≥ 0,95, curtose sem mudança. O ganho é
  modesto (especificidade com ruído muscular a 0 dB: 0,84 → 0,89; a −6 dB: 0,41 → 0,55), e o custo é a
  rejeição limpa passar de 3–4% para 6–8%. Adotado para o sistema a bordo (`sqi_onboard`). Os experimentos
  A–I mantêm o SQI inicial para reprodução.
- **D38. H, análises de sensibilidade acrescentadas depois do resultado principal.** A simulação principal
  trata as janelas como independentes e dá cerca de 0,01 falso alerta por dia com 3 de 3. Isso é otimista.
  Acrescentei, e declaro que foi depois: (a) erros correlacionados, com cada registro negativo repetido por
  cerca de 5 min; (b) pessoas cujo ritmo de base é ectopia frequente ou arritmia sinusal. Esses cenários dão
  de ~4 a 180 falsos alertas por dia (ver `monitoring_sensitivity.csv`).
- **D39. I, referência ao TCC.** Saída de 3 classes = logística (AFIB) + regra de FC (< 60 bpm → SB). O teste
  balanceado de Shaoxing tem 201 por classe, o máximo disponível no teste A. O do PTB-XL tem 356 por classe,
  o mesmo tamanho do TCC. Os números do TCC estão em `results/reference/tcc_reported.json`, transcritos das
  Tabelas 3 e 4.

## Etapas 7 e 8 — inferência a bordo, stream, benchmark e painel (2026-11-03)

- **D40. Artefato do modelo.** `models/afib_logreg_v1.json` (34 KB) traz os parâmetros em numpy puro:
  imputação com indicadores, padronização, coeficientes, Platt, limiar, detector fora-do-padrão, SQI de
  bordo, votação 3 de 3 e regra de FC. Inclui metadados: commit, regra de escolha e SHA-256 dos zips de dados.
  A inferência (`src/inference.py`) usa só numpy/scipy, sem scikit-learn. ONNX: o skl2onnx não converte o
  `SimpleImputer` com indicadores, então o grafo foi montado à mão (`models/afib_logreg_v1.onnx`, 0,8 KB).
  A diferença máxima contra o scikit-learn é de 3,3e-6 em 8.118 janelas, e o teste de paridade do JSON passa
  com tolerância de 1e-9.
- **D41. Estados.** `predict(window)` devolve o estado da janela (`AFIB` isolado ainda não é alerta).
  `Monitor.update` devolve os estados do sistema do briefing. Uma janela AFIB ainda não confirmada pela
  votação aparece como `INCERTO` com o motivo `afib_em_confirmacao`.
- **D42. Regra de FC com histórico pessoal.** Usa limiares absolutos (60/100 bpm) até haver 30 janelas
  sinusais com sinal bom. Depois, FC baixa < min(60, 0,8 × mediana pessoal) e FC alta > max(100, 1,5 ×
  mediana pessoal). O histórico inclui janelas com aviso de FC, senão um atleta com FC de repouso baixa nunca
  sairia do aviso (bug achado em teste e corrigido). Esses fatores são escolhas de projeto, não validadas
  clinicamente.
- **D43. Comportamento conhecido da votação.** Uma janela `SINAL_RUIM` conta como não-voto, como no
  experimento H. Durante AFIB, uma janela ruim no meio interrompe a condição 3 de 3, e o mesmo episódio pode
  gerar mais de um alerta (visto no painel). Alternativa candidata: ignorar janelas ruins na votação. Exige
  reavaliar o H antes de adotar.
- **D44. Demonstração.** O replay usa 40 registros por cenário do teste A (Shaoxing, nunca vistos no treino),
  em `data/demo/`, fora do Git, gerado por `make demo-data`. O cenário "sinal ruim" usa ruído real da NSTDB a
  −6 dB e eletrodo solto. Parte dessas janelas passa pelo SQI, como no experimento F, e isso não foi
  escondido. Sem as bases baixadas, o painel e o stream usam ECG sintético, com faixa própria. O Streamlit
  roda local (`.streamlit/config.toml`: sem telemetria, localhost, tema claro com o azul de série como cor
  primária, já que o vermelho é reservado ao alerta). Testes: `tests/test_dashboard.py` (AppTest). A
  verificação sem rede foi feita com `unshare -rn` para testes, stream e benchmark, e a página foi conferida
  em Firefox headless.
- **D45. Benchmark.** `results/benchmark/benchmark_LucianDebian.json`, medido no i7-1165G7 desta máquina com
  1 thread. **Não há medição em Raspberry Pi**: o script está pronto para rodar lá (identifica a placa pelo
  campo `Model` do /proc/cpuinfo).
