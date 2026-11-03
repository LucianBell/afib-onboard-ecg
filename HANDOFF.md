# Relatório de passagem: estado do projeto e conclusões

Relatório para outra pessoa ou outra instância do Claude continuar o trabalho sem refazer a análise.

- **Estado em 2026-11-03**, commit `50cef09`, branch `master`, árvore limpa.
- **Números deste relatório foram transcritos** dos arquivos em `results/`, com o caminho indicado ao lado.
  Se os resultados forem regenerados, a fonte de verdade é `results/` e o `README.md`, que é gerado por
  código; este arquivo pode ficar defasado.
- **Leitura obrigatória antes de mexer:**
  - `CLAUDE.md`: briefing original, regras de linguagem e integridade;
  - `docs/decisions.md`: decisões D1–D47 e desvios do briefing;
  - `docs/qa_jurados.md`: revisão cética, com perguntas e respostas.

---

## 1. O que é o projeto

Detector de **fibrilação atrial (AFIB) que roda a bordo**, em ECG de derivação única (derivação I, 250 Hz,
janelas de 2.400 amostras ≈ 9,6 s), pensado para um Holter preso ao astronauta enviando sinal a um Raspberry
Pi. É para o **NASA Space Apps Challenge 2026**: envio de 14/11 às 9h até 15/11 às 23h59, repositório pronto
até 12/11, recursos oficiais dos desafios em 13/11. O ponto de partida é o TCC de Maggioni & Rebonatto (UPF,
2023), em `docs/`.

Cada janela passa por três camadas:

1. **SQI** (qualidade do sinal). Reprovada → `SINAL_RUIM`.
2. **Modelo AFIB vs. sinusal**: regressão logística sobre 30 atributos. Bradi e taquicardia sinusais
   são negativos no treino.
3. **Regra de FC**: `AVISO_FC_BAIXA` / `AVISO_FC_ALTA` como aviso leve, com limiares 60/100 bpm adaptados ao
   histórico da pessoa.

Por cima disso:
- `INCERTO` cobre entrada fora do padrão (Mahalanobis) e confiança baixa (limiar ≤ p < 0,5);
- `ALERTA_AFIB` exige AFIB em **3 de 3** janelas consecutivas, regra escolhida na validação.

**Regras de linguagem** (CLAUDE.md §1):
- dizer "detecção do ritmo presente na janela", nunca "previsão";
- não alegar infarto, parada cardíaca nem arritmia ventricular;
- não dizer "melhor que Holter";
- sempre: "protótipo de pesquisa, não é dispositivo médico";
- os dados são clínicos, públicos e terrestres: **não são da NASA nem de astronautas**.

---

## 2. Estado das etapas (CLAUDE.md §13)

| Etapa | Situação | Commit principal |
|---|---|---|
| 1. Estrutura e ambiente | ✅ conda `afib-onboard`, Python 3.12, `requirements.lock` | `cab7b1d` |
| 2. Download e auditoria | ✅ `docs/data_audit.md` | `c25965b` |
| 3. Pré-processamento e testes | ✅ | `a03d09a` |
| 4. Atributos, SQI, baseline RR | ✅ | `a03d09a` |
| 5. Experimento A | ✅ escolha pré-registrada, teste aberto | `782757e`, `e4e402f` |
| 6. Experimentos B–I | ✅ | `d1047fe`, `473513c`, `7f80593` |
| 7. Inferência, stream, benchmark | ✅ (benchmark só em notebook) | `1a36401` |
| 8. Painel | ✅ Streamlit offline | `1a36401` |
| 9. README, model card, figuras | ✅ gerados de `results/` | `f695475`, `f6c2789` |
| 10. `make` do zero em subconjunto | ✅ código 0, 59 testes, 6 min 23 s | `720403d`, `d6a0a31`, `50cef09` |

**Critério de pronto (§14):**
- **Parcial:** reprodução num clone novo. Passou em subconjunto, mas o ambiente conda não foi recriado do zero,
  os zips entraram por hardlink e o pipeline completo nunca rodou num único `make reproduce`.
