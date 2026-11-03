# Contexto do projeto: detector de fibrilação atrial a bordo para astronautas (NASA Space Apps 2026)

Este documento é o briefing completo do projeto. Siga a ordem da seção 13. Em cada etapa, escolha, registre em `docs/decisions.md` e continue. Só interrompa o usuário nos bloqueios listados na seção 13.

## 1. Missão

Construir um repositório reproduzível, com modelo treinado, resultados preliminares reais e uma demonstração simples, de um **detector de fibrilação atrial (AFIB) que roda a bordo, em ECG de derivação única, sem depender da Terra, validado entre bases independentes e com controle de falsos alarmes**.

**Produto imaginado:** um Holter (monitor de ECG portátil) preso ao astronauta envia o sinal a um Raspberry Pi. O Pi analisa janelas consecutivas localmente e gera avisos.

**Fora do escopo agora:** a transmissão Holter → Pi. Ela é simulada por um script que reproduz registros públicos.

**Ponto de partida:** o TCC em `docs/` (Maggioni & Rebonatto, UPF), que deve ser citado. Reaproveitamos as bases e o cenário de sinal limitado, mas trocamos a rede profunda por modelos simples e corrigimos os problemas de avaliação da seção 3.

### Por que AFIB

- Registros de arritmias atriais em astronautas e recomendação das Academias Nacionais dos EUA de dar mais ênfase à AFIB no relatório de risco da NASA.
- É frequentemente intermitente ou sem sintomas, então um alerta automático tem valor.
- É detectável em uma derivação e tem dados nas bases escolhidas.

### Linguagem obrigatória

- Dizer **detecção precoce** do ritmo presente na janela, nunca "previsão de evento futuro". As bases têm exames isolados de 10 s, sem desfecho posterior.
- Não afirmar que o sistema detecta infarto, parada cardíaca ou arritmias ventriculares.
- Não afirmar que é "melhor que o Holter". Comparações com a literatura são apenas referência, pois não usam o mesmo conjunto de teste.
- O argumento defensável é **análise a bordo durante o registro**, mais a comparação com um baseline no mesmo teste.
- Declarar sempre: protótipo de pesquisa e apoio à decisão, não dispositivo médico nem diagnóstico. Não foi validado em astronautas nem em microgravidade.

## 2. Arquitetura do sistema

Cada janela passa por três camadas:

1. **Qualidade do sinal (SQI).** Janela ruim retorna `SINAL_RUIM` e não gera aviso clínico.
2. **Modelo de ML: AFIB vs. ritmo sinusal.** É o núcleo do projeto. Bradicardia e taquicardia sinusais pertencem ao lado **não AFIB**, porque o modelo não pode confundir frequência alterada com fibrilação.
3. **Regra de frequência cardíaca.** Marca bradicardia e taquicardia como aviso leve, comparando com limiares configuráveis e o histórico da própria pessoa. Não é alarme grave: atletas podem ter frequência baixa sem doença, e a taquicardia é esperada no exercício.

### Saídas

| Estado | Condição | Severidade |
|---|---|---|
| `SINAL_RUIM` | SQI reprovado | técnica |
| `INCERTO` | confiança baixa ou entrada fora do padrão | revisar |
| `ALERTA_AFIB` | AFIB em N de M janelas consecutivas | alta |
| `AVISO_FC_BAIXA` / `AVISO_FC_ALTA` | desvio da regra de frequência, sem AFIB | leve |
| `OK` | ritmo sinusal, frequência dentro do esperado | nenhuma |

## 3. Especificação do sinal-alvo (aparelho MP-IoT do TCC)

| Item | Valor |
|---|---|
| Derivação | I |
| Frequência | 250 Hz |
| Janela | 2.400 amostras (9,6 s) |
| Banda útil | 0,05 a 30 Hz |
| Sensor | AD8232 |
| Saída | somente valores positivos (conversor A/D) |

