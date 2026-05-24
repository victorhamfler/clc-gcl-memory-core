# Answer Behavior Proposals Handover

Date: 2026-05-24

## Purpose

This handover records the selector-side proposal layer built after the answer-feedback memory bank and guard.

The development path is now:

```text
answer-level feedback
-> answer-feedback signal artifact
-> multi-run answer-feedback memory bank
-> answer-feedback bank guard
-> answer behavior proposals
```

All stages remain report-only. No resolver behavior, selector policy, runtime config, database rows, or learned artifacts are changed.

## Files Added

```text
eval/answer_behavior_proposal_eval.py
eval/answer_behavior_proposal_regression.py
```

Docs updated:

```text
docs/CLC_ARCHITECTURE_STATUS.md
docs/ARCHITECTURE_RESTRUCTURE_ROADMAP.md
```

## Output Schema

```text
answer_behavior_proposals/v1
```

The proposal artifact consumes:

```text
answer_feedback_memory_bank/v1
answer_feedback_bank_guard/v1
```

It emits behavior proposals only for guarded ready clusters. Every proposal includes:

- source cluster key;
- target behavior;
- evidence summary;
- preconditions;
- guard requirements;
- examples;
- `mutates_config: false`;
- `mutates_runtime: false`;
- `auto_promote: false`.

## Current Local Result

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_eval.py --bank ..\experiments\answer_feedback_memory_bank_results.json --guard ..\experiments\answer_feedback_bank_guard_results.json --out-json ..\experiments\answer_behavior_proposals_results.json --out-md ..\experiments\answer_behavior_proposals_report.md
```

Result:

```json
{
  "ok": true,
  "proposal_count": 3,
  "held_count": 0
}
```

Generated:

```text
C:\Users\victo\Desktop\projcod2\experiments\answer_behavior_proposals_results.json
C:\Users\victo\Desktop\projcod2\experiments\answer_behavior_proposals_report.md
```

## Current Proposals

### 1. Evidence-Backed Supported Answers

```text
proposal_require_evidence_backed_supported_answers
```

Meaning:

```text
Prefer answer forms that cite selected memory evidence and mark weak support when evidence is limited.
```

This comes from repeated `answer_correct` feedback.

### 2. OGCF Bridge-Risk Warning

```text
proposal_emit_ogcf_bridge_warning_when_supported
```

Meaning:

```text
When OGCF bridge diagnostics are present and retrieved evidence supports a cross-domain bridge answer, consider emitting a concise bridge-risk warning.
```

This comes from repeated `answer_bridge_warning_useful` feedback, and the bank guard confirms OGCF metadata is present.

### 3. Missing-Support Refusal

```text
proposal_preserve_missing_support_refusal
```

Meaning:

```text
When no selected evidence supports a query, preserve refusal or insufficient-support language instead of composing from weak raw candidates.
```

This comes from repeated negative `answer_missing_support` feedback with no selected memory evidence.

## Validation

Commands run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_regression.py
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_eval.py --bank ..\experiments\answer_feedback_memory_bank_results.json --guard ..\experiments\answer_feedback_bank_guard_results.json --out-json ..\experiments\answer_behavior_proposals_results.json --out-md ..\experiments\answer_behavior_proposals_report.md
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_bank_guard.py --bank ..\experiments\answer_feedback_memory_bank_results.json --out-json ..\experiments\answer_feedback_bank_guard_results.json --out-md ..\experiments\answer_feedback_bank_guard_report.md
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_policy_distribution_regression.py
..\.venv-torch\Scripts\python.exe -m py_compile .\eval\answer_behavior_proposal_eval.py .\eval\answer_behavior_proposal_regression.py
```

All passed.

## Next Step

The next selector-side step has now been added:

```text
answer_behavior_proposal_guard.py
```

It tests proposal safety directly:

- supported-answer proposals must not cite irrelevant evidence;
- bridge-warning proposals must not trigger on ordinary fact lookups;
- missing-support proposals must not suppress valid supported answers;
- stale/conflict cases must still disclose uncertainty;
- no proposal may mutate config automatically.

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_guard.py --proposals ..\experiments\answer_behavior_proposals_results.json --out-json ..\experiments\answer_behavior_proposal_guard_results.json --out-md ..\experiments\answer_behavior_proposal_guard_report.md
```

Result:

```json
{
  "ok": true,
  "proposal_count": 3,
  "issue_count": 0,
  "error_count": 0,
  "warning_count": 0
}
```

Generated:

```text
C:\Users\victo\Desktop\projcod2\experiments\answer_behavior_proposal_guard_results.json
C:\Users\victo\Desktop\projcod2\experiments\answer_behavior_proposal_guard_report.md
```

Only after this guard also passes on real Hermes logs should the memory-program session consider a configurable resolver behavior change.

Next selector-side target:

```text
answer_behavior_shadow_eval.py
```

It should simulate the guarded-ready proposals over controlled answer cases without modifying resolver code.
