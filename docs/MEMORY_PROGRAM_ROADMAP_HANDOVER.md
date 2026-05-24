# Memory Program Roadmap Handover

This handover is from the selector-module session to the memory-program session.

The user has asked us to keep development split for now:

- selector-module session: selector architecture, configurable controller surfaces, OGCF intent, candidate miners, promotion gates, selector documentation;
- memory-program session: the full memory program, API behavior, learning/feedback flows, realistic Hermes workflows, outcome logs, and memory-side integration.

Do not merge ownership unless the user explicitly decides to centralize both projects later.

## Why This Handover Exists

Since the last memory-session improvement, the selector session continued the restructuring roadmap. The roadmap goal is to remove hardcoded behavior gradually and turn the program into a local neural-symbolic adaptive memory brain.

The direction is not to build a frontier-scale model. The direction is:

```text
working symbolic memory program
-> configurable controller surfaces
-> outcome-log candidate mining
-> promotion/readiness gates
-> small learned or calibrated neural-symbolic controllers
```

The learned part should propose or score memory-control features. The symbolic part should keep safety contracts, auditability, rollback, and promotion gates.

## Current Architecture Direction

The current combined architecture should be understood like this:

```text
Memory program stores and retrieves evidence
        |
        v
Canonical memory organizes support, duplicates, and provenance
        |
        v
OGCF detects geometry/bridge/maintenance pressure
        |
        v
Selector decides protect vs verified refresh vs XSEQ refresh
        |
        v
Outcome logs provide evidence for future adaptive improvements
```

Important selector-side components now exist:

- `canonical_memory` config and canonical retrieval support metadata;
- OGCF bridge/geometry signals;
- query-aware OGCF intent gate;
- config-backed `ogcf_intent` controller surface;
- candidate miner for `ogcf_intent_candidates/v1`;
- regressions proving ordinary queries stay protected while bridge/geometry queries can receive pressure.

## What Changed On The Selector Side

The selector session added a configurable OGCF intent gate.

Files:

- `core/ogcf_intent.py`
- `core/ogcf_signals.py`
- `core/ogcf_selector.py`
- `config.yaml`, section `ogcf_intent`

The gate distinguishes:

- ordinary fact lookup;
- memory maintenance;
- cross-domain bridge synthesis;
- explicit OGCF/geometry query;
- weak geometry context.

The gate controls whether passive bridge-cluster membership should affect selector features.

Behavior:

- ordinary fact lookups should usually not be escalated only because they touch a bridge cluster;
- explicit bridge/OGCF geometry questions can receive bridge pressure;
- true loop overload still bypasses the intent gate;
- config now controls terms, scores, and thresholds.

Regression tests:

```powershell
py .\eval\ogcf_intent_gate_regression.py
py .\eval\ogcf_intent_config_regression.py
```

## New Candidate Miner

The selector session added a proposal-only miner:

