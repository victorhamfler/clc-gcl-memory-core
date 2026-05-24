# Hermes Selector Real Log Test Handover

Date: 2026-05-21

## Purpose

This handover is for the Hermes agent/orchestrator.

The selector and memory sessions have finished a restructure checkpoint. The next task is to run the selector candidate pipeline on a real Hermes outcome log, not only the synthetic contract workflow.

The goal is to find whether real agent-memory failures can safely produce useful retrieval-signal or evidence-state candidate artifacts.

Do not promote candidates into production config during this test. Produce reports only.

## Repository

Repository:

```text
https://github.com/victorhamfler/clc-gcl-memory-core.git
```

Branch:

```text
main
```

The pushed version should include:

- selector signal extraction;
- evidence-state extraction;
- memory outcome-log field enrichment;
- candidate miners;
- candidate evals;
- promotion gates;
- unified selector architecture gate;
- one-command candidate pipeline from an outcome log.

## Main Command To Test

From the repository root:

```text
clc_gcl_memory_core
```

Run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log PATH_TO_REAL_HERMES_OUTCOME_LOG.jsonl --out-json ..\experiments\selector_candidate_pipeline_hermes_real_results.json --out-md ..\experiments\selector_candidate_pipeline_hermes_real_report.md
```

If running from WSL or a Linux environment, use the Python interpreter available to Hermes and equivalent paths, for example:

```bash
python eval/selector_candidate_pipeline_from_log.py --log /path/to/real_hermes_outcome_log.jsonl --out-json ../experiments/selector_candidate_pipeline_hermes_real_results.json --out-md ../experiments/selector_candidate_pipeline_hermes_real_report.md
```

## What The Pipeline Does

The pipeline:

1. reads one outcome log;
2. mines retrieval-signal candidates;
3. mines evidence-state candidates;
4. classifies candidate promotion readiness;
5. builds a report-only semantic candidate memory;
6. runs the unified selector architecture gate with those mined candidates;
7. writes one top-level JSON report and one Markdown report.

It also writes sub-artifacts next to the top-level report:

- retrieval candidate JSON and Markdown;
- evidence candidate JSON and Markdown;
- promotion-readiness JSON and Markdown;
- semantic-memory JSON and Markdown;
- unified architecture gate JSON and Markdown.

## Required Outcome Log Shape

The log should contain linked `ask` and `feedback` events.

Minimum useful ask event:

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

Minimum useful feedback event:

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

Important:

- `feedback.linked_operation_id` must match the related ask event.
- `feedback.payload.request.memory_id` must identify the judged retrieval row.
- `ask.payload.response.raw_results` should include the row being judged.

## Useful Feedback Labels

Retrieval-signal miner currently benefits from:

```text
wrong_domain
stale
irrelevant
bad_source
incorrect
not_useful
```

Evidence-state miner currently benefits from:

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

Use the best-fitting label. The label quality matters because this is candidate mining, not direct learning.

## Suggested Real Hermes Test

Run a realistic working session that includes:

- normal ask/answer cycles;
- stale/current correction cases;
- near-topic wrong-domain distractors;
- broad policy or generic note distractors;
- sensitive lookup questions where exact evidence should be required;
- at least a few feedback events linked to specific ask operation IDs.

The log does not need to be huge for the first real test. A useful first target is:

```text
20-50 ask events
5-15 linked feedback events
```

More is better if it stays realistic.

## Acceptance Criteria

The run is successful if:

- `selector_candidate_pipeline_from_log.py` exits with code `0`;
- the top-level JSON has `"ok": true`;
- `required_summary.log_exists` is true;
- `required_summary.retrieval_mining_ok` is true;
- `required_summary.evidence_mining_ok` is true;
- `required_summary.promotion_readiness_ok` is true;
- `required_summary.semantic_memory_ok` is true;
- `required_summary.architecture_gate_ok` is true.

Candidate count can be zero for one family if no relevant failures happened. That is acceptable.

## What To Report Back

Please write a Markdown report and, if possible, a JSON summary containing:

- source outcome log path;
- number of ask events;
- number of feedback events;
- number of linked feedback events;
- whether any required fields were missing;
- command run;
- top-level pipeline report path;
- retrieval candidate artifact path;
- evidence candidate artifact path;
- promotion-readiness artifact path;
- semantic-memory artifact path;
- architecture gate report path;
- candidate counts;
- candidate terms proposed;
- readiness counts for `ready`, `hold`, `reject`, and `held_out`;
- semantic cluster counts for `semantic_ready`, `semantic_hold`, `reject`, and `held_out`;
- whether the candidates look synthetic, too broad, or plausibly useful;
- any failures, stack traces, or missing dependency issues.

Do not promote mined candidates into `config.yaml`.

## Known Baseline

Before this handover, the selector session validated the synthetic memory contract log with:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log ..\experiments\memory_outcome_contract_workflow.jsonl
```

