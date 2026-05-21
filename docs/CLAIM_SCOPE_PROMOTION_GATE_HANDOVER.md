# Claim Scope Promotion Gate Handover

This handover is for the memory-program session that owns the broader agent memory system and outcome logging. The selector-module session now has a reusable promotion gate for claim-scope aliases. Use this gate before recommending that new mined aliases become permanent selector configuration.

## Current Boundary Between Sessions

- The other memory-program session owns the broad memory program, live outcome generation, outcome labels, and real usage reports.
- This selector-module session owns claim-scope selector architecture, alias promotion rules, selector guard tests, and permanent selector configuration.
- The other session should not directly promote broad mined terms into selector configuration. It should mine candidates, run or request the promotion gate, and hand the report back here.

## New Gate Script

Run from:

`C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core`

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py --include-selector-guards --candidates ..\experiments\claim_scope_alias_candidates_v2.json
```

If the other session creates a new candidate file, replace the candidates path:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py --include-selector-guards --candidates ..\experiments\NEW_CANDIDATE_FILE.json
```

## What The Gate Runs

The gate runs:

- Python compile checks for selector and eval scripts.
- `claim_scope_candidate_ab_eval.py`
- `claim_scope_outcome_replay_eval.py`
- `claim_scope_config_regression.py`
- `selector_near_topic_distractor_eval.py`
- `agent_workflow_selector_integration_eval.py`
- `selector_retrieval_guard_randomized_eval.py`

The gate writes:

- `C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report.md`
- candidate AB subreports
- outcome replay subreports

## Promotion Rule

Only recommend selector promotion when:

```text
Promotion ready: True
candidate_ab_ok: True
outcome_replay_ok: True
config_regression_ok: True
selector_guards_ok: True
```

If any field is false, do not promote the aliases. Instead, report:

- which check failed
- which candidate slots were involved
- whether the failure was a broad alias, wrong-domain lift, stale lift, or near-topic leak
- the exact rows from the generated report that explain the failure

## Current Known Good State

The latest gate run passed with:

```text
Promotion ready: True
candidate_ab_ok: True
outcome_replay_ok: True
config_regression_ok: True
selector_guards_ok: True
```

Current promoted selector slots include:

- `backend_port`
- `github_upload`
- `calendar_change`
- `gcl_curvature`
- `csd`
- `deadline`

The `backend_port` slot was tightened after outcome replay found it could lift backend host/local-testing memories for port questions. It now excludes:

```text
host, remain, 127, local, testing
```

Do not remove those exclusions unless a new gate run proves the replacement is safer.

## What The Other Session Should Do Next

1. Continue generating realistic outcome logs from actual agent-memory use.
2. Mine claim-scope alias candidates from accepted/rejected outcome rows.
3. Save new candidates under:

```text
C:\Users\victo\Desktop\projcod2\experiments\
```

4. Run the promotion gate with the new candidate file.
5. Send this selector-module session:

- the candidate JSON file path
- `claim_scope_promotion_gate_report.md`
- `claim_scope_promotion_gate_results.json`
- any failure subreports if the gate fails
- a short recommendation: promote, reject, split into narrower slots, or gather more outcomes

## Candidate Design Guidance

Prefer narrow slots that represent a specific claim type, not broad topic words.

Good examples:

- `github_upload`
- `calendar_change`
- `backend_port`
- `gcl_curvature`
- `deadline`

Risky examples:

- `policy`
- `project`
- `memory`
- `status` when used too broadly
- owner/person terms unless the test corpus proves clean separation from deadlines, assignments, and preferences

When a mined alias appears useful but broad, split it into narrower slots and add exclusions. Example:

- Use `github_upload` and `calendar_change` instead of one broad `policy` slot.
- Use `backend_port` with exclusions for host/local-testing instead of a broad `backend` slot.

## What To Hand Back Here

Use this format:

```text
Candidate file:
Gate report:
Gate result:
Promotion ready:
Slots proposed:
Slots rejected:
Reason for each proposed slot:
Failures or risks:
Recommended next selector change:
```

This lets the selector-module session make the final architecture/configuration decision without duplicating the other session's broader memory-program work.
