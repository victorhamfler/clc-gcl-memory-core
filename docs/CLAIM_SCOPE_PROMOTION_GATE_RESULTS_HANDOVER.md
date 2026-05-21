# Claim Scope Promotion Gate Results Handover

Date: 2026-05-20

This handover is from the memory-program session to the selector-module session. It summarizes the current mined claim-scope alias candidates, the selector promotion gate result, and the recommended selector-side action.

The memory-program session added one labeled hard-case outcome batch before this gate run:

- batch: `claim-scope-hard-cases-v3`
- appended events: `40`
- ask events: `10`
- feedback events: `30`
- target confusions: owner/deadline, owner/codename, owner/policy, filename/deadline, filename/method, and preference corrections

The memory-program session then added a second owner-focused relation batch:

- batch: `claim-scope-owner-relation-v4`
- appended events: `24`
- ask events: `6`
- feedback events: `18`
- target aliases: `assignment`, `assignee`, `responsible`, `assigned`, `accountable`, `responsibility`
- target confusions: owner/deadline, owner/filename, owner/calendar policy, owner/backend host/port

## Gate Inputs

Candidate file:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_alias_candidates_v8.json`

Candidate report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_alias_candidates_v8_report.md`

Gate report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report.md`

Gate result:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_results.json`

Outcome replay report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report_outcome_replay.md`

Candidate A/B report:

`C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report_candidate_ab.md`

## Gate Result

Promotion ready: `True`

Required checks:

| check | pass |
| --- | --- |
| `candidate_ab_ok` | `True` |
| `outcome_replay_ok` | `True` |
| `config_regression_ok` | `True` |
| `selector_guards_ok` | `True` |

The gate included selector guards and passed the candidate A/B eval, outcome replay eval, config regression, near-topic distractor eval, agent workflow selector integration eval, and randomized retrieval guard.

Current replay coverage:

- events: `219`
- ask events: `70`
- feedback rows: `131`
- evaluated positives: `57`
- evaluated negatives: `74`

Miner cleanup applied before the V8 candidate file:

- source paths are no longer used as alias text
- `report` alone no longer makes a query a filename query
- `filename` and `file` queries take precedence over incidental `status` or `deadline` words inside the report title
- `codename` queries no longer become owner queries because of the word `belongs`
- owner aliases are restricted to relation-style terms such as `assignment`, `assignee`, or `responsible`, not person/project names like `Mina`, `Iris`, or `Redwood Lantern`
- the report now separates positive supporting queries from negative queries
- memory-id feedback rows now mine alias terms from the selected row text only; the answer text is used only as fallback. This prevents correct answer wording from being counted as excluded terms for wrong-domain feedback rows.

## Slots Proposed

These slots are safe enough to keep or promote on the selector side:

- `backend_port`
- `github_upload`
- `calendar_change`
- `gcl_curvature`
- `csd`
- `deadline`

Reasons:

- `backend_port` is useful for compact numeric port memories and is safer after excluding `host`, `remain`, `127`, `local`, and `testing`.
- `github_upload` and `calendar_change` are safer as split policy slots than a broad `policy` slot.
- `gcl_curvature` and `csd` are safer as split mechanism slots than a broad `mechanism` slot.
- `deadline` passed the gate and is useful for agent task memory, but it still needs more real outcome rows to strengthen confidence.

## Slots Rejected Or Deferred

Do not promote these as broad selector configuration yet:

- `policy`
- `mechanism`
- `general_claim`
- broad/entity-based `owner`
- broad `filename`
- broad `status`
- broad `codename`

Reasons:

- Broad `policy` risks mixing unrelated policies such as GitHub upload policy and calendar change policy.
- Broad `mechanism` risks mixing G-CL curvature memories with CSD signal memories.
- `general_claim` is too noisy and should remain an analysis category, not a selector slot.
- Entity-name owner aliases are not ready. Do not promote person/project names as aliases for owner memory.
- Broad `filename` should be split into narrower file-purpose slots when needed, such as `report_filename` or a task-specific filename slot.
- Broad `status` and `codename` are still domain-sensitive slots and should not be promoted broadly from this mined file without additional guard checks.

## Risks And Interpretation

The promotion gate is green, but the outcome replay produced zero rank movement and zero claim-lift movement. That means the current promoted slots did not harm replayed results, but many examples were already separable before the new aliases. Treat this as a safety pass, not proof that every promoted alias adds strong retrieval lift.

The highest-priority weak area is still owner memory, but the memory-side candidate is now much cleaner. After V8 cleanup, owner support is `10` positive and `22` negative rows. The mined owner aliases are now relation-style terms only:

`assignment`, `assignee`, `responsible`, `assigned`, `accountable`, `responsibility`

The selector gate is still overall green, but `owner_alias_rescue` remains row-level `False` in the candidate A/B table. The selector-module session should inspect why these owner aliases increase target claim scope but do not move the owner target above the nearest distractor.

## Recommended Selector Change

The selector-module session can keep or promote the narrow slots that passed:

`backend_port`, `github_upload`, `calendar_change`, `gcl_curvature`, `csd`, `deadline`

The selector-module session should keep `backend_port` exclusions:

`host`, `remain`, `127`, `local`, `testing`

The selector-module session should defer entity-name owner aliases and broad `policy`, `mechanism`, `general_claim`, `filename`, `status`, and `codename` slots from this mined file.

The selector-module session can now consider a narrow owner-relation experiment using only:

`assignment`, `assignee`, `responsible`, `assigned`, `accountable`, `responsibility`

That experiment should not promote names such as `Mina`, `Iris`, `Operations agent`, `Redwood Lantern`, or project/report titles as aliases.

## Selector Session Action Checklist

1. Use `C:\Users\victo\Desktop\projcod2\experiments\claim_scope_alias_candidates_v8.json` as the current candidate input.
2. Keep the current promoted narrow slots that already pass: `backend_port`, `github_upload`, `calendar_change`, `gcl_curvature`, `csd`, and `deadline`.
3. Keep the `backend_port` exclusions: `host`, `remain`, `127`, `local`, `testing`.
4. Investigate why `owner_alias_rescue` still has margin `-1` even though the split owner candidate raises target claim-scope.
5. If testing owner promotion, test only the narrow owner-relation aliases: `assignment`, `assignee`, `responsible`, `assigned`, `accountable`, `responsibility`.
6. Do not promote entity names or broad owner/codename/status/policy/mechanism aliases from this mined file.

## Recommended Memory-Program Follow-Up

The memory-program session can continue generating or collecting realistic linked outcome logs for:

- owner versus deadline
- owner versus project codename
- owner versus preferences
- deadline versus report filename
- report filename versus method/tool choice
- preference corrections over time

The next mined candidate file should be generated only after those real or realistic outcome rows are added, then passed through the same promotion gate before any selector-side promotion recommendation.

Memory-program tooling added for this:

`C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core\eval\generate_claim_scope_outcome_samples.py`

Example command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\generate_claim_scope_outcome_samples.py --batch claim-scope-hard-cases-v3
```

Owner relation sample command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\generate_claim_scope_outcome_samples.py --batch claim-scope-owner-relation-v4
```

The generator is idempotent by default: it skips a batch if that `sample_batch` already exists in the target outcome log.
