# Análise do TCC de partida

**Referência:** Maggioni, A. F.; Rebonatto, M. T. *Inteligência Artificial aplicada a análise de
Eletrocardiograma*. TCC, Ciência da Computação, Universidade de Passo Fundo, 2023
(`docs/PF2023AugustoFelipeMaggioni_cópia.pdf`).

Os números atribuídos ao TCC neste documento são os que ele mesmo relata, com a página indicada. Os
nossos resultados não são repetidos aqui: o texto aponta para os arquivos em `results/`, e os números
gerados por código estão no README.

## O que o TCC fez

- **Bases:** Chapman ("A large scale 12-lead electrocardiogram database for arrhythmia study") para as
  arritmias e PTB-XL para os normais (seção 3.1, p. 8–9).
- **Sinal-alvo:** aparelho MP-IoT (sensor AD8232), derivação I, 250 Hz, 2.400 amostras (~9,6 s),
  apenas valores positivos (seção 2.3, p. 4–5).
- **Pré-processamento:** notch de 50 Hz → Butterworth 0,05–30 Hz de ordem 4 → LOESS (janela 10) →
  interpolação cúbica de 500 para 250 Hz → deslocamento para valores positivos → Butterworth de ordem 2
  → MinMax 0–10 (seções 3.2–3.3).
- **Dados:** 1.780 registros por classe (undersampling), 80/20, validação cruzada em 5 dobras (seção 3.3,
  Tabela 1).
- **Modelo RHCB5:** Conv1D + Bi-LSTM + camadas densas, 60 épocas, Adam (seção 3.5).
- **Resultados:** 3 classes (AFIB, SB, normal), acurácia de 96,91% e especificidade de 98,45% (Tabela 3);
  4 classes, acurácia de 87,42% (Tabela 2); matriz de confusão na Tabela 4.
- **Validação externa ao laboratório:** 15 eventos do simulador Fluke (Tabela 5) e 5 pessoas com o
  MP-IoT (Tabela 6).

## Problemas e como este projeto os trata

| # | Problema no TCC | Evidência no próprio TCC | Como tratamos / o que medimos |
|---|---|---|---|
| 1 | **Confusão de fonte de dados.** Normais vêm do PTB-XL (Alemanha) e arritmias da Chapman (China), então base e rótulo coincidem. | Seções 3.1.1–3.1.2. A escala também difere: Chapman ÷ 10³ (p. 9) e PTB-XL ÷ 10 (Anexo A, p. 23). | Experimento C (`results/expC/`): só a amplitude, na escala do TCC, separa as bases perfeitamente. Com unidades corretas a assinatura é moderada. O treino usa uma única fonte (Shaoxing), e a validação externa é feita no PTB-XL (experimento B). |
| 2 | **A própria Chapman tem duas fontes** (Shaoxing e Ningbo), e só Shaoxing tem AFIB. | Não discutido no TCC. | Auditoria (`docs/data_audit.md` §2.1) e D12–D14 em `docs/decisions.md`. |
| 3 | **Teste balanceado artificialmente** (33% por classe). | Tabela 4: 356 por classe. | Métricas na prevalência natural, PPV em prevalências hipotéticas e falsos alertas por dia (experimento H). O teste balanceado é usado só como referência no experimento I. |
| 4 | **Vazamento possível:** normalização antes da divisão, "validação" e "teste" misturados, divisão sem respeitar paciente. | Seção 3.3 (MinMax antes da divisão); seção 3.6 (escolha pelo menor loss sobre as próprias dobras). | Normalização por janela, sem escalonamento global. Imputação e padronização ficam dentro do Pipeline, ajustado só no treino. Deduplicação por hash. PTB-XL usa `strat_fold`, que respeita paciente. Escolha do modelo pré-registrada, e teste aberto uma única vez (`results/expA/TEST_OPENED.json`). Testes em `tests/test_no_leakage.py`. |
| 5 | **Conjunto fechado:** FV e TV viraram AFIB com mais de 98% de confiança, e assistolia virou SB com 99%. | Tabela 5, IDs 8 e 11–15. | Estado `INCERTO` (fora do padrão ou confiança baixa) e camada de SQI. O experimento G mede quanto de cada ritmo não treinado vira AFIB, e a limitação continua relevante. Não afirmamos nada sobre TV/FV. |
| 6 | **Validação real muito pequena e sem laudo.** O caso "insuficiência cardíaca → AFIB" não confirma nada, porque insuficiência cardíaca não é ritmo. | Tabela 6. | Validação externa com cerca de 1,4 mil AFIB do PTB-XL. Validação real em Holter continua como próximo passo. |
| 7 | **Inconsistências internas.** | O resumo cita 66.989 dados, a seção 3.1 cita 44.217 e o treino usa 7.120. O Butterworth é chamado de FIR (p. 10), mas é IIR. Precisão de 63,69% no RHCB4 (Tabela 3), provável erro de digitação. A especificidade macro de 89,66% (Tabela 2) não bate com a matriz da Tabela 4. O texto diz "Fibrilação Arterial". | Contagens geradas por código (`results/audit/`). Filtros descritos como IIR (SOS, `sosfiltfilt`). Todas as métricas saem do mesmo código de avaliação (`src/evaluate.py`). |
| 8 | **Anexo A incorreto:** em `16+24 1000/mV 16 0 -49 15041 0 I`, o `16+24` é o formato, `1000/mV` o ganho, `16` os bits do A/D, `-49` o primeiro valor e `15041` o checksum. Os rótulos usam SNOMED CT, não CID. | Anexo A, p. 22. | Unidades lidas do cabeçalho com `wfdb` e conferidas empiricamente (`docs/data_audit.md` §4). Rótulos lidos dos dicionários SNOMED/SCP, mais o dicionário complementar do CinC 2021. |

Conferência da especificidade macro de 4 classes a partir da Tabela 4 (cálculo nosso sobre os números do
TCC): para cada classe, especificidade = VN / (VN + FP), com 1.068 negativos por classe. AFIB: FP = 15 →
0,986. SB: FP = 60 → 0,944. SI: FP = 56 → 0,948. Normal: FP = 48 → 0,955. A média dá cerca de 0,958, e não
os 89,66% relatados.

## O que reaproveitamos

As bases (com outro desenho de rótulos), o cenário de sinal limitado do MP-IoT (derivação I, 250 Hz,
2.400 amostras, 0,05–30 Hz, A/D positivo; ver `simulate_device()`), o notch de 50 Hz e o passa-banda
Butterworth. LOESS e interpolação cúbica ficaram como ablação não executada (D22).
