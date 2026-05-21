# Answer Type Outcome Batch Results Handover

Date: 2026-05-21

This handover is from the memory-program session to the selector-module session. It responds to `ANSWER_TYPE_SELECTOR_ARCHITECTURE_HANDOVER.md` by adding realistic linked ask/feedback outcome rows for answer-type boundaries, mining a new candidate file, and running the promotion gate.

## Outcome Batch

Outcome batch name:

`answer-type-boundaries-v1`

Events appended:

`48`

Ask events:

`12`

Feedback events:

`36`

The generator is idempotent and will skip this batch if it already exists in the log.

Generator command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\generate_claim_scope_outcome_samples.py --batch answer-type-boundaries-v1
```

## Batch Coverage

The batch covers the requested high-overlap answer-type boundaries:

- method/tool versus report filename
- report filename versus report color/theme
- owner/responsible versus deadline
- deadline versus owner and filename
- feedback-report filename versus owner/deadline
- GitHub upload policy versus calendar change policy
- narrow policy examples versus unrelated broad policy notes

## Candidate And Gate Artifacts

Candidate file:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_alias_candidates_v9.json`

Candidate report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_alias_candidates_v9_report.md`

Gate report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report.md`

Gate result:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_results.json`

Outcome replay report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report_outcome_replay.md`

## Gate Result

Promotion ready:

`False`

Required check summary:

| check | pass |
| --- | --- |
| `nested_config_ok` | `True` |
| `candidate_ab_ok` | `True` |
| `outcome_replay_ok` | `False` |
| `config_regression_ok` | `True` |
| `answer_type_regression_ok` | `True` |
| `answer_type_config_ok` | `True` |
| `answer_type_method_filename_ok` | `True` |
| `selector_guards_ok` | `True` |

Outcome replay coverage:

- events: `267`
- feedback rows: `167`
- evaluated positives: `69`
- evaluated negatives: `98`

## Failure Summary

Failed checks:

- `outcome_replay_ok`

Negative answer-type violations:

`0`

Negative claim-scope violations:

`1`

This is useful: the new answer-type rules appear to be doing their job, but the expanded outcome rows exposed a claim-scope leak around generic deadline questions and filename memories.

## Exact Failure Row

From `claim_scope_promotion_gate_report_outcome_replay.md` / `claim_scope_promotion_gate_results_outcome_replay.json`:

```text
query: What deadline should Hermes remember?
label: wrong_domain
source: v5/feedback_report_filename.md
text: Selector feedback report filename should be selector_feedback_report.md.
legacy_rank: 3
current_rank: 2
rank_delta: 1
legacy_claim_scope_score: 0.0
current_claim_scope_score: 0.333333
current_answer_type_score: 0.0
claim_scope_lift: 0.333333
answer_type_lift: 0.0
```

Interpretation:

The filename row is still wrong-domain for a generic deadline query, but current claim-scope scoring gives it a `0.333333` lift. The answer-type layer does not cause this failure because answer-type lift is `0.0` and there are no negative answer-type violations.

## New Answer-Type Rule Candidates

The best next answer-type candidate area remains policy split:

- `github_upload_policy`
- `calendar_change_policy`

The new batch includes policy split rows, but this should still be treated as candidate evidence only. Do not promote broad `policy`.

## Recommended Selector Action

1. Do not promote from V9 as-is because the gate is not promotion-ready.
2. Investigate the deadline claim-scope leak where a filename memory receives deadline claim-scope lift.
3. Consider adding `filename,file` to `claim_scope.excluded_terms.deadline`, or otherwise ensure filename/file-name memories do not receive deadline claim-scope lift unless they also contain due/date evidence.
4. Keep the answer-type changes: focused answer-type checks passed and `negative_answer_type_violations` remained `0`.
5. Continue policy split experimentation with narrow rules only: `github_upload_policy` and `calendar_change_policy`.

## Memory-Program Notes

The memory-program session changed only memory-owned outcome generation and reporting artifacts. Selector-owned configuration and selector architecture should remain owned by the selector session.
