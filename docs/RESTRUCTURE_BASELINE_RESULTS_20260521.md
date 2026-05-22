# Restructure Baseline Results

Date: 2026-05-21

Purpose: record the minimum pre-refactor baseline before restructuring the selector-facing retrieval signal logic.

## Git State

Baseline was run from the local `main` branch with no tracked source changes before the roadmap documents were added.

## Tests Run

### Claim Scope Promotion Gate

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
```

Result:

```text
PASS
```

Required summary:

- nested config: pass
- candidate A/B: pass
- outcome replay: pass
- config regression: pass
- claim-scope deadline filename: pass
- answer-type regression: pass
- answer-type config: pass
- answer-type method filename: pass
- answer-type policy split probe: pass
- policy correction deflection: pass
- multi-intent answer composition: pass
- approval log ambiguity: pass
- repo publish permission ambiguity: pass

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\claim_scope_promotion_gate_report.md`

### Selector Retrieval Guard Randomized Eval

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
```

Result:

```text
PASS: 64/64 aligned, alignment_rate=1.0
```

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\selector_retrieval_guard_randomized_eval_seed20260520_n64_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\selector_retrieval_guard_randomized_eval_seed20260520_n64_report.md`

### Teach/Correct Smoke

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\teach_correct_smoke.py
```

Result:

```text
PASS
```

Important observed behavior:

- The old GitHub upload policy was marked stale.
- The correction was treated as current.
- The final answer preferred the corrected current memory.
- Conflict was surfaced correctly because stale evidence was still present.

## Baseline Judgment

The codebase is ready for the first no-behavior-change extraction of selector-facing retrieval signal logic.

The next implementation should extract the signal scorer while preserving:

- retrieval row field names;
- selector explain behavior;
- claim-scope promotion gate behavior;
- randomized stale/current guard behavior;
- teach/correct correction-chain behavior.

## Post-Extraction Validation

After extracting selector-facing retrieval signal logic into `core/retrieval_signals.py`, the baseline was rerun.

### Module Smoke

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signals_module_smoke.py
```

Result:

```text
PASS
```

Coverage:

- claim-scope scorer;
- answer-type positive scoring;
- answer-type negative scoring;
- scope-deflection detection;
- correction-relevance dampening.

### Baseline Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\teach_correct_smoke.py
```

Results:

```text
claim_scope_promotion_gate.py: PASS
selector_retrieval_guard_randomized_eval.py: PASS, 64/64 aligned
teach_correct_smoke.py: PASS
```

### Extended Selector/Retrieval Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_pressure_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\answer_quality_eval.py
```

Results:

```text
selector_retrieval_calibration_eval.py: PASS, 6/6 aligned
selector_retrieval_guard_pressure_eval.py: PASS, 6/6 aligned
agent_workflow_selector_integration_eval.py: PASS, 7/7 aligned
answer_quality_eval.py: PASS, mean_score=0.9583
```

Post-extraction judgment: the first selector signal extraction preserved current behavior and is ready for review.

## Configurable Signal Rules Validation

After the first extraction, the next hardcoded signal components were moved behind explicit `retrieval_signals` configuration:

- broad generic source/text markers;
- broad generic penalty;
- scope-deflection query terms;
- scope-deflection correction prefixes;
- scope-deflection text markers;
- scope-deflection penalty;
- correction-relevance match threshold;
- correction-relevance minimum damped score.

The default config was added to `config.yaml`, and `pipeline_config_view()` now exposes the normalized `retrieval_signals` config.

### Direct Config Smoke

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signals_module_smoke.py
```

Result:

```text
PASS
```

Additional coverage added:

- custom broad generic source marker;
- custom scope-deflection marker;
- custom correction-relevance minimum.

### Config Parser Smoke

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\config_nested_parser_regression.py
```

Result:

```text
PASS
```

