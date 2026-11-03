# Detector de fibrilação atrial a bordo para astronautas

**NASA Space Apps Challenge 2026 · protótipo de pesquisa** · [English version](README.en.md)

> **Não é dispositivo médico nem diagnóstico.** Este é um protótipo de pesquisa e apoio à decisão. Não foi
> validado em astronautas, em microgravidade nem com um Holter real. Todos os dados são ECGs clínicos,
> públicos, terrestres e de repouso, obtidos na PhysioNet. **Não são dados da NASA nem de astronautas.**

*Este README é gerado por `make report` a partir de `docs/templates/README.pt.template.md`. Todo número abaixo
vem de um arquivo em `results/` ou, quando é constante de projeto, de `configs/default.yaml`. A origem de cada
valor está em [`results/readme_numbers.json`](results/readme_numbers.json), e um teste automático impede
números escritos à mão.*

---

## Em uma frase

Um programa leve que roda num Raspberry Pi ligado a um ECG portátil de uma derivação (como um Holter). Ele
analisa o sinal em janelas de {{win_s}} s **durante a gravação, sem depender da Terra**, e avisa quando
encontra **fibrilação atrial (AFIB)**, controlando os falsos alarmes.

## Por que fibrilação atrial, e por que a bordo

- Uma revisão das Academias Nacionais dos EUA sobre os relatórios de risco à saúde da NASA concluiu que
  "a greater emphasis in the evidence report on the risk of atrial fibrillation is supported by contemporary
  experience", e que o manejo de AFIB surgida em voos longos precisa ser estudado (relatório de 2017).
- Khine et al. (2018) relatam prevalência de AFIB de cerca de {{lit_khine_prev}} em astronautas ativos,
  semelhante à da população geral, mas em idade mais jovem, e aumento transitório do átrio esquerdo após
  {{lit_khine_months}} meses no espaço. **O mesmo estudo não observou nenhum episódio de AFIB em voo.** O
  argumento, portanto, é de risco, não de AFIB frequente em órbita.
- A AFIB costuma ser intermitente ou sem sintomas, então um alerta automático tem valor. Ela é detectável numa
  única derivação. Em missões longas, a análise precisa acontecer localmente.

Fontes conferidas no original: `results/reference/literature.json`.

## Como funciona

O sinal-alvo é o do aparelho MP-IoT do TCC de partida: derivação I, {{fs}} Hz, janelas de {{win}} amostras,
banda de {{band_lo}} a {{band_hi}} Hz e conversor A/D de {{adc_bits}} bits que só gera valores positivos. Cada
janela passa por três camadas:

1. **Qualidade do sinal (SQI).** Janela ruim → `SINAL_RUIM`, sem mensagem clínica.
2. **Modelo de ML: AFIB vs. ritmo sinusal.** Regressão logística sobre {{n_feat}} atributos interpretáveis:
   irregularidade dos intervalos RR, atividade atrial (onda P), morfologia do QRS e espectro. Bradicardia e
   taquicardia sinusais entram no treino como *não AFIB*, para ensinar que só a frequência alterada não é
   fibrilação. Fora da base de treino, porém, ele ainda as confunde com mais frequência (experimento E). O
   detector de QRS, feito para ser leve, concorda com a referência XQRS do `wfdb` em dados reais
   (sensibilidade ≥ {{qrs_sens_min}}, PPV ≥ {{qrs_ppv_min}}).
3. **Regra de frequência cardíaca.** Gera `AVISO_FC_BAIXA` / `AVISO_FC_ALTA`, avisos leves. Os limiares
   padrão são {{brady}} e {{tachy}} bpm, adaptados ao histórico da própria pessoa, para que um atleta com FC
   de repouso baixa não receba aviso o tempo todo.

Por cima das camadas:

| Estado | Quando | Severidade |
|---|---|---|
| `SINAL_RUIM` | SQI reprovado | técnica |
| `INCERTO` | entrada fora do padrão do treino, ou confiança baixa | revisar |
| `ALERTA_AFIB` | AFIB em {{vote_n}} de {{vote_m}} janelas consecutivas | alta |
| `AVISO_FC_BAIXA` / `AVISO_FC_ALTA` | FC fora dos limiares, sem AFIB | leve |
| `OK` | ritmo sinusal, FC esperada | nenhuma |

**O que alegamos:** *detecção precoce do ritmo presente na janela* (não previsão de eventos futuros), análise
**a bordo durante o registro** e comparação justa com um baseline no mesmo conjunto de teste. **O que não
alegamos:** detectar infarto, parada cardíaca ou arritmias ventriculares, nem ser "melhor que o Holter".

