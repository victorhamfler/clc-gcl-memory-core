# Selector Restructure Handover To Memory Session

Date: 2026-05-21

## Purpose

This handover explains the selector-side restructuring work done in the current session and what the memory-program session should do next.

The current agreement still holds:

- This session owns selector architecture, retrieval signals, evidence-state candidate loops, selector gates, and selector-side restructuring docs.
- The memory-program session owns broader memory-program integration, storage behavior, learning endpoints, Hermes workflow integration, and general memory runtime behavior.
- Both sessions should coordinate before GitHub uploads that affect shared contracts.

## What Changed On The Selector Side

The selector/retrieval architecture now has two extracted configurable control surfaces.

### 1. Retrieval Signals

New module:

```text
core/retrieval_signals.py
```

This extracted selector-facing retrieval signal logic from `core/pipeline.py`, including:

- claim-scope scoring;
- answer-type scoring;
- correction relevance;
- broad generic note detection;
- scope deflection detection;
- token helpers used by these signals.

Config section:

```text
retrieval_signals
```

Candidate loop files:

```text
docs/RETRIEVAL_SIGNAL_CANDIDATE_FORMAT.md
eval/retrieval_signal_candidate_eval.py
eval/mine_retrieval_signal_candidates.py
eval/retrieval_signal_promotion_gate.py
test_corpora/retrieval_signal_candidates_v1.json
test_corpora/retrieval_signal_failure_outcomes.jsonl
```

### 2. Evidence States

New module:

```text
core/evidence_states.py
```

This extracted resolver evidence-state classification from `core/resolver.py`, including:

- `current`;
- `stale`;
- `historical`;
- `disputed`;
- `summary`;
- weak evidence filtering;
- sensitive lookup detection.

Config section:

```text
evidence_states
```

Candidate loop files:

```text
docs/EVIDENCE_STATE_CANDIDATE_FORMAT.md
eval/evidence_state_candidate_eval.py
eval/mine_evidence_state_candidates.py
eval/evidence_state_promotion_gate.py
test_corpora/evidence_state_candidates_v1.json
test_corpora/evidence_state_failure_outcomes.jsonl
```

## Current Unified Gate

The main selector-side safety gate is now:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

It runs:

- retrieval-signal promotion gate;
- evidence-state promotion gate.

It wrote passing reports here:

```text
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_results.json
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_report.md
```

The mined fixture version also passed:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json --evidence-candidates ..\experiments\evidence_state_candidates_mined_fixture.json --out-json ..\experiments\selector_architecture_gate_mined_fixture_results.json --out-md ..\experiments\selector_architecture_gate_mined_fixture_report.md
```

Passing reports:

```text
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_mined_fixture_results.json
C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_mined_fixture_report.md
```

## Rule For Promotion

Do not directly edit production config from a mined candidate.

The intended workflow is:

1. Memory program or Hermes logs a failure with linked `ask` and `feedback` events.
2. Candidate miner proposes a JSON artifact.
3. Candidate eval validates the proposed artifact.
4. Promotion gate validates no known behavior was damaged.
5. Only then should the candidate be considered for promotion into config.

The selector side currently treats candidate artifacts as proposals, not accepted truth.

## Outcome Log Contract Needed From Memory Session

The selector-side miners need linked `ask` and `feedback` events.

The minimum useful `ask` event shape is:

```json
{
  "event_type": "ask",
  "operation_id": "ask_unique_id",
  "payload": {
    "request": {
      "query": "User question"
    },
    "response": {
      "raw_results": [
        {
          "memory_id": "mem_id",
          "score": 0.42,
          "text_match_score": 0.4,
          "intent_match_score": 0.0,
          "supersession_score": 0.0,
          "relation_supersession_score": 0.0,
          "summary_relation_score": 0.0,
          "feedback_score": 0.0,
          "authority_state": "",
          "source": "source.md",
          "text": "Retrieved memory text"
        }
      ]
    }
  }
}
```

The minimum useful `feedback` event shape is:

```json
{
  "event_type": "feedback",
  "operation_id": "feedback_unique_id",
  "linked_operation_id": "ask_unique_id",
  "payload": {
    "request": {
      "memory_id": "mem_id",
      "query": "User question",
      "label": "stale",
      "rating": -1.0
    }
  }
}
```

Important fields:

- `linked_operation_id` must point to the related `ask.operation_id`.
- `memory_id` must identify the retrieved row being judged.
- `response.raw_results` should contain the retrieval rows shown to the resolver/answer layer.
- `label` should describe the failure class.
- `rating` should be negative for bad retrieval/evidence outcomes and positive for corrected/current outcomes.

## Labels Useful For Current Miners

Retrieval-signal miner currently recognizes negative labels such as:

```text
wrong_domain
stale
irrelevant
bad_source
incorrect
not_useful
```

Evidence-state miner currently recognizes:

```text
stale
old
obsolete
superseded
incorrect_stale
current
should_be_current
fresh
corrected_current
sensitive
sensitive_lookup
needs_exact_evidence
private_lookup
```

The memory session can add richer labels later, but these are enough for the current candidate miners.

## Commands For Memory Session

From:

```text
C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core
```

Run the unified gate:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

Mine retrieval-signal candidates from an outcome log:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_retrieval_signal_candidates.py --log PATH_TO_OUTCOME_LOG.jsonl --out-json ..\experiments\retrieval_signal_candidates_from_memory_session.json --out-md ..\experiments\retrieval_signal_candidates_from_memory_session_report.md
```