- **Concluídos:** experimentos e benchmark publicados (benchmark sem Pi); README com resultado interno,
  externo, baseline, falsos alertas e limitações; inferência e painel offline; citações e aviso.

---

## 3. Ambiente e dados locais (fora do Git)

- **Ambiente:** `conda activate afib-onboard`, ou `PYTHON=/home/lucianbell/miniconda3/envs/afib-onboard/bin/python`
  nos comandos `make`. Torch está instalado em versão CPU, só para a CNN de referência.
- **`data/raw/`** (~13 GB):
  - zips da Chapman (*ecg-arrhythmia* 1.0.0) e do PTB-XL 1.0.3, já extraídos;
  - `nstdb/`: ruídos `bw`, `em`, `ma` da MIT-BIH NSTDB;
  - `snomed_maps/`: tabelas do CinC 2021, commit `e2a75fc`.
- **`data/interim/`:** cache da derivação I (mV, 500 Hz) e índices.
- **`data/processed/`:** janelas, atributos, SQI e modelos candidatos do experimento A.
- **`data/demo/demo_pack.npz`:** replay do painel.
- **Máquina usada:** i7-1165G7, 8 threads, 7,5 GB de RAM, sem GPU, Debian.

**Comandos (Makefile):**

```bash
make data audit features      # dados → auditoria → janelas/atributos/SQI/validação do QRS
make train                    # exp. A fase dev (não abre o teste)
make evaluate                 # exp. A fase test — TRAVADO (já aberto); num clone: EVAL_FLAGS=--reproduce
make experiments              # B–I (inclui f2 = calibração do SQI)
make export benchmark         # models/afib_logreg_v1.{json,onnx}; latência/memória
make demo-data demo           # painel em http://localhost:8501 (sem internet)
make stream                   # simulação do Pi com eventos JSON
make report                   # figuras + README.md + MODEL_CARD.md a partir de results/
make test                     # 59 testes
make reproduce SUBSET=4000    # do zero, rápido
```

---

## 4. Decisões de desenho que mudaram o plano (ver `docs/decisions.md`)

- **A Chapman são duas bases** (D12–D14). Shaoxing vai até JS10646 (10.247 registros) e Ningbo vem depois
  (34.905). **Toda a AFIB está em Shaoxing; Ningbo tem zero.** A fronteira foi conferida contra o CinC 2021: 93
  de 94 códigos idênticos.
  - → **O experimento A usa só Shaoxing.** Ningbo entra apenas como teste de assinatura de fonte (C) e como
    negativos extras (E, H).
- **O "flutter" de Ningbo provavelmente é AFIB:** 12 sinais idênticos estão rotulados AFIB em Shaoxing e flutter
  em Ningbo. Ficou excluído. A "TV paroxística" de Ningbo coincide com SVT em 21 de 26 cópias, então não há
  alegação sobre TV/FV.
- **Dicionário SNOMED oficial incompleto:** 13.191 registros usam códigos ausentes e 2 códigos estão errados.
  Foram resolvidos com as tabelas do CinC 2021 (D17).
- **Rótulos** (D8–D9): `SINUS_NORMAL`, `SINUS_OUTRO` (sinusal com outros achados; **entra nos negativos**),
  `SINUS_BRADY`, `SINUS_TACHY`, `SINUS_ARRITMIA` (só estresse), `FORA_DE_TREINO`, `CONFLITO`. Ectopia e bloqueio
  AV com ritmo sinusal → `FORA_DE_TREINO`.
- **Pré-processamento** (D20): reamostragem 500 → 250 Hz **antes** dos filtros, para treino e aparelho usarem
  exatamente a mesma `preprocess_window`. Notch de 50 Hz, Butterworth 0,05–30 Hz em SOS, normalização robusta
  por janela, invariância a offset testada. LOESS e cúbica do TCC não foram testados (D22).
