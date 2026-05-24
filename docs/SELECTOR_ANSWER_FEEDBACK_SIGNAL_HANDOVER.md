# Selector Answer Feedback Signal Handover

Date: 2026-05-24

## Purpose

This handover responds to:

```text
docs/MEMORY_SESSION_NEURAL_SYMBOLIC_OUTCOME_HANDOVER.md
```

The memory session added answer-level feedback, non-empty OGCF diagnostics in selector snapshots, and a controlled neural-symbolic holdout workflow. The selector session accepted that contract and added a report-only parser for answer-level supervision.

## Selector-Side Change

Added:

```text
eval/answer_feedback_signal_eval.py
```

Updated:

```text
docs/CLC_ARCHITECTURE_STATUS.md
docs/ARCHITECTURE_RESTRUCTURE_ROADMAP.md
```

The new eval reads linked outcome logs and writes:

```text
answer_feedback_controller_signals/v1
```

This artifact separates answer-level supervision from memory-row supervision. It does not mutate DB rows, selector config, resolver weights, or learned policy artifacts.

## What The Eval Checks

The eval verifies:

- answer feedback events exist;
- answer feedback rows link back to an `ask` operation;
- positive and negative answer signals are both present;
- bridge-warning answer feedback includes non-empty OGCF diagnostics;
- missing-support refusal feedback is present;
- all parsed signals remain report-only holdout/controller signals.

## Result On Memory Session Workflow

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_signal_eval.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl
```

Result:

```json
{
  "ok": true,
  "answer_feedback_count": 3,
  "signal_count": 3,
  "family_counts": {
    "answer_quality": 1,
    "bridge_warning_quality": 1,
    "missing_support_refusal": 1
  },
  "recommendation_counts": {
    "holdout_ready": 3
  }
}
```

Generated artifacts:

```text
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_signal_eval_results.json
C:\Users\victo\Desktop\projcod2\experiments\answer_feedback_signal_eval_report.md
```

## Validation Commands Run

```powershell
..\.venv-torch\Scripts\python.exe .\eval\neural_symbolic_outcome_holdout_workflow.py
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_signal_eval.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_policy_distribution_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
..\.venv-torch\Scripts\python.exe -m py_compile .\eval\answer_feedback_signal_eval.py .\serve.py .\eval\neural_symbolic_outcome_holdout_workflow.py
```

All passed.

## Recommendation For Memory Session

Keep the answer-level feedback contract and continue producing real Hermes logs with these labels. The most useful next memory-side contribution is not a new synthetic fixture; it is a real multi-session Hermes run that produces answer-level feedback across:

- correct supported answers;
- stale answers;
- wrong-scope answers;
- missing-support refusals;
- overconfident unsupported answers;
- useful bridge warnings;
- noisy bridge warnings;
- conflict not disclosed cases.

Please return:

- the outcome log path;
- the generated holdout candidate artifact;
- answer-feedback label counts;
- examples where OGCF metadata is present;
- examples where the answer was wrong despite high retrieval score;
- any memory-side resolver behavior that looked hardcoded and should become configurable.

The selector session will then aggregate the answer-feedback signal artifacts into a multi-run answer-feedback memory bank before proposing any learned resolver/controller change.
