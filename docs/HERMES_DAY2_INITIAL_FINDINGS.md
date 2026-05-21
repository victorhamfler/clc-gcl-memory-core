# Hermes Day 2 Initial Findings

Date: 2026-05-21

## What Was Done

The Day 2 live shadow harness was added as a repo-owned script:

- `eval/hermes_policy_shadow_run_day2.py`

The harness tests:

- Day 1 carry-forward policy boundaries
- paraphrase pressure
- multi-intent questions
- near-topic distractors
- correction pressure
- unrelated-topic leakage
- `/ask` evidence source, not just retrieval top-1

## New Fix Added

Day 2 exposed a real weakness: current corrected near-policy notes could override the actual policy memory.

Example:

- Query: `What GitHub upload policy should Hermes follow?`
- Wrong source: `Correction: GitHub issue notes can mention upload blockers, but they are not permission to upload to the repository.`
- Correct source: `GitHub uploads require explicit confirmation in the current conversation before any upload action.`

Fix:

- Added a retrieval-time `scope_deflection_penalty` for correction notes that explicitly say they are not the requested permission/policy or that a separate policy applies.
- Updated resolver evidence ordering so correction-chain priority yields when the correction is a scope-deflection note and a stronger policy memory is available.
- Updated answer snippet selection so deflection notes do not become the quoted answer sentence when non-deflecting evidence is present.
- Added `eval/policy_correction_deflection_regression.py`.
- Added the new regression to `eval/claim_scope_promotion_gate.py`.

Validation:

- `policy_correction_deflection_regression.py`: passed
- `day1_answer_source_regression.py`: passed
- `answer_type_policy_split_probe.py`: passed
- `hermes_policy_shadow_smoke.py`: passed
- full promotion gate with selector guards: passed

## Current Day 2 Live Result

A temporary local server was started from this checkout on port `8766` using the Gemma embedding backend. The latest local Day 2 run did not pass yet.

Artifact paths:

- `C:\Users\victo\Desktop\projcod2\experiments\hermes_policy_shadow_day2_local_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\hermes_policy_shadow_day2_local_report.md`

Current result:

- Policy passed: 42/63
- Policy failed: 21/63
- Unrelated passed: 14/18
- Unrelated failed: 4/18

Main remaining failure classes:

- approval archive notes beat broad policy log answers
- broad policy answers sometimes include calendar support snippets
- some compound repo publish/report questions still miss the upload permission rule
- generic filename queries can still surface GitHub filename memories as secondary evidence
- repo publish/report questions still need better handling when they ask for both filename and permission

## Interpretation

Day 2 is not ready for promotion. That is expected and useful.

Day 1 remains promoted. The new Day 2 harness has already produced one validated architecture improvement: scope-deflection correction handling. The remaining failures should be treated as the next development queue, not as Day 1 regressions.

## Best Next Development Step

The next architectural improvement after this checkpoint should target approval-log ambiguity.

Reason:

- The multi-source answer composition issue has now been converted into a focused regression and fixed locally.
- The largest remaining Day 2 cluster is approval archive notes beating broad policy log answers.
- The remaining failures show that `Approval archive entries are stored for audit history...` is too easily treated as the answer to `Where should general approvals be logged?`

Completed multi-intent improvement:

- Added `eval/multi_intent_answer_composition_regression.py`.
- Added source-aware snippet selection for compound questions.
- `What file should the GitHub report use, and can Hermes upload it automatically?` now answers with both `github_upload_report.md` and `explicit confirmation`.
- `Can Hermes change meetings, and where should approvals be documented?` now answers with both `manual approval` and `documented in the change log`.
- Added the new regression to the full promotion gate.

Validation after the multi-intent improvement:

- `multi_intent_answer_composition_regression.py`: passed
- `policy_correction_deflection_regression.py`: passed
- `day1_answer_source_regression.py`: passed
- `answer_type_policy_split_probe.py`: passed
- full promotion gate with selector guards: passed

Previous Day 2 live check after multi-intent composition:

- `missing_required_answer_text` improved from 15 to 9
- Day 2 still does not pass
- main remaining classes:
  - approval archive note beats broad policy log answer
  - generic filename queries can still surface GitHub filename as secondary evidence
  - repo publish/report questions still need better permission-rule retrieval

Completed approval-log ambiguity improvement:

- Added `eval/approval_log_ambiguity_regression.py`.
- Narrowed the broad-policy answer-type rule so approval/archive/audit/history memories do not satisfy broad logging/documentation questions.
- Preserved archive behavior for explicit archive/audit-history questions.
- Adjusted compound intent detection so `overall policy note` changes are not interpreted as calendar-change intent.
- Added the new regression to the full promotion gate.

Validation after approval-log improvement:

- `approval_log_ambiguity_regression.py`: passed
- `multi_intent_answer_composition_regression.py`: passed
- `policy_correction_deflection_regression.py`: passed
- `answer_type_policy_split_probe.py`: passed
- full promotion gate with selector guards: passed

Latest Day 2 live check after approval-log improvement:

- Policy passed: 46/63
- Policy failed: 17/63
- Unrelated passed: 14/18
- Unrelated failed: 4/18
- Approval-archive failures disappeared.
- Remaining main classes:
  - repo publish/report permission questions still miss `github_upload_policy`
  - generic filename queries still surface `github_upload_filename` as secondary evidence
  - some Day 2 strict retrieval-top expectations report `None` even when the answer evidence and answer text are now correct

Completed repo publish/report permission improvement:

- Added `eval/repo_publish_permission_ambiguity_regression.py`.
- Added `query_excludes_unless_any` support for answer-type rules.
- Updated `github_upload_policy` so filename/report terms still suppress filename-only questions, but compound permission/rule questions can activate the upload policy.
- Expanded resolver query terms so `repo publish permission` maps to GitHub upload confirmation.
- Added negative-permission evidence handling so `not upload permission` notes can remain context but cannot satisfy the upload-permission answer bucket.
- Added the new regression to the full promotion gate.

Validation after repo publish/report permission improvement:

- `repo_publish_permission_ambiguity_regression.py`: passed
- `multi_intent_answer_composition_regression.py`: passed
- `approval_log_ambiguity_regression.py`: passed
- `answer_type_policy_split_probe.py`: passed
- full promotion gate with selector guards: passed

Latest Day 2 live check after repo publish/report permission improvement:

- Policy passed: 49/63
- Policy failed: 14/63
- Unrelated passed: 14/18
- Unrelated failed: 4/18
- Repo publish/report permission failures disappeared.
- Remaining main classes:
  - generic filename queries still surface `github_upload_filename` as secondary evidence
  - some strict retrieval-top labels report `None` even when answer evidence and answer text are correct
  - `upload_artifact_paraphrase` answers correctly but its top evidence bookkeeping still reports `broad_policy_note`

Recommended next test:

1. Add a focused local regression for generic filename leakage.
2. Include `github_upload_filename`, `weather_filename_note`, and `report_template_note`.
3. Query `What filename is used for weather radar text notes?`
4. Require the weather filename memory to answer with `radar_snapshot.txt`.
5. Ensure `github_upload_filename` can remain below the target but does not enter answer evidence for non-GitHub filename questions.