- **SQI do sistema a bordo** = SQI inicial com concordância entre detectores ≥ 0,95, calibrado no experimento
  F (D37; chave `sqi_onboard`). Os experimentos A–I usaram o SQI inicial.
- **Deduplicação por hash antes de dividir** (D16). A Chapman não tem identificador de paciente, então a
  divisão é por registro (D19).

---

## 5. Resultados principais (por janela de 9,6 s)

### A — interno, Shaoxing (`results/expA/test.json`)
Teste: 1.230 janelas, 261 AFIB (21%).

| Modelo | AUROC | Sensibilidade | Especificidade | PPV |
|---|---|---|---|---|
| Baseline RR (nRMSSD) | 0,9947 | 0,992 | 0,985 | 0,945 |
| **Regressão logística (escolhida)** | 0,9998 | 1,000 | 0,988 | 0,956 |
| Random Forest | 0,9998 | 1,000 | 0,985 | 0,946 |
| LightGBM | 0,9999 | 1,000 | 0,987 | 0,953 |
| CNN (24 mil parâmetros) | 0,9991 | 0,992 | 0,988 | 0,956 |

- **Escolha** (`results/expA/selection.json`): o modelo mais simples a até **0,010** de AUPRC de validação do
  melhor. A logística empatou no topo (0,9997).
- **Os números internos estão no teto:** os negativos são sinusal limpo de uma única fonte.

### B — externo, Shaoxing → PTB-XL inteiro (`results/expB/`)

| Medida | Interno → externo |
|---|---|
| AUROC | 0,9998 → 0,9968 |
| Sensibilidade | 1,000 → 0,990 |
| **Especificidade** | **0,988 → 0,957** (≈ 3,4× mais falsos positivos) |
| PPV | 0,956 → 0,677 (prevalência 8%) |
| PPV a 1% de prevalência | 0,449 → 0,190 |

- **Inverso:** PTB-XL → Shaoxing dá AUROC 0,9995.
- **Entre os modelos de ML,** a logística ficou com IC de AUROC sobreposto ao do RF e do LightGBM, e melhor
  que a CNN (0,9914).
- **Calibração externa** (`calibration_external.json`): ECE 0,013, mas probabilidades entre 0,5 e 0,9 são AFIB
  em só 3–24% dos casos. **A probabilidade é confiante demais fora da fonte.**

### C — confusão de fonte (`results/expC/`)

| O que separa as bases | AUROC |
|---|---|
| Só a amplitude, **com a escala do TCC** (÷10³ vs. ÷10) | **1,00** |
| Só a amplitude, com unidades corretas | 0,59 |
| Atributos de ritmo (normais Shaoxing × PTB-XL) | 0,86 |
| Descritores do sinal | 0,77 |
| Shaoxing × Ningbo | ≈ 0,50 |

No desenho do TCC, nossa logística não explora a fonte.

### D — contra o baseline (`results/expD/summary.json`)
- **Ranking:** o modelo é melhor. ΔAUROC de +0,005 interno e +0,011 externo; ΔAUPRC de +0,034 e +0,178; IC
  acima de zero.
- **No ponto de operação externo, o baseline erra menos:** 621 contra 689 erros, McNemar p = 0,003. O
  limiar da logística (p ≥ 0,0105), escolhido em Shaoxing, não transfere.

### E — frequência alterada (`results/expE/`)
- **Falso AFIB por janela:** Shaoxing, bradi 1,2% e taqui 1,6%; **PTB-XL, bradi 9,2% e taqui 6,6%** (normal
  3,4%); Ningbo, taqui 7,5%.
- **Regra de FC:** acerta ≥ 98,2% das bradi e taquicardias, mas marca FC baixa em 18% dos "normais" do PTB-XL.

### F — ruído real NSTDB (`results/expF/`)
- A sensibilidade fica em 1,0 ou perto disso.
- A conversão de 12 bits não tem efeito.
- **A especificidade despenca:** ruído muscular, 0,80 a 0 dB e 0,37 a −6 dB; movimento de eletrodo, 0,75 a
  0 dB.
