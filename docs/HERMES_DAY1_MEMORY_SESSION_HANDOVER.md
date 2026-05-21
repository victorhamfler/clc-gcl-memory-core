# Hermes Day 1 Memory Session Handover

Date: 2026-05-21

This handover is for the memory-program session. The selector session analyzed the Hermes Day 1 shadow-run reports and fixed the selector-side filename/policy split issue. The remaining Day 1 failure appears to belong to the memory program's answer and evidence construction path, not to selector ranking.

## Files To Review

- Hermes Day 1 report:
  - `C:\Users\victo\Documents\GitHub\experiments\hermes_policy_shadow_day1_report.md`
- Hermes Day 1 JSON:
  - `C:\Users\victo\Documents\GitHub\experiments\hermes_policy_shadow_day1_results.json`
- Hermes Day 1 harness copy:
  - `C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\eval\hermes_policy_shadow_run_day1.py`

## Selector-Side Update Already Done Here

The selector session found a real selector defect in GitHub filename questions:

- Query examples:
  - `What GitHub upload report filename should be used?`
  - `What file should the GitHub upload report use?`
- Before the fix, `github_upload_policy` ranked ahead of `github_upload_filename`.
- Cause: the `github_upload_policy` answer-type rule still activated on filename/report questions because those queries also contain `github` and `upload`.
- Fix implemented in the selector module:
  - Added configurable `query_excludes_any` support for answer-type rules.
  - Configured `github_upload_policy` with `query_excludes_any: filename,file,report`.
  - Added two regression cases to `eval/answer_type_policy_split_probe.py`.

Verification in selector session:

- `answer_type_policy_split_probe.py`: passed, 6/6 cases
- `answer_type_method_filename_regression.py`: passed
- `hermes_policy_shadow_smoke.py`: passed
- `config_nested_parser_regression.py`: passed
- Full promotion gate with selector guards: passed

Important: these changes are currently local in the selector session unless the user has asked to upload them after this handover.

## Remaining Failure For Memory Session

The unresolved Day 1 issue is the calendar `/ask` answer source:

- Query:
  - `What calendar change policy should Hermes follow?`
  - `Can Hermes change meetings automatically?`
- Retrieval ranked `calendar_change_policy` first.
- The answer still quoted or selected `broad_policy_note`.
- Example wrong answer:
  - `Broad policy note: all approvals should be documented in the change log.`

This means the selector gave the memory program enough signal, but the answer/evidence construction layer did not preserve the intended top source.

## What The Memory Session Should Improve

Implement a guarded answer/evidence selection rule for `/ask` so the final answer uses the best eligible retrieval row, not merely a plausible lower-ranked policy row.

Recommended behavior:

1. When a retrieval row has rank 1 and a positive selector signal for the query, prefer it as the primary evidence.
2. For policy questions, prefer rows with the matching policy answer-type over broad policy notes.
3. If a lower-ranked row is broad/generic and the top-ranked row is specific, do not let the broad row become the leading answer source.
4. Preserve useful supporting evidence, but make the primary answer come from the top specific row.
5. Add a regression that checks both retrieval and `/ask` final answer source.

Suggested eligibility fields to use if available:

- retrieval rank
- `answer_type_score`
- `claim_scope_score`
- source/ref label
- source specificity, such as `calendar_change_policy` versus `broad_policy_note`
- current-session/current-memory flag, if the memory program tracks it

## Regression Test To Add In Memory Program

Create a focused test with at least these memories:

- `calendar_change_policy`:
  - `Calendar schedule changes require manual approval before changing meeting events.`
- `broad_policy_note`:
  - `Broad policy note: all approvals should be documented in the change log.`
- Optional distractor:
  - `GitHub uploads require explicit confirmation in the current conversation.`

Queries:

- `What calendar change policy should Hermes follow?`
- `Can Hermes change meetings automatically?`

Expected results:

- Retrieval top row is `calendar_change_policy`.
- Final `/ask` answer uses `calendar_change_policy` as the primary evidence.
- Final answer should mention manual approval before changing calendar/meeting events.
- Final answer should not lead with the broad policy note.

Suggested failure checks:

- Fail if the final answer starts from or primarily cites `broad_policy_note`.
- Fail if evidence rank 1 is ignored when it has positive answer-type support.
- Fail if broad policy text is selected while a specific calendar policy row is ranked higher.

## Boundary Between Sessions

Selector session owns:

- answer-type scoring
- claim-scope scoring
- selector gates and promotion tests
- config-driven rule improvements

Memory-program session owns:

- `/ask` answer synthesis
- evidence ordering and citation choice
- current-memory handling
- final response source selection

For this issue, the next implementation should happen in the memory-program session. The selector session can later add a smoke test or harness update once the memory program exposes the improved answer/evidence behavior.