**Ponto de partida:** o TCC de Maggioni & Rebonatto (UPF, 2023), em [`docs/`](docs/). Reaproveitamos as bases
e o cenário de sinal limitado, trocamos a rede profunda por modelos simples e corrigimos os problemas de
avaliação (ver [`docs/tcc_analysis.md`](docs/tcc_analysis.md)).

## Dados

Auditoria completa: [`docs/data_audit.md`](docs/data_audit.md).

| Fonte | Registros | AFIB | Papel |
|---|---|---|---|
| Chapman-Shaoxing (parte da *ecg-arrhythmia* v1.0.0, PhysioNet) | {{sh_total}} | {{sh_afib}} | treino e teste interno (exp. A) |
| Ningbo (mesma publicação) | {{nb_total}} | {{nb_afib}} | teste de assinatura de fonte; negativos extras |
| PTB-XL v1.0.3 | {{ptb_total}} | {{ptb_afib}} | **validação externa** (exp. B) |

Achados da auditoria que mudaram o desenho:

- **A base "Chapman" junta dois hospitais, e toda a AFIB está em Shaoxing; Ningbo não tem nenhuma.**
  Inferimos a fronteira e a conferimos contra as contagens por fonte do PhysioNet/CinC 2021 ({{bnd_eq}} de
  {{bnd_cmp}} códigos idênticos). Usar a base inteira faria o modelo aprender o *hospital* em vez da
  arritmia, o mesmo erro central que encontramos no TCC. Por isso o treino usa só Shaoxing.
- **O rótulo "flutter atrial" de Ningbo não é confiável:** {{dup_afib_af}} sinais rotulados AFIB em Shaoxing
  aparecem, idênticos bit a bit, como flutter em Ningbo.
- {{supp_recs}} registros usam códigos SNOMED ausentes do dicionário oficial. Foram resolvidos com as
  tabelas do CinC 2021; sem isso, ritmos de marcapasso e juncionais seriam contados como sinusais normais.
- As unidades foram lidas dos cabeçalhos WFDB e conferidas empiricamente (QRS em mV plausíveis).

## Resultados

Todos os números são **por janela de {{win_s}} s**, com IC 95% por bootstrap quando indicado. Os limiares
foram escolhidos na validação de Shaoxing (especificidade ≥ {{min_spec}}) e **congelados** antes de abrir
qualquer conjunto de teste. Tabelas completas em `results/exp*/`.

### Teste interno (experimento A, Shaoxing, mesma fonte)

São {{a_n}} janelas, {{a_pos}} com AFIB ({{a_prev}} de prevalência). Os negativos são ritmo sinusal "limpo":
normal, com outros achados, bradi e taqui. Os confundidores difíceis são testados à parte (experimentos E e G).

| Modelo | AUROC | AUPRC [IC 95%] | Sensibilidade [IC 95%] | Especificidade [IC 95%] | PPV |
|---|---|---|---|---|---|
| Baseline de irregularidade RR (nRMSSD, sem aprendizado) | {{a_baseline_rr_auroc}} | {{a_baseline_rr_auprc}} [{{a_baseline_rr_auprc_ci}}] | {{a_baseline_rr_sens}} [{{a_baseline_rr_sens_ci}}] | {{a_baseline_rr_spec}} [{{a_baseline_rr_spec_ci}}] | {{a_baseline_rr_ppv}} |
| **Regressão logística (escolhida)** | {{a_logreg_auroc}} | {{a_logreg_auprc}} [{{a_logreg_auprc_ci}}] | {{a_logreg_sens}} [{{a_logreg_sens_ci}}] | {{a_logreg_spec}} [{{a_logreg_spec_ci}}] | {{a_logreg_ppv}} |
| Random Forest | {{a_random_forest_auroc}} | {{a_random_forest_auprc}} [{{a_random_forest_auprc_ci}}] | {{a_random_forest_sens}} [{{a_random_forest_sens_ci}}] | {{a_random_forest_spec}} [{{a_random_forest_spec_ci}}] | {{a_random_forest_ppv}} |
| LightGBM | {{a_lightgbm_auroc}} | {{a_lightgbm_auprc}} [{{a_lightgbm_auprc_ci}}] | {{a_lightgbm_sens}} [{{a_lightgbm_sens_ci}}] | {{a_lightgbm_spec}} [{{a_lightgbm_spec_ci}}] | {{a_lightgbm_ppv}} |
| CNN 1D compacta (referência) | {{a_cnn_auroc}} | {{a_cnn_auprc}} [{{a_cnn_auprc_ci}}] | {{a_cnn_sens}} [{{a_cnn_sens_ci}}] | {{a_cnn_spec}} [{{a_cnn_spec_ci}}] | {{a_cnn_ppv}} |

