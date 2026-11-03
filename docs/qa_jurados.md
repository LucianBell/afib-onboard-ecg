# Preparação para os jurados: revisão cética e respostas

Revisão feita do ponto de vista de um jurado técnico cético (cardiologia, ML, operações de voo). Cada resposta
aponta o arquivo de onde vem o número, para que possa ser aberto na hora.

**Regra de ouro para a apresentação:** dizer primeiro o que o projeto **não** mostra. Os números fortes (interno)
só valem acompanhados dos fracos (externo, ruído, ritmos parecidos, falsos alertas).

---

## 1. Alegações sem evidência (ou acima da evidência)

Revisei README, MODEL_CARD, painel e código. Os itens marcados "corrigido" foram reescritos nesta revisão; os
outros precisam ser ditos com a ressalva indicada.

| # | Alegação | Problema | Situação |
|---|---|---|---|
| 1 | "Bradi e taquicardia estão do lado não-AFIB, **então** FC alterada não é confundida com fibrilação" | No PTB-XL, o falso AFIB por janela é 9,2% em bradicardia e 6,6% em taquicardia, contra 3,4% em sinusal normal (`results/expE/false_afib_by_rate.csv`). O treino *tenta* ensinar isso, mas fora da fonte não basta. | **Corrigido** no README |
| 2 | "A regressão logística **generalizou melhor** que os outros modelos" | No PTB-XL, os IC 95% de AUROC da logística, do RF e do LightGBM se sobrepõem. Só a vantagem sobre a CNN é clara (`results/expB/all_models.csv`). | **Corrigido**: "pelo menos tão bem quanto, e melhor que a CNN" |
| 3 | A probabilidade de AFIB mostrada no painel é uma probabilidade | Calibrada só em Shaoxing. No PTB-XL, janelas com probabilidade prevista entre 0,5 e 0,9 são AFIB em apenas 3–24% dos casos (`results/expB/calibration_external.json`). | **Corrigido**: README e MODEL_CARD avisam. No painel, ler como escore e não como probabilidade. |
| 4 | "Roda no Raspberry Pi" / "pronto para o Pi" | Nunca foi executado num Pi. O benchmark é de um i7-1165G7 (`results/benchmark/benchmark_LucianDebian.json`). | Dizer: "projetado para o Pi; medido apenas num notebook; o script de benchmark está pronto para o Pi". |
| 5 | "Análise a bordo, durante o registro" | O fluxo Holter → Pi é simulado por replay de registros de 10 s. | Dizer "simulado". Faixa fixa no painel. |
| 6 | "Detecção precoce" | Significa o ritmo **presente** na janela, não previsão. Bases sem desfecho. | Usar sempre "detecção do ritmo na janela". |
| 7 | "Falsos alertas por dia ≈ 0,01" | Supõe janelas independentes de pacientes diferentes. Com erros correlacionados vai a ~4/dia no PTB-XL, e a 53–179/dia em quem tem ectopia (`results/expH/monitoring_sensitivity.csv`). | Nunca citar o 0,01 sozinho. |
| 8 | "O 'flutter' de Ningbo é AFIB mal rotulada" | Hipótese apoiada por 12 sinais idênticos rotulados AFIB/flutter (`results/audit/chapman_cross_source_duplicate_labels.csv`) e por 84% desses registros classificados AFIB (`results/expG/out_of_training.csv`). Não há laudo. | Dizer "forte indício", nunca "é". |
| 9 | "Com a escala do TCC, só a amplitude separa as bases (AUROC 1,00)" | Simula a escala *descrita no texto* do TCC (÷10³ vs. ÷10). Não rodamos o código do TCC. | Dizer "se a escala foi a descrita no texto…". |
| 10 | Regra de FC "com histórico da própria pessoa" | Os fatores 0,8 e 1,5 × mediana pessoal são escolhas de projeto, sem validação clínica (D42). | Apresentar como funcionalidade de demonstração. |
| 11 | `INCERTO` captura entradas fora do padrão | Captura só parte: o flutter vira AFIB em 55% e `INCERTO` em 15% (`results/expG/out_of_training.csv`). | Dizer que é mitigação parcial. |
| 12 | O SQI protege contra ruído | Com ruído muscular a −6 dB, a especificidade vai a 0,367 sem SQI e 0,547 com o SQI calibrado (`results/expF/robustness_sqi_calibrated.csv`). | Dizer que o SQI é fraco. |
| 13 | Motivação: "AFIB em astronautas" | Verificado: as Academias Nacionais recomendam mais ênfase em AFIB, e a prevalência é ≈5% em astronautas ativos, em idade mais jovem. **Mas o estudo de 2018 não observou nenhum episódio de AFIB em voo** (`results/reference/literature.json`). | Apresentar como argumento de risco, não como "AFIB é comum em órbita". |

