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
- **D9. Pendente para a etapa 5** (agora restrito a Shaoxing, ver D13): definir se `SINUS_OUTRO` entra nos negativos do treino.
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