Coloque tudo em `configs/`. O pipeline não pode depender do deslocamento (offset) absoluto do sinal.

### O que o TCC fez

- **Bases:** Chapman-Shaoxing/Ningbo para arritmias e PTB-XL para normais.
- **Pré-processamento:** notch de 50 Hz → Butterworth 0,05–30 Hz (ordem 4) → LOESS (janela 10) → interpolação cúbica de 500 para 250 Hz → deslocamento para positivos → Butterworth (ordem 2) → MinMax 0–10.
- **Dados:** undersampling para 1.780 registros por classe, 80/20, validação cruzada em 5 dobras.
- **Melhor modelo (RHCB5):** Conv1D 512-256-256-128 + Bi-LSTM 256 + densas 256-128-saída, 60 épocas, Adam.
- **Resultado principal (3 classes: AFIB, SB, normal):** acurácia 96,91%, precisão 96,91%, recall 96,90%, F1 96,90%, especificidade 98,45%. Recall por classe, calculado da matriz de confusão: AFIB 99,4%, SB 94,7%, normal 96,6%.
- **4 classes (com SI):** acurácia 87,42%.

### Problemas a evitar

1. **Confusão de fonte de dados (o mais grave).** Normais vieram da Alemanha/PTB-XL (equipamento Schiller, anos 1990) e arritmias da China/Chapman (GE MUSE). O modelo pode ter aprendido a distinguir base e equipamento, e não patologia. A escala também difere: o TCC descreve divisão por 10³ em uma base e por 10 na outra.
2. **Teste balanceado artificialmente.** Com 33% por classe, as métricas não refletem uso real, em que arritmia é rara.
3. **Vazamento possível.** A normalização é descrita antes da divisão, e "validação" e "teste" se confundem. Não há conjunto externo. A divisão não respeita paciente, embora o PTB-XL tenha vários registros por paciente.
4. **Conjunto fechado.** No simulador, fibrilação e taquicardia ventricular viraram AFIB com mais de 98% de confiança, e assistolia virou SB com 99%. O rótulo está errado e a confiança é enganosa.
5. **Validação real muito pequena.** São 5 pessoas e 15 eventos simulados, sem laudo do ECG coletado. O caso "insuficiência cardíaca → AFIB" não confirma nada, pois insuficiência cardíaca não é ritmo.
6. **Inconsistências internas.**
   - O resumo cita 66.989 dados (soma bruta das bases), a seção 3.1 cita 44.217 e o treino usa 7.120.
   - O texto chama o Butterworth de FIR, mas ele é IIR.
   - Precisão de 63,69% no RHCB4 parece erro de digitação.
   - A especificidade macro de 89,66% (4 classes) não bate com a matriz: daria cerca de 95,8%.
   - O texto traz "Fibrilação Arterial", quando o correto é atrial.
7. **Anexo A incorreto.** No `.hea`, `16+24` é o formato de armazenamento, `1000/mV` é o ganho, `16` são os bits do A/D, `-49` é o primeiro valor e `15041` é o checksum. **Não use esse anexo.** Leia as unidades com `wfdb`. Os rótulos usam SNOMED CT, não CID.

## 4. Dados

Baixe da PhysioNet para `data/raw/`, que fica no `.gitignore`. Confirme a licença de cada base e registre as citações exigidas em `DATA.md`.

- **Chapman:** https://physionet.org/content/ecg-arrhythmia/1.0.0/ — 45.152 ECGs de 12 derivações, 10 s, 500 Hz. O mapeamento vem de `ConditionNames_SNOMED-CT`. **Não codifique códigos SNOMED de memória:** leia-os do arquivo.
- **PTB-XL:** https://physionet.org/content/ptb-xl/ — use a versão mais recente, com `records500`, `ptbxl_database.csv` e `scp_statements.csv`. Use `strat_fold`: 1–8 treino, 9 validação, 10 teste. Os registros de um paciente ficam na mesma dobra.