### Behavior Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_pressure_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\teach_correct_smoke.py
..\.venv-torch\Scripts\python.exe .\eval\agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\answer_quality_eval.py
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
```

Results:

```text
claim_scope_promotion_gate.py: PASS
selector_retrieval_guard_randomized_eval.py: PASS, 64/64 aligned
selector_retrieval_calibration_eval.py: PASS, 6/6 aligned
selector_retrieval_guard_pressure_eval.py: PASS, 6/6 aligned
teach_correct_smoke.py: PASS
agent_workflow_selector_integration_eval.py: PASS, 7/7 aligned
answer_quality_eval.py: PASS, mean_score=0.9583
policy_correction_deflection_regression.py: PASS, 3/3
```

Configurable signal judgment: the first hardcoded-to-configurable migration preserved current behavior and created a safer path toward learned signal candidates.

## Retrieval-Signal Candidate Artifact Validation

The next step added a candidate artifact format so Hermes can propose retrieval-signal config changes without editing `config.yaml` directly.

Added:

- `test_corpora/retrieval_signal_candidates_v1.json`
- `eval/retrieval_signal_candidate_eval.py`
- `docs/RETRIEVAL_SIGNAL_CANDIDATE_FORMAT.md`

### Candidate Eval

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_candidate_eval.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
```

Result:

```text
PASS, 7/7 checks
```

The eval confirmed:

- default broad-generic behavior is preserved;
- candidate broad-generic source markers can activate;
- candidate broad-generic text prefixes can activate;
- default scope-deflection behavior is preserved;
- candidate scope-deflection markers can activate;
- candidate scope-deflection does not overactivate on positive permission text;
- default correction-relevance behavior is preserved.

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidate_eval_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_candidate_eval_report.md`

### Behavior Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
```

Results:

```text
claim_scope_promotion_gate.py: PASS
selector_retrieval_guard_randomized_eval.py: PASS, 64/64 aligned
policy_correction_deflection_regression.py: PASS, 3/3
```

Candidate artifact judgment: retrieval-signal changes now have a reproducible proposal-and-validation path. This is an early self-improvement mechanism: failures can produce candidate artifacts, candidates can be tested, and only passing candidates should be promoted into config.

## Retrieval-Signal Candidate Mining Validation

The next step connected candidate artifacts to outcome/failure logs.

Added:

- `eval/mine_retrieval_signal_candidates.py`
- `test_corpora/retrieval_signal_failure_outcomes.jsonl`

The fixture log contains linked `ask` and `feedback` events for:

- a broad/generic operations note retrieved for a specific permission query;
- a correction note that says it is not transfer approval.

### Mining Command

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_retrieval_signal_candidates.py --log .\test_corpora\retrieval_signal_failure_outcomes.jsonl --out-json ..\experiments\retrieval_signal_candidates_mined_fixture.json --out-md ..\experiments\retrieval_signal_candidates_mined_fixture_report.md
```

Result:

```text
PASS, 2 candidate sections mined
```

Mined candidates:

- `broad_generic`: `mission_control`, `global operations note`
- `scope_deflection`: `transfer`, `not transfer approval`

### Mined Candidate Validation

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_candidate_eval.py --candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json --out-json ..\experiments\retrieval_signal_candidate_eval_mined_fixture_results.json --out-md ..\experiments\retrieval_signal_candidate_eval_mined_fixture_report.md
```

Result:

```text
PASS, 7/7 checks
```

### Safety Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
```

Results:

```text
claim_scope_promotion_gate.py: PASS
selector_retrieval_guard_randomized_eval.py: PASS, 64/64 aligned
policy_correction_deflection_regression.py: PASS, 3/3
```

Mining judgment: the architecture now has a complete conservative loop for this signal family: logged failure -> mined candidate artifact -> candidate validation -> promotion gates.

## Retrieval-Signal Promotion Gate Validation

The formal promotion gate for retrieval-signal candidates was added:

- `eval/retrieval_signal_promotion_gate.py`

### Fixture Candidate Gate

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
```

Result:

```text
PASS
```

Required summary:

- candidate eval: pass
- module smoke: pass
- nested config: pass
- claim-scope gate: pass
- randomized guard: pass
- policy deflection: pass
- answer quality: pass

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_promotion_gate_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_promotion_gate_report.md`

### Mined Candidate Gate

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json --out-json ..\experiments\retrieval_signal_promotion_gate_mined_fixture_results.json --out-md ..\experiments\retrieval_signal_promotion_gate_mined_fixture_report.md
```

