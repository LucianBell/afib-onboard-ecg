# Data sources

No raw data is stored in this repository. `make data` downloads the archives from
PhysioNet into `data/raw/` (git-ignored). Archive sizes and SHA-256 hashes of the
copies used are written to `results/audit/data_manifest.json`.

| Base | Version | Licence | DOI | Download |
|---|---|---|---|---|
| A large scale 12-lead electrocardiogram database for arrhythmia study ("Chapman-Shaoxing/Ningbo") | 1.0.0 (24 Aug 2022) | Creative Commons Attribution 4.0 International | [10.13026/wgex-er52](https://doi.org/10.13026/wgex-er52) | zip, 2,498,709,074 bytes |
| PTB-XL, a large publicly available electrocardiography dataset | 1.0.3 (9 Nov 2022, latest version on 2026-11-03) | Creative Commons Attribution 4.0 International | [10.13026/kfzx-aw45](https://doi.org/10.13026/kfzx-aw45) | zip, 1,839,504,686 bytes |

| MIT-BIH Noise Stress Test Database (noise records `bw`, `em`, `ma` only; used for robustness experiment F) | 1.0.0 | Open Data Commons Attribution License v1.0 | [10.13026/C2HS3T](https://doi.org/10.13026/C2HS3T) | 6 files, checked against the published SHA256SUMS |

| PhysioNet/CinC Challenge 2021 SNOMED mapping tables (`dx_mapping_scored.csv`, `dx_mapping_unscored.csv`; used only to resolve codes missing from the Chapman dictionary) | GitHub `physionetchallenges/evaluation-2021`, commit `e2a75fc` | BSD-2-Clause | – | 2 small CSV files, SHA-256 in `data_manifest.json` |

Licences and citations were checked (citation metadata via Crossref) on the PhysioNet project pages on 2026-11-03.
CC BY 4.0 allows reuse and derived works with attribution, which is compatible with
the MIT licence of the code (data are not redistributed).

## Required citations

**Chapman-Shaoxing/Ningbo (ecg-arrhythmia 1.0.0)**

- Zheng, J., Guo, H., & Chu, H. (2022). A large scale 12-lead electrocardiogram database for arrhythmia study (version 1.0.0). *PhysioNet*. RRID:SCR_007345. https://doi.org/10.13026/wgex-er52
- Original publication: Zheng, J., Chu, H., Struppa, D., Zhang, J., Yacoub, S. M., El-Askary, H., Chang, A., Ehwerhemuepha, L., Abudayyeh, I., Barrett, A., Fu, G., Yao, H., Li, D., Guo, H., & Rakovski, C. (2020). Optimal multi-stage arrhythmia classification approach. *Scientific Reports*, 10, 2898. https://doi.org/10.1038/s41598-020-59821-7
- Related data descriptor (Chapman 10k subset): Zheng, J., Zhang, J., Danioko, S., Yao, H., Guo, H., & Rakovski, C. (2020). A 12-lead electrocardiogram database for arrhythmia research covering more than 10,000 patients. *Scientific Data*, 7, 48. https://doi.org/10.1038/s41597-020-0386-x

**PTB-XL (1.0.3)**

- Wagner, P., Strodthoff, N., Bousseljot, R., Samek, W., & Schaeffter, T. (2022). PTB-XL, a large publicly available electrocardiography dataset (version 1.0.3). *PhysioNet*. RRID:SCR_007345. https://doi.org/10.13026/kfzx-aw45
- Original publication: Wagner, P., Strodthoff, N., Bousseljot, R.-D., Kreiseler, D., Lunze, F. I., Samek, W., & Schaeffter, T. (2020). PTB-XL, a large publicly available electrocardiography dataset. *Scientific Data*, 7, 154. https://doi.org/10.1038/s41597-020-0495-6

**MIT-BIH Noise Stress Test Database (1.0.0)**

- Moody, G. B., Muldrow, W. E., & Mark, R. G. (1984). A noise stress test for arrhythmia detectors. *Computers in Cardiology*, 11, 381–384.

**PhysioNet standard citation** (as requested on both project pages)

- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. *Nature Health*, 1, 792–795. https://doi.org/10.1038/s44360-026-00096-z
- Goldberger, A. L., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet. *Circulation*, 101(23), e215–e220. https://doi.org/10.1161/01.CIR.101.23.e215

**Starting point of this project**

- Maggioni, A. F., & Rebonatto, M. T. (2023). *Inteligência Artificial aplicada a análise de Eletrocardiograma*. Trabalho de Conclusão de Curso, Ciência da Computação, Universidade de Passo Fundo (UPF). The PDF is not redistributed in this repository.

## Derived local files (never committed)

- `data/interim/`: lead-I cache (mV, 500 Hz) and per-record index with labels and quality statistics.
- `data/processed/`: preprocessed windows (250 Hz, 2,400 samples), features, SQI and trained candidate models.
- `data/demo/demo_pack.npz`: replay pack for the dashboard and the stream simulation. It holds 40 test-split
  Shaoxing records per scenario, converted to the device format, plus noisy versions built with the NSTDB
  records. It is created locally by `make demo-data` and never redistributed.

## Important caveats

- Both databases are terrestrial, clinical, resting 10-second 12-lead ECGs. **They are not NASA data and not astronaut data.**
- Label dictionaries are read from the files shipped with each database (`ConditionNames_SNOMED-CT.csv`, `scp_statements.csv`), complemented by the CinC 2021 mapping tables for codes missing from the Chapman dictionary; no SNOMED code is hard-coded.
- The *ecg-arrhythmia* release combines two sources (Shaoxing, Ningbo) without saying so in the headers; the boundary was inferred and verified (`docs/data_audit.md` §2.1). Ningbo's "atrial flutter" and "paroxysmal VT" labels are unreliable (see audit).
- Units are read from each WFDB header with `wfdb`; the TCC's Annex A interpretation of the `.hea` fields is not used.
