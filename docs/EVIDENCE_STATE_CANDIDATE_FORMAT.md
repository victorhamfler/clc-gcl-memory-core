# Evidence State Candidate Format

Date: 2026-05-21

## Purpose

Evidence-state candidates are small JSON artifacts that let Hermes or another test harness propose changes to `evidence_states` without directly editing `config.yaml`.

This is the companion loop to retrieval-signal candidates:

1. observe a stale/current/sensitive-evidence failure;
2. propose a narrow language marker or threshold;
3. run a candidate eval;
4. run the promotion gate;
5. promote only if behavior is preserved or improved.

## Artifact Shape

Example:

```json
{
  "schema": "evidence_state_candidates/v1",
  "description": "Candidate evidence-state changes from a failure batch.",
  "candidates": [
    {
      "id": "retired_truth_stale_language",
      "section": "stale_language",
      "terms": ["retired truth"],
      "notes": "Marks memories that explicitly describe themselves as retired truth as stale."
    }
  ]
}
```

Supported sections:

- `stale_language`
- `correction_language`
- `sensitive_lookup`
- `thresholds`
- `weak_evidence`

Supported `stale_language` fields:

- `terms`
- `stale_regex`

Supported `correction_language` fields:

- `terms`

Supported `sensitive_lookup` fields:

- `terms`

Supported `thresholds` fields:

- `current_threshold`
- `stale_threshold`
- `stale_feedback_threshold`
- `disputed_feedback_threshold`

Supported `weak_evidence` fields:

- `score_threshold`
- `text_match_threshold`
- `intent_match_threshold`
- `intent_text_match_threshold`

## Validation Command

From `clc_gcl_memory_core`:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_candidate_eval.py --candidates .\test_corpora\evidence_state_candidates_v1.json
```

The eval writes:

- `C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidate_eval_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidate_eval_report.md`

## Mining Command

Candidates can be mined from linked `ask` and `feedback` events:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log .\test_corpora\evidence_state_failure_outcomes.jsonl --out-json ..\experiments\evidence_state_candidates_mined_fixture.json --out-md ..\experiments\evidence_state_candidates_mined_fixture_report.md
```

Then validate the mined candidate file:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_candidate_eval.py --candidates ..\experiments\evidence_state_candidates_mined_fixture.json
```

The miner currently looks for:

- rows labeled stale but classified as non-stale;
- rows labeled current/corrected but classified as non-current;
- sensitive lookup feedback labels.

This is intentionally conservative. It proposes candidate markers, not direct config changes.

## Promotion Rule

An evidence-state candidate is not promoted just because this eval passes.

Promotion requires:

1. `evidence_state_promotion_gate.py` passes.
2. the candidate is tied to a real failure report or holdout improvement.

Run the formal gate with:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_promotion_gate.py --candidates .\test_corpora\evidence_state_candidates_v1.json
```

For a mined candidate file:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_promotion_gate.py --candidates ..\experiments\evidence_state_candidates_mined_fixture.json --out-json ..\experiments\evidence_state_promotion_gate_mined_fixture_results.json --out-md ..\experiments\evidence_state_promotion_gate_mined_fixture_report.md
```

## Development Direction

This completes the second adaptive control surface:

- retrieval-signal candidates improve what gets retrieved and downranked;
- evidence-state candidates improve how retrieved evidence is classified as current, stale, disputed, sensitive, or too weak.

Together, they are the beginning of the configurable CLC/CSD selector brain: observe failures, propose narrow changes, verify them against gates, and only then promote.