Mine evidence-state candidates from an outcome log:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log PATH_TO_OUTCOME_LOG.jsonl --out-json ..\experiments\evidence_state_candidates_from_memory_session.json --out-md ..\experiments\evidence_state_candidates_from_memory_session_report.md
```

Run the unified gate with mined candidates:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_from_memory_session.json --evidence-candidates ..\experiments\evidence_state_candidates_from_memory_session.json --out-json ..\experiments\selector_architecture_gate_memory_session_candidates_results.json --out-md ..\experiments\selector_architecture_gate_memory_session_candidates_report.md
```

If only one candidate family exists, omit the other argument and the gate will use the default fixture for that family.

If an automation may or may not have produced one of the candidate files, use:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_from_memory_session.json --evidence-candidates ..\experiments\evidence_state_candidates_from_memory_session.json --allow-missing-candidates --out-json ..\experiments\selector_architecture_gate_memory_session_candidates_results.json --out-md ..\experiments\selector_architecture_gate_memory_session_candidates_report.md
```

With `--allow-missing-candidates`, a missing candidate file falls back to the default fixture for that family and records the fallback in the gate report.

### One-Command Pipeline From A Log

The selector session also added a wrapper that mines both candidate families from one outcome log and then runs the unified gate:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log PATH_TO_OUTCOME_LOG.jsonl
```

For a real Hermes log, use explicit output paths:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log PATH_TO_HERMES_OUTCOME_LOG.jsonl --out-json ..\experiments\selector_candidate_pipeline_hermes_results.json --out-md ..\experiments\selector_candidate_pipeline_hermes_report.md
```

This writes:

- retrieval-signal candidate JSON and report;
- evidence-state candidate JSON and report;
- selector architecture gate JSON and report;
- one top-level pipeline JSON and report.

The memory-session contract log passed this command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log ..\experiments\memory_outcome_contract_workflow.jsonl
```

Result:

```text
PASS, retrieval candidate sections=1, evidence candidate sections=2
```

## What The Memory Session Should Do Next

The memory session should not change selector internals yet.

Recommended next work:

1. Review the outcome logging path and confirm linked `ask`/`feedback` events contain the fields listed above.
2. Add or adjust memory-side logging if fields are missing.
3. Run a small realistic Hermes memory workflow that creates:
   - stale evidence feedback;
   - current/correction feedback;
   - sensitive lookup feedback;
   - irrelevant or wrong-domain retrieval feedback.
4. Run the candidate miners against that real log.
5. Run `selector_architecture_gate.py` with the mined candidate artifacts.
6. Write a report back to this selector session with:
   - log path used;
   - candidate files produced;
   - gate result paths;
   - any missing fields or labels;
   - any candidates that seem too broad or unsafe.

## What To Avoid For Now

Avoid these until both sessions coordinate:

- editing `core/retrieval_signals.py` from the memory-program session;
- editing `core/evidence_states.py` from the memory-program session;
- changing `retrieval_signals` or `evidence_states` defaults in `config.yaml` without a passing candidate gate;
- promoting mined candidates from a single anecdotal failure without a holdout or regression gate;
- changing outcome-log structure without keeping backward-compatible fields for the miners.

## Current Judgment

The selector-side restructure is in a good checkpoint state.

It is not finished as a full architecture rewrite, but it now has the right shape:

```text
hardcoded behavior -> configurable module -> candidate artifact -> miner -> promotion gate -> possible promotion
```

The memory session's most valuable contribution now is not to rewrite selector code. It is to make sure the broader memory program produces high-quality outcome logs so the selector-side adaptive loops can learn from real failures safely.
