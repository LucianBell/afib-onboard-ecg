## 9. Leitura da auditoria

*Texto interpretativo mantido à mão. Os números citados estão nas seções acima, geradas de `results/audit/`.*

1. **A Chapman são duas bases.** Os registros até JS10646 vêm de Chapman-Shaoxing e os seguintes de Ningbo
   (seção 2.1). A fronteira foi inferida pela mudança de vocabulário e conferida contra as contagens por fonte
   publicadas pelo CinC 2021, com 93 de 94 códigos idênticos. **Toda a AFIB está em Shaoxing**: Ningbo tem zero.
   Misturar os sinusais de Ningbo com a AFIB de Shaoxing repetiria o problema central do TCC (fonte ≡ rótulo).
2. **O "flutter atrial" de Ningbo não é confiável.** Os 12 sinais idênticos que Shaoxing rotula como AFIB
   aparecem em Ningbo com o código de flutter (seção 7). Isso é compatível com "AF" (fibrilação, no uso
   comum) ter sido convertido para o código SNOMED de flutter. É uma hipótese: não há laudo para confirmar.
   Os ~7,6 mil "flutter" de Ningbo ficam fora das análises principais.
3. **Ritmos ventriculares: sem cobertura utilizável.** PTB-XL não tem nenhum enunciado de ritmo ventricular.
   Os rótulos de TV/FV de Ningbo vêm só do dicionário complementar, e 21 dos 26 sinais de SVT de Shaoxing
   duplicados em Ningbo receberam "TV paroxística". Esses rótulos não sustentam nenhuma afirmação sobre
   detecção de TV/FV.
4. **O dicionário oficial da Chapman está incompleto e tem erros.** 29% dos registros usam códigos ausentes
   dele, e dois acrônimos (AVNRT, SAAWR) aparecem nos cabeçalhos com códigos diferentes dos do dicionário.
   Sem o dicionário complementar, registros com marcapasso, ritmo juncional ou bloqueio de ramo cairiam como
   "sinusal normal".
5. **Unidades corretas.** Ganho 1000/mV em todos os registros de ambas as bases. A amplitude mediana do QRS na
   derivação I fica em 0,77 mV (Chapman) e 0,92 mV (PTB-XL), valores plausíveis. A interpretação de
   4,88 µV/bit daria medianas acima de 3 mV na derivação I, implausíveis. Há diferença de escala entre bases
   (~20%), absorvida pela normalização por janela.
6. **Integridade do sinal boa.** Apenas 3 registros inválidos (Chapman), nenhum NaN e todos com 5.000 amostras.
   Derivações planas aparecem em 1.495 registros da Chapman, quase todos de Ningbo, mas a derivação I é plana
   em só 1.
7. **Duplicatas.** São 87 pares exatos na Chapman: 71 entre Shaoxing e Ningbo e 13 dentro de Shaoxing.
   Nenhuma no PTB-XL nem entre bases. Precisam ser removidas antes de dividir treino e teste, senão há
   vazamento.
8. **Paciente.** A Chapman não tem identificador de paciente, então a divisão de Shaoxing é por registro
   (limitação declarada). O PTB-XL tem `patient_id`, e nenhum paciente aparece em mais de uma `strat_fold`.
9. **Idade é um confundidor forte.** A AFIB tem mediana de 72–75 anos, contra 52–64 nos grupos sinusais. Só 8–11% da
   AFIB está na faixa de 30 a 55 anos, então os subgrupos "idade de astronauta" terão intervalos largos.
10. **Volume suficiente: o desenho continua viável**, com o ajuste do item 1. Shaoxing tem 1.779 AFIB e 6.669
    sinusais (normal + outro + bradi + taqui) para o experimento A. O PTB-XL tem 1.477 AFIB para a validação
    externa (experimento B), bem acima do mínimo para intervalos de confiança úteis. O sentido inverso também
    é viável: treinar no PTB-XL (folds 1–8: 1.181 AFIB) e testar em Shaoxing.