**Escolha do modelo (pré-registrada):** o mais simples cujo AUPRC de validação esteja a no máximo {{margin}}
do melhor, na ordem logística → Random Forest → LightGBM → CNN. AUPRC de validação: logística {{val_logreg}},
RF {{val_random_forest}}, LightGBM {{val_lightgbm}}, CNN {{val_cnn}} → **{{chosen}}**. A regra e a escolha
foram commitadas antes de abrir o teste (`results/expA/selection.json`, `results/expA/TEST_OPENED.json`).
Os números internos estão perto do teto porque os negativos são sinusal limpo de uma única fonte. O número
que importa é o externo.

### Validação externa (experimento B): treino em Shaoxing, teste no PTB-XL inteiro

![interno vs externo](results/figures/fig_internal_vs_external.png)

| Treino → teste | AUROC | Sensibilidade | Especificidade | PPV | AFIB / não AFIB |
|---|---|---|---|---|---|
| Shaoxing → Shaoxing (interno) | {{a_logreg_auroc}} | {{a_logreg_sens}} | {{a_logreg_spec}} | {{a_logreg_ppv}} | {{a_pos}} / – |
| **Shaoxing → PTB-XL (externo)** | **{{ext_auroc}}** [{{ext_auro_ci}}] | **{{ext_sens}}** [{{ext_sens_ci}}] | **{{ext_spec}}** [{{ext_espe_ci}}] | **{{ext_ppv}}** | {{ext_pos}} / {{ext_neg}} |
| PTB-XL → PTB-XL (fold {{inv_fold}}) | {{inv_ptb_auroc}} | {{inv_ptb_sens}} | {{inv_ptb_spec}} | {{inv_ptb_ppv}} | {{inv_ptb_pos}} / {{inv_ptb_neg}} |
| PTB-XL → Shaoxing (inverso) | {{inv_sh_auroc}} | {{inv_sh_sens}} | {{inv_sh_spec}} | {{inv_sh_ppv}} | {{inv_sh_pos}} / {{inv_sh_neg}} |

- **Queda de A para B:** a sensibilidade se mantém, mas **a especificidade cai de {{a_logreg_spec}} para
  {{ext_spec}}**, cerca de {{ext_fp_x}}× mais janelas falso-positivas. O PPV também cai, em parte porque a
  prevalência no PTB-XL é menor ({{ext_prev}}).
- **Entre os modelos,** a regressão logística generalizou pelo menos tão bem quanto os mais complexos (AUROC
  externo {{b_logreg_auroc}}, contra {{b_random_forest_auroc}} do RF e {{b_lightgbm_auroc}} do LightGBM, com ICs
  sobrepostos) e melhor que a CNN ({{b_cnn_auroc}}).
- **A calibração não se transfere:** o ECE externo geral é {{cal_ext_ece}}, mas janelas do PTB-XL com
  probabilidade prevista entre {{cal_lo}} e {{cal_hi}} são AFIB em apenas {{cal_obs_lo}} a {{cal_obs_hi}} dos
  casos. A probabilidade exibida é confiante demais fora da fonte de treino.
- **Restringindo o PTB-XL a laudos validados por humanos,** a especificidade é {{ext_hv_spec}}.

### Comparação com o baseline RR (experimento D, pareada, mesmas janelas)

- **Ranqueamento, sem limiar:** o modelo supera o baseline nos dois testes. No bootstrap pareado, ΔAUROC
  {{d_a_auro}} ({{d_a_auro_ci}}) no interno e {{d_b_auro}} ({{d_b_auro_ci}}) no externo; ΔAUPRC {{d_a_aupr}} e
  {{d_b_aupr}}.
- **No ponto de operação congelado, o quadro é misto.** No interno, a diferença não é significativa
  (McNemar p = {{d_a_p}}). **No externo, o baseline erra menos:** {{d_b_err_bl}} contra {{d_b_err_ml}}
  erros, McNemar p = {{d_b_p}}. O limiar do modelo foi escolhido onde as classes se separam quase
  perfeitamente e não se transfere tão bem quanto o do baseline.

