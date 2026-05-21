# Claim Scope Config Handover

## Purpose

This handover is for the memory-program session that owns the broader agent memory layer. The selector session has improved the selector-side weakness where `claim_scope_score` depended on hard-coded topic vocabulary in `core/pipeline.py`.

The selector now supports configurable claim-scope aliases through a top-level `claim_scope:` section in `config.yaml`. The next useful collaboration is for the memory-program session to mine real memory outcomes and propose better claim-scope aliases from actual agent usage.

## Current Selector-Side Status

The selector session changed the claim-scope mechanism so it can be configured without editing selector code.

Changed files in the selector module:

- `core/pipeline.py`
  - Added default claim-scope stopwords, slot aliases, and excluded terms.
  - Added `claim_scope_config` to `MemoryPipeline`.
  - Replaced the embedded drink/pizza/radar/status/codename branches inside `_claim_scope_affinity` with configurable slot alias matching.

- `core/runtime.py`
  - Passes `config.get("claim_scope")` into `MemoryPipeline`.
  - Exposes normalized claim-scope config in the runtime config view.

- `config.yaml`
  - Adds:

```yaml
claim_scope:
  stopwords: about,check,checks,current,currently,does,for,from,help,helps,latest,prefer,prefers,preference,should,that,the,use,what,when,where,which,who,with,victor,hermes,project
  slot_aliases:
    drink: drink,water,sparkling,espresso,tea,coffee,beverage
    pizza: pizza,cheese,mushroom,pepperoni
    method: method,tool,url,accuweather,radar,checks
    codename: codename,cedar,alpha
    status: status,stable,blocked,ready
  excluded_terms:
    method: filename
```

- `eval/claim_scope_config_regression.py`
  - Proves a new `calendar policy` scope can be configured without changing selector code.
  - The configured calendar-policy memory ranked above a near-topic calendar-color correction.

## Test Results From Selector Session

These selector-side tests passed after the change:

- `claim_scope_config_regression.py`
  - Passed.
  - Calendar policy target ranked #1.
  - Near-topic calendar color correction ranked lower.

- `selector_near_topic_distractor_eval.py --embedding-backend hash --top-k 10`
  - 6/6 aligned.

- `agent_workflow_selector_integration_eval.py --embedding-backend hash --top-k 10`
  - 7/7 aligned.

- `selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 128 --seed 20260520 --top-k 10`
  - 128/128 aligned.

- `selector_runtime_config_eval.py`
  - Passed.

- `correction_chain_retrieval_regression.py`
  - Passed.

## What Is Still Not Solved

The hard-coded vocabulary weakness is improved, but not fully solved.

The selector no longer requires code changes for new claim scopes. However, the aliases are still manually written in config. The next technological step is to make the memory-program layer propose, learn, or extract those aliases from real memory outcomes.

The selector session should continue owning:

- `core/pipeline.py`
- selector scoring behavior
- selector/runtime config handling
- selector evals and calibration tests

The memory-program session should continue owning:

- memory outcome logging
- real agent workflow traces
- extracting candidate labels or aliases from memory use
- deciding when an alias candidate is supported by enough evidence

## Requested Work For The Memory-Program Session

Please build a small outcome-log analysis step that proposes claim-scope alias candidates from real agent memory use.

Recommended output file:

```text
experiments/claim_scope_alias_candidates.json
```

Recommended schema:

```json
{
  "generated_at": "ISO-8601 timestamp",
  "source_logs": ["logs/memory_outcomes.jsonl"],
  "candidate_count": 0,
  "candidates": [
    {
      "slot": "policy",
      "aliases": ["manual", "approval", "schedule", "changes"],
      "excluded_terms": ["color"],
      "supporting_queries": [
        "What calendar policy should Hermes use?"
      ],
      "supporting_memory_ids": [],
      "positive_count": 0,
      "negative_count": 0,
      "confidence": 0.0,
      "notes": "Short reason this slot is useful."
    }
  ]
}
```

If the memory program already has a better report format, use that format too, but please also produce a compact JSON candidate file because the selector session can consume it more easily.

## Suggested Extraction Method

Start simple and make the evidence visible.

1. Read outcome events where a retrieval, ask, correction, or memory selection has a clear query and accepted/rejected memories.

2. Extract likely query slots from nouns or key phrases in the user query:
   - Examples: `policy`, `status`, `codename`, `method`, `preference`, `filename`, `owner`, `deadline`, `decision`, `constraint`.

3. Collect alias terms from memories that were useful for the query:
   - Memory text.
   - Source filename stem.
   - Correction text.
   - Accepted answer text, if available.

4. Collect excluded terms from near-topic rejected memories:
   - Example: query slot `policy`, rejected memory topic `color`.
   - Example: query slot `method`, rejected memory topic `filename`.

5. Score candidate aliases conservatively:
   - More support if the same slot appears across repeated successful retrievals.
   - Less support if aliases appear often in rejected memories.
   - Prefer compact alias lists over broad topic bags.

6. Write a human-readable report with:
   - Top proposed slots.
   - Evidence examples.
   - Risky aliases to avoid.
   - Cases where no reliable alias should be added.

## Good First Test

Use the memory-program logs to produce 5 to 20 candidate claim-scope slots, then create a small A/B report:

- Baseline: current selector config.
- Variant: current selector config plus proposed aliases.

Measure:

- Did accepted/desired memories rank higher?
- Did near-topic rejected memories rank lower?
- Did correction chains still escalate when they are truly same-topic?
- Did false stale pressure increase?

Important: do not tune only for one synthetic case. The value comes from repeated real agent usage.

## Coordination Rule

Please do not edit selector-owned files directly unless the user explicitly asks you to do so in that session.

Instead:

- Generate candidate alias JSON/report files.
- Add a handover note explaining the evidence.
- Tell the user to bring the candidate file/report back to the selector session.

The selector session can then decide whether to:

- Merge candidates into `config.yaml`.
- Add an importer for alias candidate JSON.
- Add new regressions for the strongest discovered scopes.

## Success Criteria

The next stage is successful if the memory-program session can produce candidate aliases that improve at least one real retrieval/correction scenario without increasing false positives in near-topic distractor tests.

The most valuable candidates are not broad topic labels. They are narrow claim slots that prevent the selector from confusing similar memories, such as:

- status versus codename
- method versus filename
- policy versus color
- decision versus discussion
- deadline versus owner
- preference versus project work