---

## 2. Pontos fracos, do mais grave para o menos grave

1. **Nada foi validado em astronautas, em microgravidade, em exercício nem num Holter real.** Os dados são ECGs
   clínicos de repouso em hospital.
2. **Especificidade externa cai:** 0,988 → 0,957 (cerca de 3,4× mais janelas falso-positivas;
   `results/expB/external_validation.csv`). PPV por janela a 1% de prevalência: 0,449 interno e 0,190
   externo.
3. **Ritmos parecidos viram AFIB:** flutter 55%, taquicardia atrial 44%, ectopia 24–31%, arritmia sinusal
   15–21% (`results/expG/out_of_training.csv`).
4. **Falsos alertas reais provavelmente altos para algumas pessoas** (ectopia, arritmia sinusal; experimento H).
5. **Ruído muscular / movimento de eletrodo** derrubam a especificidade, e o SQI não segura (experimento F).
   Em voo há movimento.
6. **No ponto de operação externo, o baseline RR erra menos que o modelo:** 621 vs. 689 erros, McNemar
   p = 0,003 (`results/expD/summary.json`).
7. **Probabilidade descalibrada fora da fonte** (item 3 da seção 1).
8. **Teste interno quase "fácil":** negativos sinusais limpos de uma única fonte. A AUROC 0,9998 é teto, não
   desempenho real (D30).
9. **Viés de idade e população:** AFIB muito mais velha. Na faixa 30–54 anos só há 19 AFIB no teste interno
   (`results/expA/test_subgroups.csv`). As populações são chinesa e alemã.
10. **Sem identificador de paciente na Chapman:** a divisão é por registro. Mitigado por deduplicação e pela
    validação externa.
11. **Transparência sobre o protocolo:**
    - o teste A foi aberto duas vezes por um erro de serialização (D31, `results/expA/TEST_OPENED.json`);
    - a calibração do SQI e as análises de sensibilidade do H foram acrescentadas depois de ver resultados
      ruins (D37, D38). Ambas foram feitas na validação ou declaradas como análise *post hoc*.
12. **Votação reiniciada por janela ruim** pode repetir o alerta no mesmo episódio (D43).
13. **Sem medição no Raspberry Pi.**

---

## 3. Perguntas difíceis e respostas

### Sobre os números

**P1. "AUROC de 0,9998? Isso é bom demais. Onde está o vazamento?"**
É teto, não vazamento. O teste interno compara AFIB com ritmo sinusal limpo da mesma fonte, um problema
quase separável pela irregularidade RR. Mesmo o baseline sem aprendizado dá AUROC 0,9947 (`results/expA/test.json`).
Contra vazamento fizemos:
- deduplicação por hash do sinal (os 87 pares exatos encontrados na auditoria);
- imputação e padronização dentro de um Pipeline ajustado só no treino;
- escolha do modelo pré-registrada em commit antes de abrir o teste;
- testes automáticos de ausência de vazamento (`tests/test_no_leakage.py`).

O número que importa é o externo: AUROC 0,9968 e **especificidade 0,957** no PTB-XL, base nunca vista.

**P2. "Qual é o desempenho real esperado?"**
Não sabemos para astronautas. O melhor proxy é o PTB-XL:
- por janela, sensibilidade 0,990 e especificidade 0,957 (`results/expB/external_validation.csv`);
- com população que inclui ritmos parecidos, ruído e correlação dentro da pessoa, pior (experimentos F, G, H).

**P3. "Vocês superam o Holter ou o Apple Watch?"**
Não afirmamos isso. A literatura (smartwatch 86%/94%; Holter com IA 98% vs. 91% de sensibilidade) usa outros
testes e outros desfechos (`results/reference/literature.json`). Nosso argumento é análise a bordo, aberta,
offline, com comparação justa contra um baseline no mesmo teste.

**P4. "Por que o baseline ganha de vocês no PTB-XL?"**
No ponto de operação, o limiar da logística foi escolhido em Shaoxing, onde as classes se separam quase
perfeitamente. Por isso ficou muito baixo (prob ≥ 0,0105) e não transfere bem. Em ranqueamento o modelo é
melhor (ΔAUROC +0,011; ΔAUPRC +0,178, IC acima de 0; `results/expD/summary.json`). A correção natural seria
escolher o limiar numa validação multi-fonte. Não fizemos isso para não tocar o teste, e fica como próximo
passo.

**P5. "Quantos falsos alertas por dia um astronauta receberia?"**
Depende de suposições que não conseguimos verificar sem dados contínuos reais (`results/expH/`):

