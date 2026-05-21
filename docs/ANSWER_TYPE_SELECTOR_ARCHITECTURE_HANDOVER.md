# Answer Type Selector Architecture Handover

Date: 2026-05-21

This handover is from the selector-module session to the memory-program session. It summarizes the newest selector architecture changes and what the memory-program session should do next when generating outcome logs or proposing selector improvements.

## Boundary Between Sessions

- The selector-module session owns selector architecture, `claim_scope`, `answer_type`, promotion-gate tests, and permanent selector config.
- The memory-program session owns broader memory-program behavior, realistic interaction/outcome generation, outcome labels, and handoff reports.
- The memory-program session should not directly promote new selector rules. It should generate outcome evidence, mine or propose candidates, run the gate when appropriate, and hand results back to this selector session.

## Important Architecture Change

The selector now has two configurable retrieval-control layers:

1. `claim_scope`
2. `answer_type`

Both are loaded from nested config in:

`C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core\config.yaml`

The nested YAML parser was fixed so nested maps now load correctly. This matters because before the fix, nested `slot_aliases`, `excluded_terms`, and `answer_type.rules` could flatten or disappear from runtime.

The promotion gate now includes a direct parser regression:

`nested_config_ok`

Do not trust selector config changes unless this remains `True`.

## Current Answer-Type Rules

The selector currently has these answer-type rules:

- `owner_relation`
- `deadline`
- `method_choice`
- `report_filename`

These rules are not broad topic aliases. They are answer-shape boundaries that help the selector decide whether a memory answers the kind of question being asked.

### Owner/Deadline Boundary

Purpose:

- Owner questions should prefer owner/assignment/responsibility memories.
- Deadline questions should prefer due/date memories.
- Owner notes should not answer deadline questions unless they also contain due/date evidence.

Current tested behavior:

- owner-vs-deadline regression passes
- outcome replay has zero negative answer-type violations

### Method/Filename Boundary

Purpose:

- Method/tool questions should prefer method/tool choice memories.
- Filename/file-name questions should prefer actual filename memories.
- Report-color or generic report memories should not be boosted as filename answers just because they contain the word `report`.

Important detail:

`report_filename` uses `positive_requires_any: filename,file,md` so `report` alone is not enough to trigger a positive filename answer-type score.

## Current Required Promotion Gate Checks

Run from:

`C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core`

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py --include-selector-guards --candidates ..\experiments\claim_scope_alias_candidates_v8.json
```

The gate must report:

```text
nested_config_ok: True
candidate_ab_ok: True
outcome_replay_ok: True
config_regression_ok: True
answer_type_regression_ok: True
answer_type_config_ok: True
answer_type_method_filename_ok: True
selector_guards_ok: True
```

Latest known selector-session result:

```text
Promotion ready: True
evaluated positives: 57
evaluated negatives: 74
negative_claim_lift_violations: 0
negative_answer_type_violations: 0
```

## New Regression Files

The memory-program session should know these now exist:

- `eval/config_nested_parser_regression.py`
- `eval/answer_type_relation_regression.py`
- `eval/answer_type_config_regression.py`
- `eval/answer_type_method_filename_regression.py`
- `eval/claim_scope_promotion_gate.py`

Reports are written under:

`C:\Users\victo\Desktop\projcod2\experiments\`

Key reports:

- `config_nested_parser_regression_report.md`
- `answer_type_relation_regression_report.md`
- `answer_type_config_regression_report.md`
- `answer_type_method_filename_regression_report.md`
- `claim_scope_promotion_gate_report.md`

## What The Memory-Program Session Should Test Next

Generate realistic linked ask/feedback outcome rows for answer-type boundaries. Focus on cases where lexical/topic overlap is high but answer type differs.

Recommended next batches:

### 1. Method vs Filename vs Report Attribute

Create interactions around:

- "What radar method should Victor use?"
- "Which radar tool is required?"
- "What radar report filename should be used?"
- "What file name should the radar report have?"
- "What radar report color/theme should be used?"

Label wrong-domain rows where:

- filename memories answer method/tool questions
- method/tool memories answer filename questions
- report color/theme memories answer filename questions

### 2. Owner vs Deadline vs Filename

Create interactions around:

- "Who owns the selector feedback report?"
- "Who is responsible for the report?"
- "When is the selector feedback report due?"
- "What deadline should Hermes remember?"
- "What filename should the feedback report use?"

Label wrong-domain rows where:

- owner memories answer deadline questions
- deadline memories answer owner questions
- filename memories answer owner or deadline questions

### 3. Policy Split Boundary

This is not promoted yet as `answer_type`, but it is a good next candidate area.

Create interactions around:

- GitHub upload policy
- calendar change policy
- approval/manual confirmation rules
- unrelated broad policy notes

The goal is to determine whether a future answer-type boundary should split:

- `github_upload_policy`
- `calendar_change_policy`
- broad `policy` distractors

Do not promote a broad `policy` rule without gate evidence.

## What To Hand Back To Selector Session

After generating new outcomes and running the gate, hand back:

```text
Outcome batch name:
Events appended:
Ask events:
Feedback events:
Candidate file:
Gate report:
Gate result:
Failed checks:
Negative answer-type violations:
Negative claim-scope violations:
New answer-type rule candidates:
Recommended selector action:
```

If the gate fails, include the exact failure rows from the relevant report. The most important failures are:

- `negative_answer_type_violations`
- `negative_claim_lift_violations`
- any failed focused answer-type regression
- any nested config regression failure

## Current Recommendation

Keep developing answer-type boundaries, but keep them narrow and test-gated.

The best next selector candidate area is probably:

`github_upload_policy` vs `calendar_change_policy`

But this should be driven by new outcome rows from the memory-program session before adding a new permanent config rule.
