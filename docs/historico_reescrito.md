# Histórico reescrito: correspondência de hashes

Em 2026-11-03, antes da publicação no GitHub, o histórico foi reescrito com `git filter-branch` para remover o
PDF do TCC de partida, uma obra de terceiros não redistribuída (D49 em `docs/decisions.md`). Conteúdo, ordem,
datas e mensagens dos commits foram preservados. **Só os hashes mudaram.**

Os documentos que citam hashes antigos (`docs/decisions.md`, `HANDOFF.md`, `results/expA/selection.json` e
`results/expA/TEST_OPENED.json`) continuam válidos por meio desta tabela. A ordem dos commits, que prova que
as regras e a escolha do modelo vieram antes de abrir os testes, é a mesma. Uma cópia completa do histórico
original (`git bundle`) foi mantida fora do repositório.

| Hash original | Hash publicado | Commit |
|---|---|---|
| `cab7b1d` | `15ab835` | Estrutura do repositório e ambiente fixado |
| `c25965b` | `c1d7acd` | Download, indexação e auditoria das bases Chapman e PTB-XL |
| `a03d09a` | `19f3b66` | Pré-processamento, detector de QRS, atributos, SQI e baseline RR |
| `782757e` | `0ea524e` | Experimento A, fase dev: CV no treino, calibração/limiar na validação e escolha pré-registrada |
| `e4e402f` | `5787f12` | Experimento A, fase test: avaliação única no teste de Shaoxing |
| `d1047fe` | `a477bc6` | Fixa regras dos experimentos B-I (INCERTO, N de M, SNR) antes de rodá-los |
| `473513c` | `4ad04a6` | Regra de calibração do SQI fixada antes de rodar (experimento F, fase 2) |
| `7f80593` | `dda61b3` | Experimentos B-I: validação externa, confusão de fonte, baseline, FC alterada, ruído, ritmos fora de treino, monitoramento simulado e referência ao TCC |
| `1a36401` | `5bcbfc8` | Inferência a bordo, simulação de stream, benchmark e painel offline |
| `f695475` | `492a266` | README, MODEL_CARD e figuras gerados de results/; análise do TCC; modo de reprodução |
| `f6c2789` | `8af89b7` | Revisão cética: perguntas e respostas para jurados, correção de alegações e calibração externa |
| `720403d` | `bd01939` | make report tolerante a subconjunto (n/d onde faltar dado), achado na reprodução do zero |
| `d6a0a31` | `af34478` | Teste de vazamento compatível com subconjunto (achado na reprodução do zero) |
| `50cef09` | `f28325d` | Registra a reprodução do zero em subconjunto (D47) |
| `85a0737` | `c624128` | Relatório de passagem com estado, resultados e conclusões do projeto |
| `1e0742f` | `f98806f` | README principal em pt-BR (gerado de results/, números em formato brasileiro); versão em inglês em README.en.md |
| `3534724` | `b3cdd7d` | Remove o PDF do TCC do repositório (obra de terceiros; citação completa em DATA.md) |