- **O SQI ajuda pouco:** depois de calibrado, 0,55 a −6 dB, ao custo de rejeitar 6–8% das janelas limpas.

### G — ritmos fora do treino (`results/expG/`), fração classificada AFIB

| Ritmo | AFIB |
|---|---|
| **Flutter** | **55%** (Shaoxing) / 29% (PTB-XL) |
| Taquicardia atrial | 44% |
| Ectopia | 24–31% |
| Arritmia sinusal | 15–21% |
| SVT | 6% |
| "Flutter" de Ningbo | 84% |

`INCERTO` captura só parte desses casos.

### H — monitoramento simulado (`results/expH/`)
- **Votação escolhida na validação:** 3 de 3.
- **Falsos alertas por dia no PTB-XL:**

| Cenário | Por dia |
|---|---|
| Sem votação | ~115 |
| 3 de 3, janelas independentes | ~0,01 |
| **3 de 3, erros correlacionados (~5 min)** | **~4** |
| **Pessoa com ectopia** | **53–179** |
| Pessoa com arritmia sinusal | 46–57 |

- **Sensibilidade por episódio:** 1,0 para episódios de ~5 min e 0,96 para ~1 min. Tempo mediano até o alerta:
  29 s.
- É simulação com registros concatenados de pacientes diferentes.

### I — referência ao TCC, 3 classes (`results/expI/`)
- Acurácia de 98,8% em Shaoxing balanceado e **89,7% no PTB-XL** (356 por classe, o mesmo tamanho do TCC).
- No PTB-XL, a AFIB tem recall de 99,2%, mas só 79,5% dos normais são reconhecidos.
- O TCC relata 96,9%, com outro protocolo.

### Bordo (`results/benchmark/benchmark_LucianDebian.json`)
- **Medido num notebook i7, 1 thread, não no Pi:** 3,6 ms por janela (p95 4,2 ms) no pipeline completo; o
  modelo em si leva 0,05 ms.
- Cerca de 104 MB de RSS.
- Artefatos: JSON de 34 KB (inferência só com numpy) e ONNX de 0,8 KB, com paridade de 3×10⁻⁶.

### Detector de QRS (`results/qrs_validation.json`)
Contra o XQRS do `wfdb`: sensibilidade ≥ 0,992 e PPV ≥ 0,982 em todos os grupos.

---

## 6. Conclusões

**O que o projeto mostra:**
- Um detector leve e interpretável acha AFIB com **sensibilidade de 0,99 ou mais**, inclusive em base externa
  e sob ruído.
- Ele roda offline em milissegundos.
- A metodologia corrige os problemas do TCC: fonte única, validação externa, teste aberto uma vez, prevalência
  natural, falsos alertas por dia.
- A escala descrita no TCC tornava as bases triviais de separar.

**O que não mostra, e são as fraquezas a assumir:**
- **Especificidade é o problema:** cai fora da fonte, colapsa com ruído muscular e de movimento, e flutter,
  ectopia e arritmia sinusal viram AFIB.
- **Os falsos alertas reais são incertos,** e altos para quem tem ectopia.
- **No ponto de operação externo, o baseline RR erra menos.**
- **A probabilidade está descalibrada fora da fonte.**
- **Nada foi validado** em astronautas, microgravidade, exercício, Holter real ou Raspberry Pi.
- **A motivação é de risco:** prevalência de ~5% em astronautas ativos, mas o estudo de 2018 não viu AFIB em
  voo.

---

## 7. Integridade e protocolo (não quebrar)

- **README.md e MODEL_CARD.md são GERADOS.** Edite `docs/templates/*.template.md` e rode `make report`.
  - Todo número entra por `{{marcador}}`, com a origem em `results/readme_numbers.json`.
  - `tests/test_report_numbers.py` reprova número escrito à mão e README editado manualmente.
  - Modo subconjunto: `AFIB_SUBSET` → "n/d".
