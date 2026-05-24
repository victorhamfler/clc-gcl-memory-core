# Answer Feedback Memory Bank Handover

Date: 2026-05-24

## Purpose

This handover records the selector-side implementation of the next roadmap step after answer-level feedback parsing:

```text
answer-level feedback logs -> answer-feedback signal artifacts -> multi-run answer-feedback memory bank
```

The implementation is report-only. It does not promote resolver weights, selector policy, runtime config, or learned artifacts.

## Files Added

```text
eval/answer_feedback_memory_bank.py
eval/answer_feedback_memory_bank_regression.py
test_corpora/answer_feedback_signals_a.json
test_corpora/answer_feedback_signals_b.json
```

Docs updated:

```text
docs/CLC_ARCHITECTURE_STATUS.md
docs/ARCHITECTURE_RESTRUCTURE_ROADMAP.md
```

## What The Memory Bank Does

The bank reads one or more artifacts with schema:

```text
answer_feedback_controller_signals/v1
```

It groups signals by answer-feedback family and label, then reports:

- support count;
- distinct source artifact count;
- distinct query count;
- positive and negative counts;
- mean rating;
- whether OGCF metadata was present for bridge-warning signals;
- examples for review;
- readiness state.

Output schema:

```text
answer_feedback_memory_bank/v1
```

Readiness is conservative:

- `ready` requires repeated support across enough artifacts and queries;
- bridge-warning clusters remain held unless OGCF metadata is present;
- missing linked operations are rejected;
- mixed positive/negative clusters are kept visible as `ready_mixed_outcome` when mature.

## Local Test Result

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_memory_bank_regression.py
```

Result:

```json
{
  "ok": true,
  "readiness_counts": {
    "ready": 3
  }
}
```

Local multi-run bank command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_memory_bank.py --signals ..\experiments\answer_feedback_signal_eval_results.json --signals .\test_corpora\answer_feedback_signals_b.json --out-json ..\experiments\answer_feedback_memory_bank_results.json --out-md ..\experiments\answer_feedback_memory_bank_report.md
```

Result:

```json
{
  "ok": true,
  "artifact_count": 2,
  "signal_count": 6,
  "cluster_count": 3,
  "readiness_counts": {
    "ready": 3
  }
}
```

Generated:

```text
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_memory_bank_results.json
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_memory_bank_report.md
```

## Interpretation

The current local bank is not proof that resolver behavior should change yet because one of the artifacts is a fixture. It proves the mechanism works:

```text
multiple answer-feedback runs can be aggregated into stable candidate behavior clusters
```

The three ready local clusters are:

- `answer_quality:answer_correct`;
- `bridge_warning_quality:answer_bridge_warning_useful`;
- `missing_support_refusal:answer_missing_support`.

## Next Best Development Direction

The next selector-side development added a guard/eval that uses this memory bank to test proposed answer behavior before any learned resolver scorer exists.

Added:

```text
eval/answer_feedback_bank_guard.py
eval/answer_feedback_bank_guard_regression.py
```

The guard verifies:

- bridge-warning clusters require OGCF diagnostics;
- missing-support refusal clusters do not encourage hallucinated answers;
- supported-answer clusters require selected evidence;
- mixed positive/negative clusters stay report-only;
- no resolver config is changed automatically.

Local command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_bank_guard.py --bank ..\experiments\answer_feedback_memory_bank_results.json --out-json ..\experiments\answer_feedback_bank_guard_results.json --out-md ..\experiments\answer_feedback_bank_guard_report.md
```

Result:

```json
{
  "ok": true,
  "cluster_count": 3,
  "ready_cluster_count": 3,
  "issue_count": 0
}
```

Generated:

```text
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_bank_guard_results.json
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_bank_guard_report.md
```

After this checkpoint, real Hermes/memory-session answer-feedback artifacts can replace the fixture artifact. The next true development step is not promotion yet; it is to run the same bank plus guard on real multi-session logs and then design an answer-behavior proposal eval.