| Cenário | Falsos alertas por dia |
|---|---|
| Sem votação | ~115 |
| 3 de 3, janelas independentes | ~0,01 |
| 3 de 3, erros correlacionados (cada registro repetido por ~5 min) | ~4 |
| Pessoa com ectopia frequente | 53–179 |

Resposta honesta: para a maioria das pessoas, provavelmente entre "quase nenhum" e alguns por dia; para quem
tem ectopia frequente, inaceitável sem ajuste individual.

**P6. "E o tempo até o alerta?"**
Em simulação, mediana de 29 s para episódios de ~5 min, com sensibilidade de 1,000. Para episódios de ~1 min,
a sensibilidade é 0,960 (`results/expH/monitoring.csv`). Episódios artificiais, concatenados.

### Sobre os dados

**P7. "Os rótulos são confiáveis?"**
São laudos clínicos das bases, não revisados por nós. A auditoria achou problemas reais:
- 29% dos registros da Chapman usam códigos fora do dicionário oficial;
- dois códigos do dicionário estão errados;
- o "flutter" de Ningbo é suspeito;
- a "TV paroxística" de Ningbo coincide com SVT de Shaoxing em 21 de 26 cópias (`docs/data_audit.md`).

No PTB-XL, a análise restrita a laudos validados por humano dá especificidade 0,956, praticamente igual
(`results/expB/external_validation.csv`).

**P8. "Por que não usaram a Chapman inteira (45 mil ECGs)?"**
Porque ela junta dois hospitais, e toda a AFIB está em Shaoxing; Ningbo tem zero. Usar tudo faria o modelo
aprender "hospital = rótulo", o erro central que apontamos no TCC. Confirmamos a fronteira contra as contagens
oficiais por fonte do CinC 2021: 93 de 94 códigos idênticos (`results/audit/audit_summary.json`).

**P9. "Há o mesmo paciente no treino e no teste?"**
Na Chapman não há como saber, porque não existe identificador de paciente. Removemos duplicatas exatas, mas
exames diferentes da mesma pessoa podem cruzar a divisão. É uma limitação declarada (D19). A validação externa
no PTB-XL, outra base e outro país, não tem esse problema.

**P10. "A idade não explica tudo? AFIB é doença de idoso."**
Idade e sexo não entram no modelo; ele recebe só o sinal. Mas a idade é um confundidor: os atributos podem
carregar sinais de envelhecimento (morfologia). No teste interno, a faixa 30–54 anos tem só 19 AFIB
(sensibilidade 1,000; especificidade 0,994), um intervalo largo demais para conclusões
(`results/expA/test_subgroups.csv`). É o ponto mais importante para validar com uma população parecida com a
de astronautas.

### Sobre o sistema

**P11. "Por que regressão logística e não deep learning?"**
Testamos uma CNN 1D compacta. Ela não ganhou na validação, e foi a pior externamente (AUROC 0,9914 vs. 0,9968;
`results/expB/all_models.csv`). A regra de escolha foi pré-registrada: o modelo mais simples a até 0,010 de
AUPRC do melhor. A logística ocupa 34 KB, roda só com numpy, custa 0,05 ms por janela e é interpretável.

**P12. "Funciona num Raspberry Pi? Quanto consome?"**
Não medimos num Pi. Num notebook (i7, 1 thread):
- 3,6 ms por janela de 9,6 s;
- cerca de 104 MB de RSS com numpy e scipy (`results/benchmark/benchmark_LucianDebian.json`).

Não há motivo técnico para não caber num Pi, mas sem medição não afirmamos número. O script
`scripts/benchmark.py` identifica a placa automaticamente.

**P13. "O que acontece com movimento, exercício, EVA?"**
Simulamos ruído real de movimento de eletrodo e muscular (MIT-BIH NSTDB):
- a sensibilidade se mantém;
- a especificidade cai para 0,75–0,80 a 0 dB e para cerca de 0,35 a −6 dB (`results/expF/robustness.csv`).

O SQI ajuda pouco. Exercício e mudanças fisiológicas da microgravidade não foram testados. É o maior risco
técnico para uso em voo.

**P14. "E flutter, taquicardia atrial, extrassístoles?"**
São o principal modo de falha. O flutter vira AFIB em 55% das janelas (Shaoxing), a ectopia em 24–31%, e o
`INCERTO` captura só parte (`results/expG/out_of_training.csv`). Clinicamente, flutter também merece atenção,
mas é outro ritmo e precisa de tratamento próprio.

**P15. "Detecta taquicardia ou fibrilação ventricular?"**
Não, e não afirmamos isso. As bases quase não têm esses ritmos, e os poucos rótulos de Ningbo não são
confiáveis (D15). O TCC classificava FV e TV como AFIB com mais de 98% de confiança; nós preferimos não
alegar nada.

