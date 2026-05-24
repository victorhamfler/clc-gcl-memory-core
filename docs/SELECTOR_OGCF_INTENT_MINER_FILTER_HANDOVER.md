# Selector OGCF Intent Miner Filter Handover

Date: 2026-05-24

## Purpose

This handover responds to:

```text
docs/MEMORY_SESSION_OGCF_INTENT_OUTCOME_HANDOVER.md
```

The memory session added OGCF-specific feedback label defaults and a controlled linked ask/feedback workflow. The selector session verified that the workflow is useful and then hardened the candidate miner so generic workflow terms are not treated as controller vocabulary.

## Selector-Side Change

Updated:

```text
eval/mine_ogcf_intent_candidates.py
eval/ogcf_intent_candidate_miner_regression.py
docs/CLC_ARCHITECTURE_STATUS.md
docs/ARCHITECTURE_RESTRUCTURE_ROADMAP.md
```

The miner now filters additional generic terms observed in the memory-session workflow, including:

```text
note
notes
memo
evidence
review
reviewed
pressure
bridge
connects
policy
radar
project
support
```

The goal is not to add another permanent hand-built vocabulary surface. This is a safety filter for the dry-run miner so ordinary scaffold words do not become promotion candidates before the later readiness/semantic-memory stages.

## Validation Result

The regenerated memory-session candidate artifact now contains only the controlled terms:

```text
bridge_terms: meshlink
geometry_terms: manifolddrift
maintenance_terms: pruneflow
ordinary_fact_terms: lunar
```

Generic terms from the previous report were removed from the emitted candidates and support map.

## Commands Run

From:

```text
C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core
```

```powershell
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_candidate_miner_regression.py
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_config_regression.py
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_gate_regression.py
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_outcome_workflow.py
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

All passed.

## Generated Artifacts

The memory-session workflow regenerated:

```text
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_outcome_workflow_results.json
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_outcome_workflow_report.md
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_candidates_from_memory_session.json
C:\Users\victo\Desktop\projcod2\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

## Recommendation For Memory Session

Keep the feedback labels and linked ask/feedback workflow.

Do not promote the controlled synthetic terms into runtime config. They are proof that the adaptive loop works, not production vocabulary.

The next useful memory-side contribution is to produce real Hermes outcome logs with these labels during normal work:

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
ogcf_false_positive
bridge_irrelevant
ordinary_lookup
ordinary_fact
unrelated_bridge
no_ogcf_pressure
```

Those real logs should then be mined by the selector-side candidate pipeline and passed through readiness/semantic-memory evaluation before any config promotion.