Result:

```text
PASS
```

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_promotion_gate_mined_fixture_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\retrieval_signal_promotion_gate_mined_fixture_report.md`

Promotion-gate judgment: retrieval-signal candidates now have the same kind of formal guarded path as claim-scope candidates.

## Evidence-State Module Extraction Validation

The next resolver restructuring step extracted evidence-state classification into:

- `core/evidence_states.py`

Added direct coverage:

- `eval/evidence_states_module_smoke.py`

The resolver keeps compatibility wrappers for now:

- `classify_memory_state`
- `evidence_is_too_weak`
- `requires_sensitive_evidence`

This preserves current imports while making the evidence-state logic independently testable.

### Direct Evidence-State Smoke

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_states_module_smoke.py
```

Result:

```text
PASS
```

Coverage:

- `current`
- `stale`
- `summary`
- `disputed`
- `historical`
- weak evidence filtering
- sensitive lookup detection
- resolver compatibility wrapper behavior

### Focused Resolver Regressions

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_conflict_classification.py
..\.venv-torch\Scripts\python.exe .\eval\authority_chain_regression.py
```

Results:

```text
resolver_conflict_classification.py: PASS
authority_chain_regression.py: PASS
```

### Broader Gate Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\answer_quality_eval.py
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
```

Results:

```text
retrieval_signal_promotion_gate.py: PASS
claim_scope_promotion_gate.py: PASS
answer_quality_eval.py: PASS, mean_score=0.9583
policy_correction_deflection_regression.py: PASS, 3/3
```

Evidence-state extraction judgment: the first resolver split preserved behavior and created the right place to later move state thresholds from hardcoded constants into config/calibration.

## Configurable Evidence-State Validation

After extracting evidence-state logic, the next hardcoded resolver components were moved behind explicit `evidence_states` configuration:

- current/stale/disputed feedback thresholds;
- stale language terms and stale regex;
- correction language terms;
- sensitive lookup terms;
- weak-evidence thresholds.

The default config was added to `config.yaml`, and `pipeline_config_view()` now exposes the normalized `evidence_states` config.

### Direct Evidence-State Config Smoke

Commands:

```powershell
..\.venv-torch\Scripts\python.exe -m py_compile .\core\evidence_states.py .\core\resolver.py .\core\pipeline.py .\core\runtime.py .\eval\evidence_states_module_smoke.py
..\.venv-torch\Scripts\python.exe .\eval\evidence_states_module_smoke.py
```

Results:

```text
py_compile: PASS
evidence_states_module_smoke.py: PASS, 20 checks
```

Additional coverage added:

- custom current threshold;
- custom stale language term;
- custom correction language term;
- custom weak-evidence threshold;
- custom sensitive lookup term.

### Config Parser And Resolver Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\config_nested_parser_regression.py
..\.venv-torch\Scripts\python.exe .\eval\resolver_conflict_classification.py
..\.venv-torch\Scripts\python.exe .\eval\authority_chain_regression.py
```

Results:

```text
config_nested_parser_regression.py: PASS
resolver_conflict_classification.py: PASS
authority_chain_regression.py: PASS
```

### Broader Gate Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
..\.venv-torch\Scripts\python.exe .\eval\answer_quality_eval.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 64 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json
```

Results:

```text
claim_scope_promotion_gate.py: PASS
policy_correction_deflection_regression.py: PASS, 3/3
answer_quality_eval.py: PASS, mean_score=0.9583
selector_retrieval_guard_randomized_eval.py: PASS, 64/64 aligned
retrieval_signal_promotion_gate.py: PASS
```

Configurable evidence-state judgment: the second hardcoded-to-configurable migration preserved current behavior. The architecture now has two extracted, configurable control surfaces: retrieval-signal scoring and evidence-state classification.

## Evidence-State Candidate Loop Validation

The next step added a candidate artifact format for evidence-state config changes:

