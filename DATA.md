# Data sources

No raw data is stored in this repository. `make data` downloads the archives from
PhysioNet into `data/raw/` (git-ignored). Archive sizes and SHA-256 hashes of the
copies used are written to `results/audit/data_manifest.json`.

| Base | Version | Licence | DOI | Download |
|---|---|---|---|---|
| A large scale 12-lead electrocardiogram database for arrhythmia study ("Chapman-Shaoxing/Ningbo") | 1.0.0 (24 Aug 2022) | Creative Commons Attribution 4.0 International | [10.13026/wgex-er52](https://doi.org/10.13026/wgex-er52) | zip, 2,498,709,074 bytes |
| PTB-XL, a large publicly available electrocardiography dataset | 1.0.3 (9 Nov 2022, latest version on 2026-11-03) | Creative Commons Attribution 4.0 International | [10.13026/kfzx-aw45](https://doi.org/10.13026/kfzx-aw45) | zip, 1,839,504,686 bytes |

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

**PhysioNet standard citation** (as requested on both project pages)

- Pollard, T., Moody, B. E., Lehman, L., Gow, B., Fernandes, C., Xie, C., Johnson, A., Mark, R. G., & Heldt, T. (2026). PhysioNet as a global platform for biomedical research. *Nature Health*, 1, 792–795. https://doi.org/10.1038/s44360-026-00096-z
- Goldberger, A. L., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet. *Circulation*, 101(23), e215–e220. https://doi.org/10.1161/01.CIR.101.23.e215

**Starting point of this project**

- Maggioni, A. F., & Rebonatto, M. T. (2023). *Inteligência Artificial aplicada a análise de Eletrocardiograma*. Trabalho de Conclusão de Curso, Ciência da Computação, Universidade de Passo Fundo (UPF). File: `docs/PF2023AugustoFelipeMaggioni_cópia.pdf`.

## Important caveats

- Both databases are terrestrial, clinical, resting 10-second 12-lead ECGs. **They are not NASA data and not astronaut data.**
- Label dictionaries are read from the files shipped with each database (`ConditionNames_SNOMED-CT.csv`, `scp_statements.csv`); no SNOMED code is hard-coded.
- Units are read from each WFDB header with `wfdb`; the TCC's Annex A interpretation of the `.hea` fields is not used.
