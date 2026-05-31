# Hermes Handover: Adaptive Residual Shadow External Log

Date: 2026-05-31

## Purpose

Collect the first independent Hermes/agent residual-shadow log for the neural-symbolic residual controller.

Codex now has three local residual-shadow holdouts passing:

```text
usable residual logs: 3
ask count:            96
decision count:       351
would overrides:      29
helpful:              29
harmful:              0
neutral-wrong:        0
```

Promotion is still blocked by design:

```text
blocked_reason: external_or_agent_residual_log_required
```

Hermes should create an independent real/agent working-condition residual log so Codex can run the same linked-feedback evaluation and readiness gate on non-local evidence.

## Repository Setup

From the Hermes WSL clone:

```bash
git pull origin main
cd clc_gcl_memory_core
```

Run the full architecture gate before testing:

```bash
python eval/selector_architecture_gate.py
```

Expected important checks:

```text
adaptive_residual_shadow_runtime_ok: true
adaptive_residual_shadow_logged_eval_ok: true
adaptive_residual_shadow_multi_log_eval_ok: true
adaptive_residual_shadow_suppressor_ok: true
adaptive_residual_shadow_term_miner_ok: true
adaptive_residual_shadow_term_patch_guard_ok: true
adaptive_residual_shadow_promotion_readiness_ok: true
```

If the gate fails, stop and report the failing command, stdout/stderr, and generated report path.

## Required Ask Flags

Every ask used for this external residual log must include:

```json
{
  "include_selector_snapshot": true,
  "include_resolver_shadow": true,
  "include_adaptive_residual_shadow": true,
  "log_adaptive_residual_shadow": true
}
```

The response or logged ask event must contain:

```text
adaptive_residual_shadow.schema == adaptive_residual_shadow/v1
adaptive_residual_shadow.report_only == true
adaptive_residual_shadow.mutates_answer == false
adaptive_residual_shadow.mutates_selector_policy == false
adaptive_residual_shadow.mutates_memory == false
adaptive_residual_shadow.mutates_config == false
```

The residual shadow must not change the answer. It is evidence collection only.

## Required Feedback

Every ask must receive linked answer feedback using the same `operation_id`.

Use answer labels from this set:

```text
answer_correct
answer_good_citation
answer_bad_citation
answer_missing_support
answer_overconfident
answer_stale
answer_conflict_not_disclosed
answer_wrong_scope
answer_bridge_warning_useful
answer_bridge_warning_noise
```

Also add memory-level feedback for returned evidence rows when possible. Include selected memory ids, rank, retrieval score, and short notes.

## Test Design

Create at least 60 ask/feedback cycles. Minimum acceptable run: 40 cycles.

Use natural agent work, not only scripted challenge prompts. Mix routine memory use with hard boundary cases.

Include these scenario families:

1. Supported evidence
   - current roadmap facts;
   - selector safety rules;
   - config/promotion policy;
   - canonical memory / duplicate handling;
   - feedback labels: `answer_correct`, `answer_good_citation`.

2. Missing support
   - unsupported claims about production promotion;
   - private/secrets/deployment keys/tokens;
   - claims not actually stored in memory;
   - feedback labels: `answer_missing_support`, `answer_overconfident`.

3. Stale/current conflict
   - old policy vs current correction;
   - previous roadmap vs latest roadmap;
   - stale backend/upload rules;
   - feedback labels: `answer_stale`, `answer_conflict_not_disclosed`, `answer_correct`.

4. Wrong scope
   - GitHub upload permission vs calendar approval;
   - broad policy notes vs explicit upload approval;
   - profile preference vs repository publishing policy;
   - ordinary namespace/profile lookup pressure;
   - feedback label: `answer_wrong_scope`.

5. OGCF bridge useful/noise
   - real cross-domain synthesis where bridge warnings are useful;
   - ordinary meeting bridge/calendar/location questions where bridge warning is noise;
   - feedback labels: `answer_bridge_warning_useful`, `answer_bridge_warning_noise`.

## Output Files

Write the main outcome log to:

```text
~/experiments_hermes/hermes_adaptive_residual_shadow_external_outcomes.jsonl
```

Write a report to:

```text
~/experiments_hermes/HERMES_ADAPTIVE_RESIDUAL_SHADOW_EXTERNAL_LOG_REPORT.md
```

Also write a JSON summary to:

```text
~/experiments_hermes/hermes_adaptive_residual_shadow_external_summary.json
```

## Required Report Contents

The report should include:

- ask count;
- answer feedback count;
- memory feedback count;
- count of ask events containing `adaptive_residual_shadow/v1`;
- count of residual decisions;
- count of `would_override`;
- harmful/helpful/neutral-wrong estimate if Hermes runs the local evaluator;
- label distribution;
- any errors or missing linked feedback;
- exact command lines used;
- git commit hash tested.

## Optional Local Evaluation On Hermes

If the eval scripts run in Hermes WSL, copy or symlink the outcome log into the repo's `../experiments` folder using a filename containing `hermes`:

```bash
mkdir -p ../experiments
cp ~/experiments_hermes/hermes_adaptive_residual_shadow_external_outcomes.jsonl \
  ../experiments/hermes_adaptive_residual_shadow_external_outcomes.jsonl
```

Then run:

```bash
python eval/adaptive_residual_shadow_logged_eval.py \
  --log ../experiments/hermes_adaptive_residual_shadow_external_outcomes.jsonl \
  --out-json ../experiments/hermes_adaptive_residual_shadow_external_logged_eval_results.json \
  --out-md ../experiments/hermes_adaptive_residual_shadow_external_logged_eval_report.md

python eval/adaptive_residual_shadow_multi_log_eval.py --min-logs 4
python eval/adaptive_residual_shadow_promotion_readiness.py
```

Expected target if the external log is clean:

```text
harmful overrides:       0
neutral-wrong overrides: 0
promotion readiness:     may still be false, but has_external_or_agent_log should become true
```

If harmful or neutral-wrong overrides appear, do not hide them. Report the exact examples. Those are the most valuable development data.

## Files To Return To Codex

Return or make available:

```text
~/experiments_hermes/hermes_adaptive_residual_shadow_external_outcomes.jsonl
~/experiments_hermes/HERMES_ADAPTIVE_RESIDUAL_SHADOW_EXTERNAL_LOG_REPORT.md
~/experiments_hermes/hermes_adaptive_residual_shadow_external_summary.json
```

If local eval was run, also return:

```text
../experiments/hermes_adaptive_residual_shadow_external_logged_eval_results.json
../experiments/hermes_adaptive_residual_shadow_external_logged_eval_report.md
../experiments/adaptive_residual_shadow_multi_log_eval_results.json
../experiments/adaptive_residual_shadow_promotion_readiness_results.json
```

## Success Criteria

The external log is useful if:

```text
ask/feedback pairs >= 40
adaptive_residual_shadow present on every ask
linked answer feedback present for every ask
harmful overrides == 0
neutral-wrong overrides == 0
helpful overrides > 0
```

If any criterion fails, the log is still useful, but it should be treated as a development failure case and returned with full examples.