- `test_corpora/evidence_state_candidates_v1.json`
- `test_corpora/evidence_state_failure_outcomes.jsonl`
- `eval/evidence_state_candidate_eval.py`
- `eval/mine_evidence_state_candidates.py`
- `eval/evidence_state_promotion_gate.py`
- `docs/EVIDENCE_STATE_CANDIDATE_FORMAT.md`

Candidate sections now cover:

- stale language terms;
- correction/current language terms;
- sensitive lookup terms;
- state thresholds;
- weak-evidence thresholds.

### Fixture Candidate Eval

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_candidate_eval.py --candidates .\test_corpora\evidence_state_candidates_v1.json
```

Result:

```text
PASS, 8/8 checks
```

The eval confirmed:

- default authority-current behavior is preserved;
- default superseded/stale behavior is preserved;
- default correction-language behavior is preserved;
- default sensitive lookup behavior is preserved;
- candidate stale-language terms can activate;
- candidate correction-language terms can activate;
- candidate sensitive lookup terms can activate;
- candidate weak-evidence thresholds can activate.

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidate_eval_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\evidence_state_candidate_eval_report.md`

### Mining Command

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log .\test_corpora\evidence_state_failure_outcomes.jsonl --out-json ..\experiments\evidence_state_candidates_mined_fixture.json --out-md ..\experiments\evidence_state_candidates_mined_fixture_report.md
```

Result:

```text
PASS, 3 candidate sections mined
```

Mined candidates:

- `stale_language`: `retired truth`
- `correction_language`: `replacement:`
- `sensitive_lookup`: `routing`

### Mined Candidate Validation

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_candidate_eval.py --candidates ..\experiments\evidence_state_candidates_mined_fixture.json --out-json ..\experiments\evidence_state_candidate_eval_mined_fixture_results.json --out-md ..\experiments\evidence_state_candidate_eval_mined_fixture_report.md
```

Result:

```text
PASS, 7/7 checks
```

### Promotion Gates

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_promotion_gate.py --candidates .\test_corpora\evidence_state_candidates_v1.json
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_promotion_gate.py --candidates ..\experiments\evidence_state_candidates_mined_fixture.json --out-json ..\experiments\evidence_state_promotion_gate_mined_fixture_results.json --out-md ..\experiments\evidence_state_promotion_gate_mined_fixture_report.md
```

Results:

```text
fixture evidence_state_promotion_gate.py: PASS
mined evidence_state_promotion_gate.py: PASS
```

Required summary:

- candidate eval: pass
- evidence-state module smoke: pass
- nested config: pass
- resolver conflict: pass
- claim-scope gate: pass
- randomized guard: pass
- policy deflection: pass
- answer quality: pass

Evidence-state candidate-loop judgment: evidence-state classification now has the same conservative self-improvement path as retrieval signals: logged failure -> mined candidate artifact -> candidate validation -> promotion gate.

## Unified Selector Architecture Gate Validation

The next step added a single top-level gate for the selector architecture:

- `eval/selector_architecture_gate.py`

The gate runs both adaptive control-surface promotion gates sequentially:

- `retrieval_signal_promotion_gate.py`
- `evidence_state_promotion_gate.py`

This gives Hermes and the memory-program session one command to run before accepting selector architecture changes or promoting candidate config artifacts.

### Fixture Architecture Gate

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

Result:

```text
PASS
```

Required summary:

- retrieval-signal gate: pass
- evidence-state gate: pass

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\selector_architecture_gate_report.md`

