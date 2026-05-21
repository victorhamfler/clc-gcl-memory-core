# Baseline And First Extraction Plan

Date: 2026-05-21

## Objective

Prepare the codebase for restructuring without losing the behavior that previous experiments already proved useful.

The first implementation step should extract selector-facing retrieval signal logic from `core/pipeline.py` into a focused module while keeping all existing public behavior unchanged.

## Why This Is The First Step

The current project has two large pressure points:

- `core/pipeline.py` is doing too many jobs.
- `core/resolver.py` is too large and heuristic-heavy.

Starting with the resolver would be high-risk because it directly controls final answers. Starting with selector-facing retrieval signals is safer because:

- those mechanisms are already well tested by selector and claim-scope regressions;
- they are mostly pure scoring logic;
- they are central to this session's architecture work;
- extracting them creates a clean place to convert hardcoded vocabularies and thresholds into config-driven and later learned mechanisms.

## Baseline Tests To Run Before Refactor

Run these before the first extraction and save the output in a report.

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_pressure_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 256 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\teach_correct_smoke.py
..\.venv-torch\Scripts\python.exe .\eval\answer_quality_eval.py
```

If time or hardware is tight, run this minimum baseline:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\teach_correct_smoke.py
```

## First Extraction Target

Move the following logic out of `MemoryPipeline`:

- `_claim_scope_affinity`
- `_claim_scope_matches`
- `_answer_type_affinity`
- `_answer_type_rule_terms`
- `_broad_generic_note`
- `_scope_deflection_note`
- `_correction_relevance`
- related normalization helpers that are only needed by these scoring functions

Recommended first module:

```text
core/retrieval_signals.py
```

This module should expose small pure functions or a small config-carrying class, for example:

```text
RetrievalSignalScorer
  - claim_scope_affinity(query, text, source)
  - claim_scope_matches(query, text)
  - answer_type_affinity(query, text, source)
  - broad_generic_note(text, source)
  - scope_deflection_note(query, text, source)
  - correction_relevance(query, text, source, claim_scope_score, text_score)
```

`MemoryPipeline` should delegate to this scorer and keep the same result fields:

- `claim_scope_score`
- `answer_type_score`
- `correction_relevance_score`

## Behavior Preservation Rules

The first extraction must obey these rules:

1. Do not change scoring formulas.
2. Do not rename retrieval row fields.
3. Do not change API responses.
4. Do not move config keys yet.
5. Do not add new adaptive behavior yet.
6. Do not modify the other memory-program session's code directly.

The only acceptable behavior change in the first extraction is no behavior change.

## Hardcoded Components To Track

During extraction, mark each hardcoded component as a future migration candidate.

### Claim Scope

Current issue:

Some claim-scope behavior was historically hardcoded around specific topic words and then improved through config. It should continue moving toward config-defined aliases and eventually learned alias candidates.

Target:

- all aliases and exclusions come from config;
- candidate aliases can be mined from outcome failures;
- promotion gate accepts aliases only if they improve holdout behavior.

### Answer Type

Current issue:

Answer-type rules are config-backed now, but the rule engine is still fixed and hand-designed.

Target:

- keep config rules as the safe baseline;
- log answer-type features and outcomes;
- learn rule candidates from failures;
- promote only conflict-safe candidates.

### Resolver Weights

Current issue:

Evidence preference uses fixed coefficients.

Target:

- move weights to config;
- add calibration reports;
- later test Bayesian or bandit-style weight updates from answer feedback.

### CSD And CLC Thresholds

Current issue:

Novelty, contradiction, domain-shift, recall, focus, and protect thresholds are mostly fixed.

Target:

- move thresholds to config;
- log per-domain false-positive and false-negative signals;
- later test per-domain threshold calibration.

### G-CL Stability

Current issue:

Stability can make old domains resistant to useful updates.

Target:

- add configurable stability decay;
- test whether drift variance and correction rate should adapt stability over time.

### Selector Policy Learning

Current issue:

The selector has a useful guarded kNN wrapper, but online learning is not automatic.

Target:

- log selector decision, retrieval diagnostics, chosen policy, and outcome;
- admit only conflict-safe samples;
- compare candidate selector artifact against fixed rules, previous accepted selector, and holdout failures;
- promote only if all guard suites pass.

## Acceptance Criteria For First Extraction

The extraction is successful if:

- baseline tests pass before and after;
- `MemoryPipeline.retrieve()` still emits the same selector-facing fields;
- `POST /selector_explain` behavior remains unchanged;
- claim-scope and answer-type config views remain unchanged;
- no new runtime dependency is introduced;
- the new module has focused unit-style coverage or is covered by existing promotion tests.

## Next Step After First Extraction

Once selector signal extraction is complete, the next refactor should split `core/resolver.py` into evidence classification, ranking, conflict detection, answer building, and confidence estimation.

Only after those splits should the project begin replacing resolver coefficients with calibrated or learned weights.