```powershell
py .\eval\mine_ogcf_intent_candidates.py --log <outcome-log.jsonl> --min-support 2 --out-json ..\experiments\ogcf_intent_candidates_from_memory_session.json --out-md ..\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

It writes:

```text
schema: ogcf_intent_candidates/v1
```

It can propose additions to:

- `bridge_terms`
- `geometry_terms`
- `maintenance_terms`
- `ordinary_fact_terms`

It does not mutate config. It does not promote terms automatically.

Regression:

```powershell
py .\eval\ogcf_intent_candidate_miner_regression.py
```

Current local result:

- `logs/memory_outcomes.jsonl` had `608` ask events and `183` feedback events;
- the miner found `0` OGCF intent candidates;
- reason: current logs do not yet contain OGCF-specific feedback labels.

This is the main memory-session task now.

## What The Memory Program Should Improve Next

The memory program should evolve its outcome logging and Hermes test workflows so the selector can learn from real memory behavior.

### 1. Add OGCF-Specific Feedback Labels

When Hermes runs bridge/geometry/memory-maintenance tests, feedback should use explicit labels.

Positive labels when OGCF pressure is useful:

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

Suppression labels when OGCF pressure would be wrong:

- `ogcf_false_positive`
- `bridge_irrelevant`
- `ordinary_lookup`
- `ordinary_fact`
- `unrelated_bridge`
- `no_ogcf_pressure`

These labels should be stored as normal feedback events linked to the original ask operation.

### 2. Preserve Linked Ask/Feedback Contract

Every feedback event should include:

- `linked_operation_id`
- original `query`
- `memory_id` when feedback targets a retrieved row
- `label`
- `rating`
- enough retrieved evidence in the linked ask response for selector mining.

The linked ask response should preserve these row fields when available:

- `memory_id`
- `text`
- `source`
- `score`
- `cosine`
- `text_match_score`
- `claim_scope_score`
- `answer_type_score`
- `authority_state`
- `supersession_score`
- `relation_supersession_score`
- `stored_contradiction_score`
- selector diagnostics if available.

The selector session does not need memory-side private implementation details. It needs good outcome evidence.

### 3. Keep Candidate Promotion Out Of The Memory Session

The memory session should not directly edit selector config for mined terms.

Correct flow:

```text
Hermes run
-> linked ask/feedback logs
-> candidate artifact
-> handover to selector session
-> selector gates and regressions
-> possible config promotion
```

This protects the project from overfitting one test run.

### 4. Continue Removing Hardcoded Memory-Side Behavior

The memory program should continue the same roadmap principle:

```text
hardcoded behavior -> config surface -> candidate artifact -> gate -> learned/calibrated controller
```

Good memory-side targets:

- resolver ranking weights;
- answer confidence thresholds;
- stale/current evidence heuristics;
- correction-linking thresholds;
- consolidation candidate thresholds;
- summarization/consolidation acceptance criteria;
- when to ask user confirmation before learning;
- when to store a correction as standalone vs linked update.

Do not jump directly to learned behavior. First make each surface configurable and testable.

### 5. Build Better Real-World Hermes Logs

The next Hermes runs should include:

- ordinary fact queries that should remain protected;
- bridge/geometry questions where OGCF pressure should matter;
- duplicate-heavy cases where canonical support/provenance should matter;
- stale/current correction cases;
- near-topic distractor cases;
- multi-intent queries;
- long-running namespace cases where support and duplicate pressure evolve over time.

The memory program should report both success and failure. The failures are especially valuable because candidate miners need realistic negative labels.

## What Not To Do

Do not:

- directly promote mined OGCF terms into selector `config.yaml`;
- remove duplicate rows blindly without preserving canonical support/provenance;
- merge semantic near-duplicates automatically when they may represent corrections or conflicts;
- collapse all feedback into generic labels like `good` or `bad`;
- hide retrieved evidence rows from outcome logs;
- change selector-owned files from the memory session unless the user explicitly asks for cross-session centralization.

## How To Coordinate With This Session

When the memory session has results, hand back:

- the outcome log path;
- any generated candidate artifact path;
- a markdown report with counts and examples;
- test command outputs;
- notes about memory-side code changes;
- any failure cases Hermes found.

Recommended command for OGCF intent candidate mining after a Hermes run:

```powershell
py .\eval\mine_ogcf_intent_candidates.py --log <memory-session-outcome-log.jsonl> --min-support 2 --out-json ..\experiments\ogcf_intent_candidates_from_memory_session.json --out-md ..\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

Then give the selector session:

```text
..\experiments\ogcf_intent_candidates_from_memory_session.json
..\experiments\ogcf_intent_candidates_from_memory_session_report.md
```

## Current Best Next Action For Memory Session

Implement or verify support for OGCF-specific feedback labels in the memory program and Hermes harness.

Then run a small controlled Hermes test with:

1. one ordinary fact query that should suppress OGCF pressure;
2. one bridge-relevant query;
3. one explicit OGCF geometry query;
4. one memory-maintenance/dedup query;
5. one false-positive bridge case.

After that, run the miner and hand the result back to the selector session.

This will move the architecture from manually configured OGCF intent toward a real adaptive neural-symbolic controller.