### Mined Fixture Architecture Gate

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_mined_fixture.json --evidence-candidates ..\experiments\evidence_state_candidates_mined_fixture.json --out-json ..\experiments\selector_architecture_gate_mined_fixture_results.json --out-md ..\experiments\selector_architecture_gate_mined_fixture_report.md
```

Result:

```text
PASS
```

Unified gate judgment: the selector architecture now has a single promotion checkpoint covering both retrieval-signal adaptation and evidence-state adaptation. This is the best current gate to run before handoff, before config promotion, and before GitHub upload.

## Memory-Session Outcome Log Contract Validation

The memory-program session responded to the selector handover with:

- enriched `ask.response.raw_results` fields in `serve.py`;
- `eval/outcome_logging_regression.py` coverage for selector-miner training fields;
- `eval/memory_outcome_contract_workflow.py`, a synthetic linked `ask`/`feedback` workflow.

The workflow produced:

- 5 ask events;
- 5 feedback events;
- 5 linked feedback events;
- 0 missing selector-miner training fields.

### Contract Regression Rerun

Commands:

```powershell
..\.venv-torch\Scripts\python.exe -m py_compile .\serve.py .\eval\outcome_logging_regression.py .\eval\memory_outcome_contract_workflow.py .\eval\mine_retrieval_signal_candidates.py .\eval\mine_evidence_state_candidates.py .\eval\selector_architecture_gate.py
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
..\.venv-torch\Scripts\python.exe .\eval\memory_outcome_contract_workflow.py
```

Results:

```text
py_compile: PASS
outcome_logging_regression.py: PASS
memory_outcome_contract_workflow.py: PASS
```

### Memory-Generated Candidate Mining

Commands:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\mine_retrieval_signal_candidates.py --log ..\experiments\memory_outcome_contract_workflow.jsonl --out-json ..\experiments\retrieval_signal_candidates_from_memory_session.json --out-md ..\experiments\retrieval_signal_candidates_from_memory_session_report.md
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log ..\experiments\memory_outcome_contract_workflow.jsonl --out-json ..\experiments\evidence_state_candidates_from_memory_session.json --out-md ..\experiments\evidence_state_candidates_from_memory_session_report.md
```

Results:

```text
retrieval-signal miner: PASS, 1 candidate section
evidence-state miner: PASS, 2 candidate sections
```

Mined candidates:

- retrieval `broad_generic`: `ops_control_note`, `universal_policy_note`, `ops control note`, `universal policy note`
- evidence `stale_language`: `retired truth`
- evidence `correction_language`: `verified current:`

Judgment: the candidates are useful contract proof, but they should not be promoted from this single synthetic workflow.

### Unified Gate With Memory Candidates

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_from_memory_session.json --evidence-candidates ..\experiments\evidence_state_candidates_from_memory_session.json --out-json ..\experiments\selector_architecture_gate_memory_session_candidates_results.json --out-md ..\experiments\selector_architecture_gate_memory_session_candidates_report.md
```

Result:

```text
PASS
```

### Optional Candidate Fallback

`eval/selector_architecture_gate.py` now supports:

```text
--allow-missing-candidates
```

If a supplied candidate file is missing, the gate uses the default fixture for that candidate family and records the fallback in the report.

Validation command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py --retrieval-candidates ..\experiments\retrieval_signal_candidates_from_memory_session.json --evidence-candidates .\does_not_exist_evidence_candidates.json --allow-missing-candidates --out-json ..\experiments\selector_architecture_gate_missing_evidence_fallback_results.json --out-md ..\experiments\selector_architecture_gate_missing_evidence_fallback_report.md
```

Result:

```text
PASS
```

Memory-session contract judgment: the selector side can now consume memory-generated outcome logs, mine candidate artifacts, run the unified architecture gate with those candidates, and tolerate one missing candidate family during automation.

## Selector Candidate Pipeline From Log

The next step added a one-command wrapper for the intended real-Hermes workflow:

- `eval/selector_candidate_pipeline_from_log.py`

It does the following:

1. mines retrieval-signal candidates from an outcome log;
2. mines evidence-state candidates from the same outcome log;
3. runs the unified selector architecture gate with those mined candidates;
4. writes a top-level JSON and Markdown report.

