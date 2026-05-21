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
- multi-intent questions retrieve multiple sources but answer only one part
- generic filename queries can still surface GitHub filename memories as secondary evidence
- repo publish/report questions still need better handling when they ask for both filename and permission

## Interpretation

Day 2 is not ready for promotion. That is expected and useful.

Day 1 remains promoted. The new Day 2 harness has already produced one validated architecture improvement: scope-deflection correction handling. The remaining failures should be treated as the next development queue, not as Day 1 regressions.

## Best Next Development Step

The next architectural improvement should target multi-source answer composition.

Reason:

- Several Day 2 failures already retrieve the needed memories in the evidence set.
- The answer text only uses the first source, so it misses the second required fact.
- This affects multi-intent queries such as filename plus upload permission, and calendar policy plus approval logging.

Recommended next test:

1. Add a focused local regression for multi-intent `/ask` composition.
2. Use two evidence memories with clearly different required facts.
3. Require the answer to include both facts.
4. Fix `select_answer_snippets` or answer assembly so multi-intent queries preserve one high-quality snippet per expected evidence source.
5. Rerun Day 2.