### Teste de confusão de fonte (experimento C)

![confusão de fonte](results/figures/fig_source_confusion.png)

- **Com a escala descrita no TCC** (uma base dividida por mil, a outra por dez), só a amplitude do QRS
  separa as bases com **AUROC {{c_tcc}}**, sem modelo nenhum. Com unidades corretas, a mesma variável dá
  {{c_amp}}.
- **Com unidades e filtragem consistentes,** a assinatura de base é moderada: AUROC {{c_rhy}} com nossos
  atributos de ritmo e {{c_desc}} com descritores genéricos do sinal. Shaoxing × Ningbo: {{c_nb_rhy}}, sem
  assinatura.
- **Reproduzindo o desenho do TCC** (AFIB da Chapman, normais do PTB-XL), nossa regressão logística **não**
  explora a fonte: AUROC {{c2_lr_mix}} no teste misto e {{c2_lr_sh}} / {{c2_lr_ptb}} nos testes de mesma
  fonte. Já um modelo de descritores, sensível à fonte, perde especificidade quando os negativos passam a ser
  da base de treino ({{c2_ds_mix_spec}} → {{c2_ds_sh_spec}}).

### Falsos alarmes em monitoramento contínuo simulado (experimento H)

Um dia tem {{wpd}} janelas sem sobreposição. Com a especificidade relatada pelo TCC ({{tcc_spec}}), seriam
cerca de {{tcc_fa_day}} falsos alertas por dia se os erros fossem independentes. Nossos números vêm de uma
**simulação que concatena janelas isoladas de pacientes diferentes**, com transições artificiais:

![sensibilidade vs falsos alertas](results/figures/expH_sens_vs_false_alerts.png)

| Cenário (falsos alertas por dia) | Teste Shaoxing | PTB-XL (externo) |
|---|---|---|
| Sem votação (alerta em qualquer janela AFIB) | {{h_sh_1}} | {{h_ptb_1}} |
| Votação {{vote_n}} de {{vote_m}}, janelas independentes | {{h_sh_v}} | {{h_ptb_v}} |
| {{vote_n}} de {{vote_m}}, **erros correlacionados** (cada registro repetido por ~{{ep5}} min) | {{h_corr_sh}} | {{h_corr_ptb}} |
| Pessoa cujo ritmo de base é ectopia frequente | – | {{h_ect_lo}} a {{h_ect_hi}} |
| Pessoa cujo ritmo de base é arritmia sinusal | – | {{h_sa_lo}} a {{h_sa_hi}} |

- **Sensibilidade por episódio no PTB-XL**, com {{vote_n}} de {{vote_m}}: {{h_ptb_sens5}} para episódios de AFIB
  de ~{{ep5}} min e {{h_ptb_sens1}} para ~{{ep1}} min. Tempo mediano até o alerta: {{h_tmed}} s.
- **O valor com janelas independentes é otimista.** Na vida real, os erros de uma mesma pessoa se repetem, e
  quem tem ectopia frequente ou arritmia sinusal receberia muitos falsos alertas.

### Outros experimentos

- **Frequência alterada (E):**
  - falso AFIB por janela em Shaoxing: bradi {{e_sh_brady}}, taqui {{e_sh_tachy}};
  - **fora da base de treino ele sobe:** PTB-XL bradi {{e_ptb_brady}}, taqui {{e_ptb_tachy}} (contra
    {{e_ptb_norm}} em sinusal normal); Ningbo taqui {{e_nb_tachy}};
  - a regra de FC marca pelo menos {{hr_brady_min}} das bradicardias e {{hr_tachy_min}} das taquicardias
    rotuladas, mas também marca como FC baixa {{hr_ptb_norm_low}} dos ECGs "normais" do PTB-XL (aviso leve).
- **Robustez a ruído real (F, MIT-BIH Noise Stress Test Database):**
  - a sensibilidade fica ≥ {{f_sens_min}} sob qualquer ruído;
  - a conversão A/D de {{adc_bits}} bits não tem efeito (especificidade {{f_adc_spec}} contra {{f_clean_spec}} no
    sinal limpo);
  - **a especificidade despenca com ruído muscular e movimento de eletrodo:** ruído muscular a {{snr0}} dB →
    {{f_ma0_nosqi}}, a {{snrm6}} dB → {{f_mam6_nosqi}};
  - o SQI inicial quase não ajudou ({{f_mam6_init}}). Recalibrado na validação (concordância entre detectores
    ≥ {{sqi_agree}}), chega a {{f_mam6_cal}}, ao custo de rejeitar {{rej_calibrado_lo}} a {{rej_calibrado_hi}} das
    janelas limpas (antes, {{rej_inicial_lo}} a {{rej_inicial_hi}}). Figura: `results/figures/expF_robustness.png`.
