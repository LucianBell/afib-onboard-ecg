# On-board atrial fibrillation detector for single-lead ECG (NASA Space Apps 2026)

> **Work in progress.** No results are reported yet. Research prototype and decision-support tool,
> **not a medical device and not a diagnosis**. Not validated in astronauts or in microgravity.
> The data are public, terrestrial, resting clinical ECGs (PhysioNet). They are **not NASA or astronaut data**.

Early detection of the rhythm present in each 9.6-s single-lead window (AFIB vs. sinus rhythm),
designed to run on board (Raspberry Pi), with a signal-quality gate, an RR-irregularity baseline
for comparison, external validation across independent databases and false-alarm control.
Starting point: Maggioni & Rebonatto (UPF, 2023), see `docs/`.

## Reproduce (so far)

```bash
make env                         # conda env "afib-onboard" (Python 3.12, pinned)
conda activate afib-onboard
make data                        # ~4.3 GB download from PhysioNet + checksum verification + lead-I cache
make audit                       # docs/data_audit.md and results/audit/
make test
```

Data sources, licences and citations: [DATA.md](DATA.md). Decisions: [docs/decisions.md](docs/decisions.md).

## Resumo (pt-BR)

Detector de fibrilação atrial a bordo, em ECG de derivação única, em desenvolvimento. Protótipo de
pesquisa, não é dispositivo médico. Os dados são clínicos, públicos e terrestres, não são da NASA
nem de astronautas.
