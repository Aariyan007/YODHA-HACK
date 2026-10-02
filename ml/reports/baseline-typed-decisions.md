# Laya evaluation: baseline-typed-decisions

Model: `typed-decisions`  |  run: 2026-10-02 10:26

## test_handwritten (n=67, median 719.8 ms)
- urgency: accuracy 0.552, macro-F1 0.565, ECE 0.486, under-triage 14, over-triage 16, emergency recall 0.278
  - by language: {'en': 0.833, 'ml': 0.263, 'ml-latin': 0.167}; rules+model accuracy 0.716, under-triage 3
- specialist: accuracy 0.478, macro-F1 0.485, ECE 0.093

## test_gretel (n=212, median 719.7 ms)
- specialist: accuracy 0.524, macro-F1 0.52, ECE 0.238

## test_generated_held_out (n=57, median 817.0 ms)
- urgency: accuracy 0.526, macro-F1 0.561, ECE 0.444, under-triage 25, over-triage 2, emergency recall 0.395
  - by language: {'en': 0.826, 'ml': 0.227, 'ml-latin': 0.5}; rules+model accuracy 0.561, under-triage 23
- specialist: accuracy 0.386, macro-F1 0.432, ECE 0.194

## Red-team emergencies (n=33)
- rules only: 33/33  |  model only: 14/33  |  **rules + model: 33/33**
- gate: PASS


Honest limits: the test sets are small. The hand-written set has 67 messages; the generated held-out set shares a generator with the training data; consultation-line labels are synthetic. Treat numbers as a smoke check, not clinical validation.