- **Ritmos fora do treino (G):**
  - fração de janelas classificadas como AFIB: **flutter atrial {{g_fl_sh}}** (Shaoxing) / {{g_fl_ptb}}
    (PTB-XL), taquicardia atrial {{g_at}}, ectopia {{g_ect_sh}} a {{g_ect_ptb}}, arritmia sinusal {{g_sa_nb}} a
    {{g_sa_ptb}}, taquicardia supraventricular {{g_svt}};
  - o estado `INCERTO` captura só parte desses casos;
  - o "flutter" de Ningbo é classificado como AFIB em {{g_nb_af}} das janelas, o que reforça o problema de
    rótulo acima. Figura: `results/figures/fig_out_of_training.png`.
- **Referência ao TCC (I, três classes: AFIB, bradicardia sinusal, normal = modelo + regra de FC):** em teste
  balanceado, acurácia de {{i_sh_acc}} em Shaoxing ({{i_sh_n}} por classe) e **{{i_ptb_acc}} no PTB-XL
  externo** ({{i_ptb_n}} por classe, o tamanho do teste do TCC). No PTB-XL, o recall de AFIB é
  {{i_ptb_rec_afib}}, mas só {{i_ptb_rec_norm}} dos normais são reconhecidos. O TCC relata {{tcc_acc}} com
  outro protocolo (normais e arritmias de bases diferentes). É uma referência, não uma comparação.

### Literatura (apenas referência; outros conjuntos de teste)

- **Algoritmos de ECG em smartwatch:** sensibilidade agregada {{lit_sw_sens}} e especificidade {{lit_sw_spec}}
  (meta-análise, J Arrhythm 2025).
- **Análise de Holter assistida por IA:** sensibilidade para AFIB de {{lit_h_dnn}}, contra {{lit_h_conv}} na
  análise convencional (Fiorina et al., JAHA 2022).

Ambas conferidas na fonte primária (`results/reference/literature.json`).

### Execução a bordo

- **Medido em {{bench_cpu}}** (notebook de desenvolvimento, uma thread), **não em Raspberry Pi**:
  {{bench_med}} ms de mediana por janela (p95 {{bench_p95}} ms) no pipeline completo (filtros, detecção de
  QRS, atributos, SQI, modelo e votação). O modelo em si leva {{bench_model}} ms.
- **Memória residente:** cerca de {{bench_rss}} MB com numpy e scipy carregados.
- **Artefato:** {{bench_json_kb}} KB em JSON (inferência só com numpy) e {{bench_onnx_kb}} KB em ONNX.
- **O `scripts/benchmark.py` está pronto para rodar no Pi.**

## Limitações

- **Não validado em astronautas, em microgravidade nem com um Holter real.** São ECGs clínicos de repouso,
  reproduzidos.
- As bases têm exames isolados de {{rec_s}} s, sem acompanhamento: é detecção do ritmo na janela, não previsão.
- **A especificidade cai fora da base de treino,** o limiar congelado se transfere mal e, no ponto de operação
  externo, o baseline RR erra menos que o modelo. A probabilidade exibida fica descalibrada fora da fonte.
- **Flutter atrial, taquicardia atrial, ectopia frequente e arritmia sinusal são frequentemente classificados
  como AFIB.** O flutter, em especial, precisa de tratamento próprio.
- **Ruído muscular forte e movimento de eletrodo derrubam a especificidade,** e o SQI ainda não é bom o
  suficiente.
- **Falsos alertas por dia foram apenas simulados.** Com erros correlacionados, ou em pessoas com ectopia, eles
  são muito maiores que a estimativa com janelas independentes.
- A Chapman não tem identificador de paciente: a divisão de Shaoxing é por registro, e exames diferentes de um
  mesmo paciente podem cruzar a divisão (duplicatas exatas foram removidas).
- **Confusão forte por idade:** os pacientes com AFIB são bem mais velhos. Na faixa etária próxima à de
  astronautas ({{age_band}} anos), o teste interno tem só {{sub3054_pos}} janelas de AFIB.
- Sem cobertura de taquicardia ou fibrilação ventricular; não alegamos nada sobre elas.
- Desempenho no Raspberry Pi não medido. A transmissão Holter → Pi está fora do escopo e é simulada por replay.