Validation command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log ..\experiments\memory_outcome_contract_workflow.jsonl
```

Result:

```text
PASS
retrieval candidate sections: 1
evidence candidate sections: 2
```

Artifacts:

- `C:\Users\victo\Desktop\projcod2\experiments\selector_candidate_pipeline_from_log_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\selector_candidate_pipeline_from_log_report.md`

Pipeline judgment: this is now the preferred command for testing a real Hermes outcome log before any candidate-promotion discussion.

## Hermes Real-Log Tooling Fixes

Hermes ran the selector candidate pipeline against a realistic generated Hermes outcome log with:

- 30 ask events;
- 16 linked feedback events;
- normal queries;
- stale/current corrections;
- wrong-domain distractors;
- broad policy distractors;
- sensitive lookups;
- bad-source cases.

The pipeline passed, but Hermes found two auxiliary-tooling bugs.

### Bug 1: Missing Claim-Scope Candidate File

Problem:

```text
claim_scope_promotion_gate.py crashed when experiments/claim_scope_alias_candidates_v2.json was missing.
```

Fix:

`eval/claim_scope_candidate_ab_eval.py` now treats a missing candidate file as a no-op candidate artifact:

```json
{
  "schema": "claim_scope_alias_candidates/v1",
  "candidates": []
}
```

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_candidate_ab_eval.py --candidates ..\experiments\definitely_missing_claim_scope_candidates.json --out-json ..\experiments\claim_scope_candidate_ab_missing_file_results.json --out-md ..\experiments\claim_scope_candidate_ab_missing_file_report.md
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_promotion_gate.py --candidates ..\experiments\definitely_missing_claim_scope_candidates.json --out-json ..\experiments\claim_scope_promotion_gate_missing_candidate_results.json --out-md ..\experiments\claim_scope_promotion_gate_missing_candidate_report.md
```

Results:

```text
claim_scope_candidate_ab_eval.py missing candidate: PASS
claim_scope_promotion_gate.py missing candidate: PASS
```

### Bug 2: Redundant Broad-Generic Source Markers

Problem:

```text
mine_retrieval_signal_candidates.py could mine broad_policy_note even though broad_policy already covered it by substring match.
```

Fix:

`eval/mine_retrieval_signal_candidates.py` now checks source stems and text prefixes using the same coverage semantics as `RetrievalSignalScorer.broad_generic_note()`.

Added:

- `test_corpora/retrieval_signal_redundant_marker_outcomes.jsonl`
- `eval/retrieval_signal_miner_regression.py`

`eval/retrieval_signal_promotion_gate.py` now runs this miner regression as a required sub-check.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_miner_regression.py
..\.venv-torch\Scripts\python.exe .\eval\retrieval_signal_promotion_gate.py --candidates .\test_corpora\retrieval_signal_candidates_v1.json --out-json ..\experiments\retrieval_signal_promotion_gate_after_tooling_fixes_results.json --out-md ..\experiments\retrieval_signal_promotion_gate_after_tooling_fixes_report.md
```

Results:

```text
retrieval_signal_miner_regression.py: PASS
retrieval_signal_promotion_gate.py: PASS, miner_regression_ok=true
```

### Hermes Real-Log Pipeline Rerun

Command:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\logs\hermes_real_test_outcome.jsonl --out-json ..\experiments\selector_candidate_pipeline_hermes_real_after_gate_regression_results.json --out-md ..\experiments\selector_candidate_pipeline_hermes_real_after_gate_regression_report.md
```

Result:

```text
PASS
retrieval candidate sections: 1
evidence candidate sections: 1
architecture gate: PASS
```

Tooling-fix judgment: Hermes' two reported auxiliary bugs are fixed, covered by regression checks, and the full real-log pipeline still passes.

## Hermes Real-Ask Feedback Log Validation

Hermes next tested a log built from real `memory_outcomes.jsonl` ask events plus realistic linked feedback.

First, Hermes confirmed that the true real log contained:

- 426 ask events;
- 0 feedback events.

The pipeline correctly passed with zero mined candidates because candidate mining requires linked feedback.

Hermes then generated a feedback-enriched log from real ask events:

- 27 real ask events;
- 12 linked feedback events;
- labels covering wrong domain, bad source, stale, irrelevant, not useful, sensitive lookup, needs exact evidence, and current.

Pipeline result:

```text
PASS
retrieval candidate sections: 1
evidence candidate sections: 1
architecture gate: PASS
```