- **O teste do experimento A está travado** (`results/expA/TEST_OPENED.json`). Não reabrir para ajustar
  nada. `--reproduce` serve só para verificação num clone.
- **Pré-registros** em commit antes de rodar: `a03d09a` (margem e limiar do A), `d1047fe` (INCERTO, N de M,
  SNR, TCC) e `473513c` (calibração do SQI).
- **Transparência já registrada:**
  - D31: o teste A foi aberto duas vezes por um erro de serialização, com cálculo determinístico;
  - D37: calibração do SQI decidida depois de ver o SQI falhar, feita na validação;
  - D38: análises de sensibilidade do H *post hoc*;
  - D46: calibração externa medida depois da revisão.
- **Citações conferidas na fonte** (`results/reference/literature.json`): meta-análise de smartwatch
  (J Arrhythm 2025), Holter com IA (Fiorina, JAHA 2022), Academias Nacionais (2017) e Khine (2018).
- **Commits pequenos,** terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

## 8. Pendências e próximos passos sugeridos

**Para a competição (até 12/11):**
1. **Recriar o ambiente do zero** (`make env`) num diretório novo e rodar `make reproduce SUBSET=4000`.
   Esse caminho ainda não foi testado.
2. **Integrar os recursos oficiais do desafio** quando saírem em 13/11. As entradas são `src/preprocess.py` e
   `predict(window)`.
3. Se houver Raspberry Pi: `python scripts/benchmark.py` lá, e **acrescentar** o JSON em
   `results/benchmark/`.
4. Ensaiar a apresentação com `docs/qa_jurados.md`.

**Melhorias técnicas (cada uma exige reavaliação na validação, sem tocar no teste A):**
- **Limiar:** escolher e calibrar numa validação multi-fonte, por exemplo fold 9 do PTB-XL mais validação de
  Shaoxing. Corrige o ponto fraco do D.
- **Flutter e ectopia:** tratamento explícito, com classe própria ou regra baseada na regularidade das ondas F.
- **SQI:** melhorar para ruído muscular e de movimento.
- **Votação:** ignorar janelas `SINAL_RUIM`, em vez de contá-las como não-voto (D43), e reavaliar o H.
- **Ainda não feitos:** ablação LOESS/cúbica (D22), CNN no experimento C, `notebooks/` vazio e subgrupos por
  idade e sexo no teste externo.

---

## 9. Mapa de arquivos-chave

| Caminho | Conteúdo |
|---|---|
| `configs/default.yaml` | todos os parâmetros e regras pré-registradas |
| `src/data.py`, `src/labels.py` | download, checksums, índices, rótulos |
| `src/preprocess.py` | `preprocess_window`, `simulate_device` |
| `src/qrs.py`, `src/features.py`, `src/sqi.py`, `src/baseline.py` | detector, 30 atributos, SQI, nRMSSD e regra de FC |
| `src/models.py`, `src/evaluate.py`, `src/splits.py` | candidatos, métricas e bootstrap, deduplicação e divisão |
| `src/decision.py`, `src/inference.py`, `src/demo.py` | estados, OOD, N de M; `predict()` e `Monitor`; replay |
| `scripts/exp_a.py`, `scripts/experiments.py` | experimento A (dev/test) e B–I |
| `scripts/export_model.py`, `benchmark.py`, `simulate_stream.py`, `build_demo_pack.py` | bordo e demonstração |
| `scripts/make_figures.py`, `make_report.py`, `calibration_external.py` | relatório |
| `app/dashboard.py`, `.streamlit/config.toml` | painel offline |
| `models/afib_logreg_v1.{json,onnx,sha256}` | modelo final com metadados e hash dos dados |
| `results/` | todas as métricas e figuras |
| `docs/data_audit.md`, `tcc_analysis.md`, `decisions.md`, `qa_jurados.md` | auditoria, TCC, decisões, jurados |
| `DATA.md`, `MODEL_CARD.md`, `README.md`, `LICENSE` | fontes, licenças e citações; documentos gerados; MIT |
