# OGCF Intent Candidates Handover To Memory Session

This handover is from the selector-module session to the memory-program session.

## Current State

The selector architecture now has a config-backed OGCF intent controller:

- `core/ogcf_intent.py`
- `core/ogcf_signals.py`
- `config.yaml` section `ogcf_intent`
- regression: `eval/ogcf_intent_config_regression.py`
- regression: `eval/ogcf_intent_gate_regression.py`

The controller decides when OGCF bridge-cluster pressure is relevant:

- ordinary fact lookups should usually stay protected;
- explicit bridge/OGCF geometry questions can receive pressure;
- true loop overload still bypasses the intent gate;
- all terms, scores, and gate thresholds are now configurable.

## New Selector-Side Miner

The selector session added:

```powershell
py .\eval\mine_ogcf_intent_candidates.py --log <outcome-log.jsonl> --min-support 2 --out-json ..\experiments\ogcf_intent_candidates_from_memory_session.json --out-md ..\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

It writes proposal-only artifacts:

```text
schema: ogcf_intent_candidates/v1
```

It does not edit `config.yaml` and does not promote anything automatically.

Regression:

```powershell
py .\eval\ogcf_intent_candidate_miner_regression.py
```

## Important Finding

Running the miner on the current local outcome log found:

- ask events: `608`
- feedback events: `183`
- OGCF intent candidates: `0`

This is expected because current outcome logs do not yet contain OGCF-specific feedback labels.

## What The Memory Session Should Add

The memory program should keep producing linked `ask` and `feedback` events, but add OGCF-specific feedback labels when Hermes is testing bridge/geometry behavior.

Use positive labels when OGCF pressure was helpful:

- `bridge_relevant`
- `cross_domain_bridge`
- `ogcf_bridge`
- `ogcf_geometry`
- `bridge_geometry`
- `loop_overload`
- `memory_maintenance`
- `dedup`
- `duplicate`
- `bridge_maintenance`

Use suppression labels when OGCF pressure would be wrong or too broad:

- `ogcf_false_positive`
- `bridge_irrelevant`
- `ordinary_lookup`
- `ordinary_fact`
- `unrelated_bridge`
- `no_ogcf_pressure`

Each feedback row should include:

- `linked_operation_id`
- original `query`
- `memory_id` when feedback targets a retrieved row
- `label`
- `rating`
- enough retrieved evidence rows in the linked ask response for the selector miner to inspect `text`, `source`, `score`, and relevance signals.

## Development Direction

Keep the session ownership split:

- selector session owns `ogcf_intent`, candidate miners, gates, and selector config;
- memory-program session owns realistic agent workflows, linked outcome logs, API behavior, and Hermes long-run tests.

The roadmap direction is:

```text
config-backed symbolic gate
-> labeled Hermes outcomes
-> mined OGCF intent candidate artifacts
-> readiness / promotion gate
-> later small learned neural-symbolic scorer
```

Do not directly promote mined terms into `config.yaml` from the memory session. Hand candidate artifacts back to the selector session first.
