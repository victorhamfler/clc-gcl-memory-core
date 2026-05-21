# Memory Session Restructure Outcome Log Handover

Date: 2026-05-21

## Purpose

This handover reports the memory-session work done in response to `SELECTOR_RESTRUCTURE_HANDOVER_TO_MEMORY_SESSION.md`.

The selector session asked the memory program to verify and improve linked `ask`/`feedback` outcome logs, then prove that the selector-side candidate miners and gates can consume a realistic memory-generated log.

## Memory-Side Changes

Updated:

```text
serve.py
eval/outcome_logging_regression.py
eval/memory_outcome_contract_workflow.py
```

### Outcome Log Enrichment

`MemoryApi._evidence_brief()` now preserves the selector/miner training fields needed from `ask.response.raw_results`, including:

- `memory_id`
- `score`
- `text_match_score`
- `intent_match_score`
- `supersession_score`
- `relation_supersession_score`
- `summary_relation_score`
- `feedback_score`
- `authority_state`
- `source`
- `text`

It also keeps useful diagnostic fields:

- `answer_type_score`
- `identifier_match_score`
- `broad_generic_penalty`
- `scope_deflection_penalty`
- `stored_contradiction_score`
- `usage_count`

### Regression Coverage

`eval/outcome_logging_regression.py` now asserts that logged `ask.raw_results` include the minimum selector-miner training fields.

Added `eval/memory_outcome_contract_workflow.py`, which creates a temporary memory API, teaches a small Hermes fixture corpus, runs linked `ask`/`feedback` events, and writes a reusable log copy.

It creates feedback examples for:

- stale evidence feedback
- current/correction feedback
- sensitive lookup feedback
- wrong-domain retrieval feedback
- generic broad-note feedback

## Validation Commands Run

From:

```text
C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core
```

Compile check:

```powershell
..\.venv-torch\Scripts\python.exe -m py_compile .\serve.py .\eval\outcome_logging_regression.py .\eval\memory_outcome_contract_workflow.py
```

Outcome log regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
```

Result: passed.

Memory outcome contract workflow:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\memory_outcome_contract_workflow.py
```

Result: passed.

Artifacts:

```text
C:\Users\victo\Desktop\projcod2\experiments\memory_outcome_contract_workflow.jsonl
C:\Users\victo\Desktop\projcod2\experiments\memory_outcome_contract_workflow_results.json
C:\Users\victo\Desktop\projcod2\experiments\memory_outcome_contract_workflow_report.md
```

The workflow produced:

- `5` ask events
- `5` feedback events
- `5` linked feedback events
- `0` missing training fields

## Candidate Mining Run

Retrieval-signal candidates:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_retrieval_signal_candidates.py --log ..\experiments\memory_outcome_contract_workflow.jsonl --out-json ..\experiments\retrieval_signal_candidates_from_memory_session.json --out-md ..\experiments\retrieval_signal_candidates_from_memory_session_report.md
```

Result: passed, `1` candidate.

Evidence-state candidates:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log ..\experiments\memory_outcome_contract_workflow.jsonl --out-json ..\experiments\evidence_state_candidates_from_memory_session.json --out-md ..\experiments\evidence_state_candidates_from_memory_session_report.md
```

Result: passed, `2` candidates.

Artifacts:

```text
C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidates_from_memory_session.json
C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidates_from_memory_session_report.md
C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidates_from_memory_session.json
C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidates_from_memory_session_report.md
```

## Gate Runs

Baseline selector architecture gate:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

Result: passed.

Gate with memory-session mined candidates:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_from_memory_session.json --evidence-candidates ..\experiments\evidence_state_candidates_from_memory_session.json --out-json ..\experiments\selector_architecture_gate_memory_session_candidates_results.json --out-md ..\experiments\selector_architecture_gate_memory_session_candidates_report.md
```

Result: passed.

Artifacts:

```text
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_memory_session_candidates_results.json
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_memory_session_candidates_report.md
```

## Mined Candidate Notes

Retrieval-signal miner proposed one broad-generic candidate:

```text
source_contains: ops_control_note, universal_policy_note
text_prefixes: ops control note, universal policy note
```

Evidence-state miner proposed:

```text
stale_language: retired truth
correction_language: verified current:
```

Judgment:

- These candidates prove the logging and mining loop works.
- They should not be promoted as production config from this synthetic single-run workflow alone.
- The `verified current:` candidate is plausible but broad; it needs real-agent holdout examples before promotion.
- The broad-note candidates are intentionally synthetic markers and should remain candidate artifacts unless repeated in real Hermes failures.

## Missing Or Weak Areas

No required outcome-log fields were missing.

The synthetic sensitive lookup feedback did not mine a new sensitive term because the current evidence-state config already appears to cover the relevant private/key terms. That is acceptable for this contract test.

## Recommended Next Step For Selector Session

Use the memory-generated log and candidate files as a fixture for selector-side miner development, but do not promote the candidates yet.

The next useful selector-side improvement would be to add optional candidate arguments so the unified gate can run with only one mined candidate family while using defaults for the other family.

## Recommended Next Step For Memory Session

Run this same outcome-log workflow against a real Hermes agent session after the restructure lands cleanly, then mine candidates from that real log. Real feedback should be used for candidate promotion decisions; this synthetic workflow should remain a contract and plumbing test.