Se o disco, a rede ou o tempo forem limitados, comece por um subconjunto e registre isso.

### Auditoria obrigatória antes de treinar (`docs/data_audit.md`)

- Contagem de cada rótulo e coocorrências em ambas as bases.
- Registros ausentes, corrompidos, planos, com NaN ou fora de 5.000 amostras.
- **Unidades:** distribuição de amplitude do QRS por base. A documentação da Chapman fala em 4,88 por bit e o cabeçalho em ganho 1000. Confirme empiricamente que tudo está em mV plausíveis.
- Idade e sexo por classe e por base. Idade é confundidor forte da AFIB e será usada na análise de subgrupos.
- Verifique se há identificadores de paciente na Chapman. Se não houver, documente a limitação.
- Duplicatas de sinal por hash.

## 5. Rótulos

| Grupo | Chapman | PTB-XL (rhythm) | Uso |
|---|---|---|---|
| `AFIB` | fibrilação atrial | `AFIB` | positivo do modelo |
| `SINUS_NORMAL` | ritmo sinusal sem outro diagnóstico relevante | `SR` + `NORM` | negativo |
| `SINUS_BRADY` | bradicardia sinusal | `SBRAD` | negativo; testa a regra de FC |
| `SINUS_TACHY` | taquicardia sinusal | `STACH` | negativo; testa a regra de FC |
| `FORA_DE_TREINO` | flutter, SVT, AT, PVC frequente, bloqueio AV e outros | equivalentes | apenas teste de estresse |

Regras:

- Excluir do treino registros com rótulos de ritmo conflitantes, e documentar quantos.
- Flutter fica fora do treino por padrão, porque na prática clínica merece análise própria. Reporte como o modelo o classifica.
- Reportar claramente que VT e VF têm pouca ou nenhuma cobertura nessas bases de repouso. Não alegar detecção desses ritmos.

## 6. Pré-processamento

Módulo único `src/preprocess.py`, igual em treino e inferência:

1. Derivação I em mV.
2. Notch de 50 Hz, compatível com a origem dos dados.
3. Butterworth 0,05–30 Hz com `sosfiltfilt` (SOS para estabilidade numérica em corte muito baixo).
4. Reamostragem 500 → 250 Hz com `resample_poly`.
5. Recorte de 2.400 amostras, em posição central ou aleatória no treino.
6. Remoção de offset e normalização robusta por janela.

Inclua um teste que confirme que somar uma constante positiva não altera a predição.

LOESS e interpolação cúbica do TCC ficam como ablação opcional: mantenha só se ajudarem na validação. O escalonamento global, se usado, é ajustado apenas no treino.

Crie também `simulate_device()`, que converte o sinal em unidades de A/D de 12 bits com offset positivo, para testar a compatibilidade.

## 7. Modelos

**Comece simples e só avance se houver ganho real.**

1. **Baseline obrigatório:** regra de irregularidade dos intervalos RR, sem aprendizado. É a comparação principal do projeto.
2. **Regressão logística** sobre atributos.
3. **Random Forest.**
4. **LightGBM ou XGBoost.**
5. **CNN 1D compacta** (menos de 100 mil parâmetros), opcional, só como referência.

### Atributos (`src/features.py`)

- **Detecção de QRS** leve e sem dependência pesada no Pi, com testes.
- **Irregularidade:** RR médio, SDNN, RMSSD, pNN50, CV do RR, SD1/SD2, entropia do RR, razão de turning points.
- **Atividade atrial:** presença de onda P no batimento médio e atividade entre batimentos.
- **Morfologia:** largura aproximada do QRS e correlação entre batimentos.
- **Frequência:** potência por banda.
- **SQI:** calculado à parte, para a camada 1.
- Idade e sexo ficam fora do modelo, porque o monitor recebe apenas o sinal.

