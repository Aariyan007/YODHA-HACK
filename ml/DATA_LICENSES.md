# Data sources and licences

MediThread uses open datasets as reference data and for training. This file lists each one with its licence.
Check a dataset's own page before reusing it outside this project.

| Data | Used for | Where it lives | Licence |
| --- | --- | --- | --- |
| DDInter 2.0 (drug-drug interactions), https://ddinter2.scbdd.com/ , Computational Biology & Drug Design Group | Interaction warnings in `ai/safety.py` | `BackEnd/data/ddi/` (built by `scripts/build_ddi.py`, not committed) | CC BY-NC-SA 4.0 (non-commercial). Fine for this project, not for a paid product. |
| Curated interaction pairs and brand-to-generic map | Patient-friendly messages for the interactions that matter most in India | `BackEnd/ai/safety.py` | Written for this project |
| Training data for Laya (triage urgency, specialist, consultation lines) | Fine-tuning | `ml/data/` (built by `ml/prepare_data.py`, not committed) | Per source, listed in `ml/data/SOURCES.json` after a build |
| Laya models, https://huggingface.co/convaiinnovations/laya | Decision classifier | `models/laya/` (not committed) | Apache 2.0 |

DDInter citation: Xiong G. et al., "DDInter: an online drug-drug interaction database towards improving clinical
decision-making and patient safety", Nucleic Acids Research 2022; DDInter 2.0, Nucleic Acids Research 2025.

All data here is reference material, not medical advice. Nothing in the app diagnoses a condition.
