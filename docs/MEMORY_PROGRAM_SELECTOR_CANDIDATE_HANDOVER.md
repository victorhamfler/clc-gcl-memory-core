# CLC-GCL Selector Candidate Handover

Date: 2026-05-20

This document packages the current CLC-GCL selector architecture candidate for later review by the separate memory-program development session. Do not merge it blindly into that program. Treat it as a candidate module and reproduce the tests below before integration.

## What Changed

The candidate adds three retrieval and selector mechanisms:

- Correction-chain scoring: current correction-chain memories receive positive retrieval pressure, while superseded memories receive negative pressure.
- Claim-scope scoring: retrieval now estimates whether a memory matches the specific claim slot in the query, such as codename vs status, radar method vs radar report filename, or drink vs pizza.
- Correction relevance damping: structurally current correction memories are damped when they are near-topic but not the actual claim being asked about.

The resolver and selector now consume these signals:

- `claim_scope_score`
- `correction_relevance_score`
- `correction_chain_score`

These fields are exposed in retrieval rows and compact evidence so an agent harness can inspect why an answer or selector decision was made.

## Files Added

- `eval/agent_workflow_selector_integration_eval.py`
- `eval/correction_chain_retrieval_regression.py`
- `eval/selector_near_topic_distractor_eval.py`

## Files Changed

- `core/pipeline.py`
- `core/resolver.py`
- `core/selector_runtime.py`
- `config.yaml`

## Validation Already Run

All of these passed on this machine:

- `agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10`: 7/7
- `agent_workflow_selector_integration_eval.py --embedding-backend config --top-k 10`: 7/7
- `selector_near_topic_distractor_eval.py --embedding-backend hash --top-k 10`: 6/6
- `selector_near_topic_distractor_eval.py --embedding-backend config --top-k 10`: 6/6
- `correction_chain_retrieval_regression.py`: PASS
- `selector_retrieval_guard_pressure_eval.py --embedding-backend hash --top-k 10`: 6/6
- `selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8`: 6/6
- `selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 256 --seed 20260520 --top-k 10`: 256/256
- `selector_retrieval_guard_randomized_eval.py --embedding-backend config --cases 128 --seed 20260520 --top-k 10`: 128/128
- `correction_evidence_ranking_regression.py`: PASS
- `teach_correct_smoke.py`: PASS
- `session_topic_switch_regression.py`: PASS
- `session_cross_topic_leak_regression.py`: PASS
- `session_context_boundary_regression.py`: PASS
- `private_label_correction_regression.py`: PASS
- `domain_contamination_eval.py`: PASS
- `answer_specificity_eval.py`: PASS
- `answer_quality_eval.py`: PASS, mean score 0.9583

## Reproduction Commands

From the `clc_gcl_memory_core` folder:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\agent_workflow_selector_integration_eval.py --embedding-backend config --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\selector_near_topic_distractor_eval.py --embedding-backend hash --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\selector_near_topic_distractor_eval.py --embedding-backend config --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\correction_chain_retrieval_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 256 --seed 20260520 --top-k 10
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_guard_randomized_eval.py --embedding-backend config --cases 128 --seed 20260520 --top-k 10
```

## Integration Guidance For The Other Memory Program

The other memory program should first integrate this as an external selector/retrieval candidate, not rewrite its whole memory system around it.

Recommended integration order:

1. Import or copy the selector-facing retrieval row fields into the memory program's test branch.
2. Confirm the memory program can produce or preserve these fields:
   - `authority_state`
   - `supersedes_memory_ids`
   - `superseded_by_memory_ids`
   - `correction_chain_depth`
   - `correction_chain_score`
   - `claim_scope_score`
   - `correction_relevance_score`
3. Run the agent workflow integration eval or an equivalent harness against the memory program's real teach/correct/ask flow.
4. Compare answer correctness, false hard-escalations, and stale/current conflict handling before enabling it in normal operation.

## Current Readiness Judgment

This candidate is ready for controlled integration testing. It is not yet a final production architecture because it has not been run inside the other memory program's full live harness for multiple days.

The most important next external test is a long-running agent workflow where the memory program repeatedly mixes:

- clean facts
- direct corrections
- deep correction chains
- near-topic distractors
- unrelated stale clutter
- multi-turn follow-up questions

The expected result is that direct same-claim correction chains trigger hard refresh behavior, while unrelated or near-topic-but-different-claim memories remain protected.