Use peso de classe em vez de descartar dados. Ajuste hiperparâmetros e o limiar de decisão só com validação.

**Critério de escolha:** o modelo mais simples dentro de uma margem pré-definida no AUPRC da validação, registrada antes de abrir o teste. O teste é usado uma única vez.

## 8. Experimentos

- **A — Principal, dentro da Chapman:** AFIB vs. sinusal, tudo da mesma fonte. Divisão 70/15/15 estratificada e semente fixa, mais validação cruzada no treino.
- **B — Validação externa (o diferencial):** treinar na Chapman e testar no PTB-XL, usando os rótulos de ritmo. Depois o inverso, se houver volume de AFIB. Reporte a queda de desempenho entre A e B.
- **C — Teste de confusão de fonte:**
  - Treinar um classificador para separar normais da Chapman de normais do PTB-XL. AUROC próximo de 1 indica assinatura forte de base.
  - Reproduzir o desenho do TCC (normais do PTB-XL, arritmias da Chapman) com o mesmo modelo simples e comparar com A e B.
- **D — Comparação com o baseline:** ML vs. regra RR no mesmo teste, com teste estatístico pareado, como McNemar ou bootstrap pareado.
- **E — Confusão com frequência alterada:** taxa de falso AFIB em `SINUS_BRADY` e `SINUS_TACHY`. Avaliar também a regra de FC contra esses rótulos.
- **F — Robustez:** ruído muscular, oscilação de linha de base, movimento de eletrodo, conversão de 12 bits. Curva de desempenho por SNR, com e sem SQI.
- **G — Fora de treino:** como cada ritmo não treinado é classificado e qual fração vai para `INCERTO`.
- **H — Monitoramento contínuo simulado:** ver seção 9.
- **I — Referência ao TCC:** derivar uma saída de 3 classes (AFIB, SB, normal) com modelo + regra, em teste balanceado de mesmo tamanho, e colocar lado a lado com o TCC, com a ressalva de que os protocolos diferem.

## 9. Avaliação

**Métricas de AFIB:** sensibilidade, especificidade, PPV, NPV, F1, AUROC, AUPRC, matriz de confusão e IC de 95% por bootstrap. **Calibração:** Brier e ECE. **Subgrupos:** faixa etária e sexo, destacando adultos em idade próxima à de astronautas, por ser a população mais relevante.

Apresente dois cenários, sem misturar: prevalência natural da base e teste balanceado, este apenas para comparar com o TCC.

**Falso alarme:** em um dia há cerca de 9.000 janelas não sobrepostas de 9,6 s. Com a especificidade de 98,45% do TCC, seriam da ordem de 140 falsos alertas por dia, se os erros fossem independentes. Portanto:

- Reportar PPV em prevalências hipotéticas de 0,1%, 1% e 5%.
- Implementar votação temporal N de M e escolher a configuração na validação.
- Mostrar a curva sensibilidade × falsos alertas/dia e o tempo até o alerta.
- Como as bases têm registros isolados de 10 s, deixar claro que é uma simulação com registros concatenados de uma mesma classe e transições artificiais.

**Literatura como referência, sem alegar superioridade:** smartwatches, em algoritmo, 86% de sensibilidade e 94% de especificidade (meta-análise, J Arrhythm 2025); Holter com DNN 98% vs. convencional 91% de sensibilidade para AFIB (Fiorina et al., JAHA 2022). Verifique essas citações na fonte antes de publicar.

## 10. Execução a bordo e demonstração

- `src/inference.py`: API `predict(window) -> {estado, prob_afib, fc, sqi}`.
- `scripts/simulate_stream.py`: reproduz ECG em tempo acelerado, com janela deslizante, votação temporal e alertas em JSON.
- `scripts/benchmark.py`: mede latência, RAM e tamanho do artefato. Exporte em formato leve (ONNX, se viável).
- **Não invente números de Raspberry Pi.** Sem o hardware, publique a medição da máquina atual, identificada, e deixe o script pronto para o Pi.
- **Painel simples (`app/`, Streamlit ou página local):** traçado do ECG, frequência cardíaca, estado atual, probabilidade de AFIB, histórico de alertas e botão para trocar o cenário (sinusal, AFIB, bradicardia, taquicardia, sinal ruim). Faixa fixa na tela: "Replay de dados clínicos públicos. Não são dados de astronautas." O painel roda sem internet.