Mined candidates:

- retrieval `broad_generic`: `report_template_note`
- evidence `sensitive_lookup`: `does`, `drink`, `prefer`, `project`, `working`

Hermes judged:

- `report_template_note` is plausible but needs more support before promotion;
- `drink`, `prefer`, `project`, and `working` are plausible exact-evidence markers;
- `does` is stop-word noise.

### Evidence Miner Stop-Term Fix

Fix:

`eval/mine_evidence_state_candidates.py` now filters additional auxiliary/modal terms such as:

```text
does, have, has, had, would, could, will, must, need, needs
```

Added:

- `test_corpora/evidence_state_sensitive_stop_terms_outcomes.jsonl`
- `eval/evidence_state_miner_regression.py`

`eval/evidence_state_promotion_gate.py` now runs this miner regression as a required sub-check.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_miner_regression.py
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\logs\hermes_real_with_feedback.jsonl --out-json ..\experiments\evidence_candidates_hermes_real_stop_terms_fix.json --out-md ..\experiments\evidence_candidates_hermes_real_stop_terms_fix.md
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\logs\hermes_real_with_feedback.jsonl --out-json ..\experiments\selector_real_with_feedback_after_evidence_stop_fix_results.json --out-md ..\experiments\selector_real_with_feedback_after_evidence_stop_fix_report.md
```

Results:

```text
evidence_state_miner_regression.py: PASS
Hermes evidence candidate rerun: PASS, terms=drink, prefer, project, working
selector_candidate_pipeline_from_log.py: PASS
```

Evidence miner judgment: the latest Hermes run produced the first useful candidate-quality improvement. The architecture should still not promote these terms yet; they should be held for repeated support from real linked feedback.

## Hermes Live Linked-Feedback Validation

Hermes then ran the pipeline against the live memory server on `localhost:8765` using namespace `hermes_policy_shadow_day1`.

The run used real server calls:

- `POST /ask`
- review actual retrieved rows;
- `POST /feedback` linked back to the ask `operation_id`.

Live run stats:

- 48 ask events generated that day;
- 17 real linked feedback events;
- 100% linked feedback with matching ask events;
- labels: `current`, `wrong_domain`, `sensitive_lookup`, `needs_exact_evidence`, `stale`.

Pipeline result:

```text
PASS
retrieval candidate sections: 0
evidence candidate sections: 1
architecture gate: PASS
```

Candidate analysis:

- no retrieval-signal candidates were mined, which is correct because no broad/generic note failures were observed;
- evidence-state sensitive lookup terms mined: `configuration`, `drink`, `exact`, `live`, `morning`, `server`;
- `live` was judged marginal because it is too broad as a standalone config term.

### Ambiguous Sensitive Term Holdout

Fix:

`eval/mine_evidence_state_candidates.py` now holds out ambiguous sensitive terms instead of adding them directly to candidate config.

Held-out terms currently include:

```text
live, lives, located, location
```

These terms still appear in the miner report under:

```text
support.held_out_sensitive_lookup
```

but they are not placed in the candidate `terms` list.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_state_miner_regression.py
..\.venv-torch\Scripts\python.exe .\eval\mine_evidence_state_candidates.py --log C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\logs\memory_outcomes.jsonl --out-json ..\experiments\evidence_candidates_live_session_heldout_terms_results.json --out-md ..\experiments\evidence_candidates_live_session_heldout_terms_report.md
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log C:\Users\victo\Documents\GitHub\clc-gcl-memory-core\logs\memory_outcomes.jsonl --out-json ..\experiments\selector_real_live_session_after_heldout_terms_results.json --out-md ..\experiments\selector_real_live_session_after_heldout_terms_report.md
```

Results:

```text
evidence_state_miner_regression.py: PASS
live held out: true
live candidate mined: false
live-session pipeline: PASS
candidate terms: configuration, drink, exact, morning, server
held-out terms: live
```

Live-feedback judgment: the architecture has now completed a real closed loop from live ask/feedback events to candidate mining and gated validation. Candidate promotion should still wait for repeated evidence across more sessions.
