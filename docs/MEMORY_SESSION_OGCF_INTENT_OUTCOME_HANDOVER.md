# Memory Session OGCF Intent Outcome Handover

Date: 2026-05-24

## Purpose

This handover responds to:

```text
docs/MEMORY_PROGRAM_ROADMAP_HANDOVER.md
docs/OGCF_INTENT_CANDIDATES_HANDOVER_TO_MEMORY_SESSION.md
```

The selector session asked the memory session to verify support for OGCF-specific feedback labels, create a controlled Hermes-style workflow with linked `ask` and `feedback` events, run the OGCF intent miner, and hand back candidate artifacts without promoting them into selector config.

## Memory-Side Changes

Updated:

```text
serve.py
eval/ogcf_intent_outcome_workflow.py
```

### Feedback Label Defaults

`serve.py` now has default ratings for OGCF-specific feedback labels, so agents can send a label without also remembering the numeric rating.

Positive labels default to `1.0`:

```text
bridge_relevant
cross_domain_bridge
ogcf_bridge
ogcf_geometry
bridge_geometry
loop_overload
memory_maintenance
dedup
duplicate
bridge_maintenance
```

Suppression labels default to negative ratings:

```text
ogcf_false_positive -> -1.0
bridge_irrelevant -> -0.75
ordinary_lookup -> -0.75
ordinary_fact -> -0.75
unrelated_bridge -> -0.75
no_ogcf_pressure -> -0.75
```

This preserves the existing linked `ask`/`feedback` contract and does not change selector config.

## Controlled Workflow

Added:

```text
eval/ogcf_intent_outcome_workflow.py
```

The workflow creates a temporary memory API, teaches a small Hermes-style fixture corpus, runs linked `ask`/`feedback` events, and then runs:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_ogcf_intent_candidates.py --log ..\experiments\ogcf_intent_outcome_workflow.jsonl --min-support 2 --out-json ..\experiments\ogcf_intent_candidates_from_memory_session.json --out-md ..\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

The workflow covers:

- ordinary fact lookup suppression
- positive bridge relevance
- positive cross-domain bridge relevance
- positive OGCF geometry relevance
- positive bridge geometry relevance
- positive memory-maintenance/dedup relevance
- positive bridge-maintenance relevance
- OGCF false-positive suppression

## Validation Run

Commands run from:

```text
C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core
```

Compile:

```powershell
..\.venv-torch\Scripts\python.exe -m py_compile .\serve.py .\eval\ogcf_intent_outcome_workflow.py .\eval\mine_ogcf_intent_candidates.py .\eval\ogcf_intent_candidate_miner_regression.py
```

Miner regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_candidate_miner_regression.py
```

Result: passed.

OGCF outcome workflow:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_outcome_workflow.py
```

Result: passed.

Outcome logging regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
```

Result: passed.

Selector OGCF regressions:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_gate_regression.py
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_config_regression.py
```

Result: both passed.

Selector architecture gate:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

Result: passed.

## Generated Artifacts

Workflow report:

```text
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_outcome_workflow_results.json
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_outcome_workflow_report.md
```

Outcome log:

```text
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_outcome_workflow.jsonl
```

Candidate artifacts:

```text
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_candidates_from_memory_session.json
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

The workflow produced:

- `8` ask events
- `8` feedback events
- `8` linked feedback events
- `4` candidate sections from the miner

## Mined Candidate Summary

The controlled workflow produced candidate sections for:

```text
bridge_terms
geometry_terms
maintenance_terms
ordinary_fact_terms
```

Notable controlled terms with support >= 2:

```text
bridge_terms: meshlink
geometry_terms: manifolddrift
maintenance_terms: pruneflow
ordinary_fact_terms: lunar
```

The miner also surfaced generic terms such as `note`, `memo`, `review`, `reviewed`, `evidence`, and `pressure`.

## Judgment

The memory-side logging and label loop works.

The generated candidates should not be promoted directly into `config.yaml` because they are controlled synthetic workflow terms. They are useful as a plumbing and regression fixture, not as real production OGCF intent vocabulary.

The most useful production next step is to run Hermes with these labels during real bridge/geometry/maintenance tests, then mine from the real outcome log with `--min-support 2` or higher.

## Recommendation For Selector Session

Use these artifacts to verify the selector-side OGCF candidate pipeline and decide whether the miner needs stronger stopword filtering for generic mined words such as `note`, `memo`, `evidence`, and `reviewed`.

Do not promote the controlled terms unless they are also observed in real agent logs.