## Como usar

Requisitos: Linux ou macOS, conda, cerca de dez gigabytes de disco livre e um download de {{dl_gb}} GB da
PhysioNet. Só CPU, sem GPU.

```bash
make env && conda activate afib-onboard       # Python 3.12, versões fixadas (requirements.lock)
make data          # download (com retomada) + checksums + cache da derivação I
make audit         # docs/data_audit.md
make features      # janelas, atributos, SQI, validação do detector de QRS
make train         # experimento A, fase de desenvolvimento (CV, validação, escolha pré-registrada)
make evaluate      # teste do experimento A, aberto uma única vez (num clone novo: make evaluate EVAL_FLAGS=--reproduce)
make experiments   # experimentos B a I
make export        # models/afib_logreg_v1.json + .onnx
make benchmark     # latência e memória nesta máquina
make report        # figuras + README.md + README.en.md + MODEL_CARD.md a partir de results/
make test
make demo          # painel local, sem internet: http://localhost:8501
```

- **Verificação rápida de ponta a ponta:** `make reproduce SUBSET=4000`, que usa um subconjunto; os números
  mudam em relação à execução completa.
- **Só a inferência:** `from src.inference import predict` e `predict(janela)`, com {{win}} amostras a {{fs}} Hz em
  qualquer unidade ou offset.
- **Simulação do Pi recebendo o Holter,** com eventos em JSON: `make stream`.

## Por onde começar a ler

| Documento | Para quê |
|---|---|
| [`HANDOFF.md`](HANDOFF.md) | estado do projeto, conclusões e próximos passos (passagem de bastão) |
| [`docs/decisions.md`](docs/decisions.md) | todas as decisões e desvios do plano, com justificativa |
| [`docs/data_audit.md`](docs/data_audit.md) | auditoria das bases |
| [`docs/tcc_analysis.md`](docs/tcc_analysis.md) | o que o TCC fez e o que corrigimos |
| [`docs/qa_jurados.md`](docs/qa_jurados.md) | revisão cética: perguntas difíceis e respostas |
| [`MODEL_CARD.md`](MODEL_CARD.md) | uso pretendido, métricas, vieses e modos de falha do modelo |
| [`DATA.md`](DATA.md) | fontes, versões, licenças e citações obrigatórias |
| [`CLAUDE.md`](CLAUDE.md) | briefing original do projeto |

## Estrutura do repositório

```
configs/   todos os parâmetros (sinal, rótulos, experimentos, regras pré-registradas)
src/       dados, rótulos, pré-processamento, QRS, atributos, SQI, baseline, modelos, decisão, avaliação, inferência
scripts/   etapas do pipeline (auditoria, atributos, exp. A, exp. B–I, export, benchmark, stream, relatório)
app/       painel Streamlit (offline)
models/    modelo final (JSON + ONNX) com metadados e hash dos dados
results/   métricas (JSON/CSV) e figuras, todas geradas por código
docs/      TCC, auditoria, análise do TCC, decisões, perguntas dos jurados, templates dos documentos
tests/     testes unitários, invariância a offset, ausência de vazamento, paridade da inferência, painel
```

## Próximos passos (não implementados)

- **Previsão de AFIB:** há literatura sobre prever AFIB a partir de ECG em ritmo sinusal e de variabilidade da
  FC, em geral retrospectiva. Exige bases com sinal anterior ao início do episódio.
- **Arritmias ventriculares:** TV e FV são o risco mais grave, mas exigem outras bases.
- **Validação com Holter real** e, depois, com dados de análogos espaciais ou de voo.
- **Dados da NASA:** integrar os indicadores do desafio numa visão mais ampla de saúde.
- **Melhorias:** tratar flutter e ectopia explicitamente, escolher o limiar numa validação multi-fonte,
  melhorar o SQI para movimento e ignorar janelas ruins na votação. Cada uma precisa ser reavaliada.

## Citação e licenças

- **Código:** MIT.
- **Dados:** não são redistribuídos. Veja [`DATA.md`](DATA.md) para as citações obrigatórias da
  Chapman-Shaoxing/Ningbo (PhysioNet *ecg-arrhythmia*), do PTB-XL, da MIT-BIH Noise Stress Test Database e
  da PhysioNet.
- **Ponto de partida:** Maggioni, A. F.; Rebonatto, M. T. *Inteligência Artificial aplicada a análise de
  Eletrocardiograma*. TCC, Universidade de Passo Fundo, 2023.