## 11. Repositório

```
README.md            inglês, com resumo em pt-BR; limitações e como reproduzir
DATA.md              fontes, versões, licenças, citações
MODEL_CARD.md        uso pretendido, limites, métricas, vieses
LICENSE              confirmar compatibilidade com as bases
Makefile             make data | audit | features | train | evaluate | report | demo | test
configs/
docs/                TCC, data_audit.md, tcc_analysis.md, decisions.md
src/                 data, preprocess, features, models, evaluate, inference
app/                 painel de demonstração
scripts/
models/              artefatos finais pequenos com metadados e hash dos dados
results/             métricas JSON/CSV e figuras geradas por código
notebooks/           apenas visualização
tests/               unidades, invariância a offset, ausência de vazamento
```

Requisitos: Python com ambiente fixado, semente registrada, testes passando, commits pequenos e nenhum dado bruto no Git.

### Regras de integridade

- Todo número do README precisa vir de um arquivo em `results/`, gerado por comando documentado. Nunca escreva métrica à mão nem antecipe resultado.
- Se o resultado for ruim, publique assim mesmo e explique.
- Dados simulados ou concatenados sempre identificados como tal.
- Registrar decisões e desvios em `docs/decisions.md`.

## 12. Próximos passos (apenas no README, não implementar agora)

- **Previsão de AFIB:** há literatura com ECG em ritmo sinusal e variabilidade da frequência cardíaca, em geral retrospectiva. Exige bases com sinal antes do início do episódio.
- **Arritmias ventriculares:** VT e VF são o risco mais grave, mas exigem outras bases.
- **Validação com Holter real** e, futuramente, dados de análogos espaciais ou de voo.
- **Dados NASA:** integrar indicadores do desafio em uma visão mais ampla de saúde.

## 13. Ordem de trabalho e bloqueios

1. Estrutura do repositório e ambiente.
2. Download e auditoria.
3. Pré-processamento e testes.
4. Atributos, SQI e baseline RR.
5. Experimento A com todos os modelos.
6. Experimentos B a I.
7. Inferência, stream e benchmark.
8. Painel de demonstração.
9. README, model card e figuras.
10. Rodar `make` do zero em um subconjunto para checar a reprodução.

Interrompa o usuário apenas se:

- as bases não puderem ser baixadas;
- a auditoria invalidar o desenho, por exemplo com AFIB insuficiente na validação externa;
- os recursos da máquina forem insuficientes até para um subconjunto.

## 14. Critério de pronto

- [ ] Um novo clone reproduz treino e avaliação pelos comandos documentados.
- [ ] Auditoria, experimentos A–I e benchmark publicados.
- [ ] README mostra resultado interno, externo, comparação com baseline, falsos alertas e limitações.
- [ ] Modelo final salvo, com inferência e painel funcionando sem internet.
- [ ] TCC e bases citados; aviso de "não é dispositivo médico" presente.

## 15. Contexto da competição

NASA Space Apps Challenge, 14–15/nov/2026. Envio abre em 14/11 às 9h e fecha em 15/11 às 23h59, no horário local. Desafio mais próximo: *Create Health Monitoring Software for Astronauts on Space Missions*.

Mantenha o repositório pronto até 12/11. Os recursos oficiais de cada desafio saem em 13/11, então deixe o projeto modular para receber dados NASA ou de agências parceiras.

**Não** alegue que os dados são da NASA nem de astronautas: as bases são clínicas, terrestres e de repouso.
