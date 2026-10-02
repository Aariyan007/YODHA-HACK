# Laya decision layer: data, training, evaluation

Laya (https://huggingface.co/convaiinnovations/laya, Apache 2.0) is a 421M-parameter classifier. You give it a
"state" (text) and typed questions; it answers with labels and calibrated probabilities in one forward pass.
MediThread uses it for judgement calls only:

| Where | Questions (defined in `BackEnd/ai/laya_schema.py`) |
| --- | --- |
| Symptom triage (`POST /api/triage`) | `urgency` (emergency / urgent / routine / self_care), `specialist` (18 kinds of doctor) |
| Doctor console, each spoken line | `emergency_phrase`, `mentions_allergy`, `orders_medicine`, `gives_follow_up` |

**Safety contract.** The Python rules run first (`BackEnd/ai/triage_rules.py`, English, Malayalam script and Manglish).
Laya may raise an urgency level or add an emergency flag; it can never lower a level the rules set, remove a warning,
or name a diagnosis. If the service is down, slow, or its quality gate has not passed, the app answers from rules alone.
Drug interactions do not come from Laya: they come from the DDInter dataset (`BackEnd/scripts/build_ddi.py`).

## Pipeline

```bash
# 1. data (downloads open datasets, merges generated + hand-written text; Groq is only needed to regenerate ml/seed/generated_*.jsonl)
cd BackEnd && ./venv/bin/python ../ml/prepare_data.py          # writes ml/data/*.jsonl and SOURCES.json

# 2. train: Colab T4 (recommended, ml/train_laya_colab.ipynb) or on a Mac
python ml/train_laya.py --device mps --freeze-below 20 --epochs 2 --micro-batch 2 --grad-accum 16

# 3. evaluate, then copy the report next to the weights so the service can read its quality gate
python ml/eval.py --model ml/out/laya-medithread --name finetuned
mkdir -p models && cp -r ml/out/laya-medithread models/laya && cp ml/reports/finetuned.json models/laya/eval_report.json

# 4. run the stack with the model
docker compose -f docker-compose.yml -f docker-compose.ai.yml up -d --build --wait
```

Use a venv that has `laya` and `torch` for steps 2 and 3 (`pip install laya`); the backend venv does not need them.

## Data (see DATA_LICENSES.md and data/SOURCES.json)

- `gretelai/symptom_to_diagnosis` (Apache 2.0): real-language symptom descriptions. The diagnosis column is mapped to a specialist by OUR table; the model never outputs a diagnosis. Urgency here is a weak prior.
- `syntech-ai/medical-triage-500` (CC BY-NC 4.0, synthetic): 250 rows for urgency, with "immediate" downgraded to "urgent" unless a chest-pain or breathlessness red flag is present.
- Generated: `generate_synthetic.py` asks Groq for wording (English, Manglish, Malayalam script) for each scenario in `scenarios.py`; the labels come from the scenario table, not from the model. Marked synthetic; 14% held out.
- Hand-written test sets (`seed/handwritten.py`, written by a person): 67 triage messages and 33 red-team emergencies. They are never trained on.

## Reading the report

`reports/<name>.md` has accuracy, macro-F1, calibration error, per-language accuracy, **under-triage** (the model less urgent than the label: the dangerous direction), and the red-team gate: rules + model must flag every emergency message. The service enables the model only if the report clears `LAYA_MIN_URGENCY_ACC` (0.80), `LAYA_MIN_SPECIALIST_ACC` (0.70) and the red-team gate.

The red-team patterns were written by the same person as the rules, so the gate is a regression check, not proof of coverage. The test sets are small. Treat every number as a smoke check, not clinical validation.
