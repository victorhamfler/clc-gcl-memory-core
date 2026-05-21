# Retrieval Signal Candidate Format

Date: 2026-05-21

## Purpose

Retrieval-signal candidates are small JSON artifacts that let Hermes or another test harness propose changes to `retrieval_signals` without directly editing `config.yaml`.

This is the first step toward self-improving retrieval signals:

1. observe a real failure;
2. propose a narrow candidate marker or threshold;
3. run a candidate eval;
4. run the promotion gates;
5. promote only if behavior is preserved or improved.

## Artifact Shape

Example:

```json
{
  "schema": "retrieval_signal_candidates/v1",
  "description": "Candidate retrieval-signal changes from a failure batch.",
  "candidates": [
    {
      "id": "transfer_scope_deflection",
      "section": "scope_deflection",
      "query_terms": ["transfer"],
      "text_markers": ["not transfer approval"],
      "notes": "Prevents near-topic correction notes from answering transfer-permission questions."
    }
  ]
}
```

Supported sections:

- `broad_generic`
- `scope_deflection`
- `correction_relevance`

Supported `broad_generic` fields:

- `source_contains`
- `text_prefixes`
- `penalty`

Supported `scope_deflection` fields:

- `query_terms`
- `correction_prefixes`
- `text_markers`
- `penalty`

Supported `correction_relevance` fields:

- `match_threshold`
- `min_relevance`

## Validation Command

From `clc_gcl_memory_core`:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_candidate_eval.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
```

The eval writes:

- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidate_eval_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidate_eval_report.md`

## Mining Command

Candidates can also be mined from outcome/failure logs that contain linked `ask` and `feedback` events.

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_retrieval_signal_candidates.py --log .\test_corpora\retrieval_signal_failure_outcomes.jsonl --out-json ..\experiments\retrieval_signal_candidates_mined_fixture.json --out-md ..\experiments\retrieval_signal_candidates_mined_fixture_report.md
```

Then validate the mined candidate file:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_candidate_eval.py --candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json
```

The miner currently looks for:

- negatively labeled broad/generic note rows;
- negatively labeled correction rows with explicit negative permission or approval language;
- query terms associated with those negative correction rows.

This is intentionally conservative. It proposes candidate markers, not direct config changes.

## Promotion Rule

A retrieval-signal candidate is not promoted just because this eval passes.

Promotion requires:

1. `retrieval_signal_promotion_gate.py` passes.
2. the candidate is tied to a real failure report or holdout improvement.

Run the formal gate with:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
```

For a mined candidate file:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json --out-json ..\experiments\retrieval_signal_promotion_gate_mined_fixture_results.json --out-md ..\experiments\retrieval_signal_promotion_gate_mined_fixture_report.md
```

The gate currently runs:

- syntax checks;
- retrieval-signal candidate eval;
- retrieval-signal module smoke;
- nested config regression;
- claim-scope promotion gate;
- randomized selector retrieval guard;
- policy correction deflection regression;
- answer quality eval.

## Development Direction

This format is intentionally simple. It is not yet learned by itself, but it creates the machinery needed for adaptive behavior:

- Hermes can mine candidate markers from failures.
- Candidate artifacts can be evaluated before touching production config.
- Accepted candidates can become config.
- Repeated accepted candidates can later train a learned marker proposer.