Result:

```text
PASS
retrieval candidate sections: 1
evidence candidate sections: 2
architecture gate: PASS
```

This proves the plumbing works. The next question is whether real Hermes logs produce candidates worth studying.

## Promotion Readiness Layer

The pipeline now includes:

```text
eval/candidate_promotion_readiness.py
```

This report is advisory only. Hermes should treat:

- `ready` as worth discussing for promotion;
- `hold` as requiring more cross-session evidence;
- `reject` as not worth promoting;
- `held_out` as evidence that must remain blocked from promotion.

Do not edit `config.yaml` automatically from a readiness report.

## Semantic Candidate Memory Layer

The pipeline now also includes:

```text
eval/candidate_semantic_memory.py
```

This layer groups compatible candidate terms into semantic clusters. It uses the fast hash embedding backend by default, and can be run separately with the configured embedding backend for deeper Gemma-based analysis:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\candidate_semantic_memory.py --readiness PATH_TO_PROMOTION_READINESS.json --embedding-backend config
```

The semantic-memory report is also advisory only. Treat `semantic_ready` as a cluster worth reviewing, not as approval to edit runtime config.

## Follow-Up From First Hermes Run

Hermes ran this test once and reported two auxiliary-tooling bugs:

- missing claim-scope candidate files could block `claim_scope_promotion_gate.py`;
- retrieval-signal mining could propose redundant broad-generic markers already covered by substring matching.

Both are fixed in the selector session:

- missing claim-scope candidate files now use a no-op candidate artifact;
- `retrieval_signal_miner_regression.py` verifies redundant broad-policy markers are not mined;
- the retrieval-signal promotion gate now requires that miner regression.

After the fixes, the Hermes real-log pipeline was rerun and passed:

```text
retrieval candidate sections: 1
evidence candidate sections: 1
architecture gate: PASS
```

## Follow-Up From Real Ask + Feedback Run

Hermes then tested a log built from real ask events plus realistic linked feedback.

Result:

```text
PASS
retrieval candidate sections: 1
evidence candidate sections: 1
architecture gate: PASS
```

Useful finding:

- `report_template_note` was mined as a plausible broad-generic source marker.
- `drink`, `prefer`, `project`, and `working` were mined as plausible exact-evidence/sensitive lookup markers.
- `does` was mined as noise.

The selector session fixed the noise case:

- `eval/mine_evidence_state_candidates.py` now filters auxiliary/modal terms such as `does`, `have`, `would`, `could`, `will`, and `must`.
- `eval/evidence_state_miner_regression.py` covers this behavior.
- `eval/evidence_state_promotion_gate.py` now requires the evidence miner regression.

After the fix, the same Hermes log mined:

```text
drink, prefer, project, working
```

and no longer mined:

```text
does
```

## Follow-Up From Live Linked-Feedback Run

Hermes then ran a live memory-server session against `localhost:8765` and produced real linked feedback.

Result:

```text
PASS
retrieval candidate sections: 0
evidence candidate sections: 1
architecture gate: PASS
```

The evidence miner initially proposed:

```text
configuration, drink, exact, live, morning, server
```

The selector session judged `live` too broad as a raw standalone config term, so the miner now holds out ambiguous location/action terms:

```text
live, lives, located, location
```

Held-out terms remain visible in reports under:

```text
support.held_out_sensitive_lookup
```

After this change, the live log mined:

```text
configuration, drink, exact, morning, server
```

and held out:

```text
live
```

## Important Caution

Candidate artifacts are proposals, not accepted policy.

The selector session will decide later whether any real mined candidates should be promoted, held for more evidence, rejected as too broad, or used to improve the miners.