**P16. "Por que 9,6 s, 250 Hz e derivação I?"**
É a especificação do aparelho MP-IoT do TCC (sensor AD8232), mantida para compatibilidade. O pré-processamento
é idêntico no treino e no aparelho, e um teste confirma que somar uma constante ao sinal não muda a predição.
A conversão para 12 bits não afeta o desempenho (`results/expF/robustness.csv`).

**P17. "O que o painel mostra é real?"**
É replay de registros públicos do conjunto de teste, que o modelo nunca viu, convertidos para o formato do
aparelho. A faixa fixa diz "Não são dados de astronautas". As janelas do cenário "sinal ruim" que passam pelo
SQI não foram escondidas.

### Sobre o método e a integridade

**P18. "Como garantem que não escolheram o melhor resultado depois de ver o teste?"**
- A regra de escolha e o limiar foram commitados antes de qualquer treino.
- A escolha foi commitada antes de abrir o teste, e o script se recusa a rodar sem esse commit.
- A trava `TEST_OPENED.json` registra cada abertura.
- Houve **uma** reabertura por erro de serialização; está registrada e o cálculo é determinístico (D31).
- Dois ajustes vieram depois de ver resultados ruins e estão declarados: a calibração do SQI (feita na
  validação, D37) e as análises de sensibilidade do H (D38).

**P19. "Os números do README são confiáveis?"**
O README é gerado por código: todo número vem de um arquivo em `results/`, ou do config quando é constante de
projeto. A origem de cada valor está em `results/readme_numbers.json`, e um teste automático reprova números
digitados à mão (`tests/test_report_numbers.py`).

**P20. "Dá para reproduzir?"**
Sim, com `make reproduce` (ou `SUBSET=N` para um teste rápido). Rodamos isso num clone novo com subconjunto
(ver `docs/decisions.md`). Os resultados completos exigem ~4,3 GB de download e, somando os passos cronometrados nesta máquina, da ordem de meia hora de CPU.

**P21. "Qual é a crítica justa ao TCC?"**
O desenho dele confunde fonte com rótulo:
- normais vêm da Alemanha, arritmias da China, e a escala é diferente entre as bases;
- o teste é balanceado;
- não há validação externa;
- não há conjunto aberto.

Mostramos que, *com a escala descrita no texto*, só a amplitude separa as bases perfeitamente. Com unidades
corretas, a assinatura de base é moderada (AUROC 0,77–0,86; `results/expC/source_classifier.csv`). Ao
reproduzir o desenho do TCC com nosso modelo de ritmo, ele não explora a fonte. Os ~97% do TCC não estão
"errados" por si; eles não respondem à pergunta clínica. Tom: crítica ao método, com reconhecimento do
trabalho de partida.

### Sobre o valor para a NASA

**P22. "Por que isso importa para a NASA?"**
As Academias Nacionais recomendaram mais ênfase ao risco de AFIB e a estratégias para AFIB em voo longo. A
prevalência em astronautas ativos é de ≈5%, em idade mais jovem que na população geral
(`results/reference/literature.json`). Em missões longas, sem comunicação contínua com a Terra, a análise
precisa ser local. **Ressalva obrigatória:** o estudo de 2018 não observou AFIB em voo; o argumento é de risco.

**P23. "Por que não usaram dados da NASA?"**
Os recursos oficiais do desafio só saem em 13/11. O projeto é modular: novos dados entram pelo mesmo
pré-processamento (`src/preprocess.py`) e pela API `predict(window)`. Não afirmamos que os dados são da NASA
ou de astronautas.

**P24. "Qual é o próximo passo concreto?"**
1. Validar com Holter real em pessoas da faixa etária de astronautas, inclusive em exercício.
2. Medir no Raspberry Pi.
3. Tratar flutter e ectopia explicitamente.
4. Escolher o limiar e calibrar em validação multi-fonte.
5. Melhorar o SQI para movimento.
6. Testar em dados de análogos espaciais.

---

## 4. Frases para usar e para evitar

| Use | Evite |
|---|---|
| "detecção do ritmo presente na janela" | "previsão de AFIB" |
| "protótipo de pesquisa, apoio à decisão" | "diagnóstico", "dispositivo médico" |
| "validado externamente no PTB-XL, com queda de especificidade" | "acurácia de 99,9%" |
| "falsos alertas simulados, entre ~0,01 e ~4 por dia conforme a suposição; muito mais com ectopia" | "praticamente nenhum falso alarme" |
| "projetado para o Pi; medido num notebook" | "roda no Raspberry Pi em 3 ms" |
| "dados clínicos públicos, terrestres, de repouso" | "dados de astronautas", "dados da NASA" |
| "flutter e ectopia são o principal modo de falha" | "detecta arritmias" (genérico) |
