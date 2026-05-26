# Hermes Handover: EvidenceContextFeatures Real-Log Collection

## Goal

Collect independent real Hermes logs for the selector neural-symbolic roadmap.

The selector now exports a stable feature vector at:

```text
adaptive_behavior_shadow.diagnostics.evidence_context_features
```

Local generated challenge logs proved the learned residual path can beat the symbolic shadow when enough symbolic-error cases exist:

```text
symbolic baseline:      0.745763
hybrid residual model:  0.915254
delta:                 +0.169491
```

That result is promising but not promotion-ready because the hard cases were generated locally. Hermes should now collect independent real logs so Codex can rerun the same hybrid residual test as a true holdout.

## Pull Latest Code

From the Hermes WSL clone:

```bash
git pull origin main
```

Then run the selector gate:

```bash
cd <repo>/clc_gcl_memory_core
python eval/selector_architecture_gate.py
```

Expected required gate keys include:

```text
adaptive_behavior_feature_scorer_ok: true
adaptive_behavior_feature_scorer_hybrid_ok: true
adaptive_behavior_feature_challenge_ok: true
evidence_context_regression_ok: true
evidence_context_selector_runtime_ok: true
```

## Required Logging Flags

Every Hermes ask used for this test must request and log the adaptive behavior shadow:

```json
{
  "include_selector_snapshot": true,
  "include_resolver_shadow": true,
  "include_adaptive_behavior_shadow": true,
  "log_adaptive_behavior_shadow": true
}
```

The resulting ask event must contain:

```text
payload.adaptive_behavior_shadow.diagnostics.evidence_context_features
```

or, if Hermes stores the shadow under the response:

```text
payload.response.adaptive_behavior_shadow.diagnostics.evidence_context_features
```

## What To Test

Create real agent sessions with answer feedback labels. The goal is not only normal questions. We need hard cases where the symbolic shadow may be wrong.

Use at least 80 ask/feedback pairs if possible. More is better.

Include these families:

1. Supported evidence
   - correct answers with low retrieval score but good selected evidence;
   - correct answers with one selected evidence row and weak raw retrieval context;
   - correct answers involving bridge/synthesis wording.

2. Missing support
   - no evidence and correct refusal;
   - weak selected evidence that should still refuse;
   - private/sensitive lookup queries where selected evidence exists but should not be enough.

3. Stale conflict
   - old/previous/stale queries where stale behavior is actually useful;
   - current/latest/corrected queries where stale behavior should stay uncertain;
   - cases where stale context appears incidentally but should not drive the answer.

4. Wrong scope
   - GitHub/upload/approval/sign-off questions;
   - selected evidence from a nearby but wrong policy scope;
   - no selected evidence but a scope-sensitive query.

5. OGCF bridge warning
   - bridge warning useful;
   - bridge warning noise;
   - ordinary bridge/location/meeting queries that should not be treated as conceptual OGCF bridge cases.

Use answer feedback labels compatible with the existing calibration scripts:

```text
answer_correct
answer_good_citation
answer_bad_citation
answer_missing_support
answer_stale
answer_wrong_scope
answer_overconfident
answer_conflict_not_disclosed
answer_bridge_warning_useful
answer_bridge_warning_noise
```

## Required Output Files

Write the Hermes outcome log to:

```text
~/experiments_hermes/hermes_feature_residual_real_outcomes.jsonl
```

Also write a Markdown report:

```text
~/experiments_hermes/HERMES_FEATURE_RESIDUAL_REAL_LOG_REPORT.md
```

The report should include:

- total ask events;
- total answer feedback events;
- count of ask events with `evidence_context_features`;
- label distribution;
- behavior-family distribution;
- symbolic match rate from calibration;
- learned global scorer result;
- learned hybrid scorer result;
- examples where symbolic was wrong and hybrid was right;
- examples where hybrid would be harmful;
- whether the data is independent real Hermes behavior or generated/scripted.

## Evaluation Commands

After collecting the log, run:

```bash
python eval/adaptive_behavior_shadow_real_log_calibration.py \
  --log ~/experiments_hermes/hermes_feature_residual_real_outcomes.jsonl \
  --out-json ~/experiments_hermes/hermes_feature_residual_calibration_results.json \
  --out-md ~/experiments_hermes/HERMES_FEATURE_RESIDUAL_CALIBRATION_REPORT.md
```

Then run the global scorer:

```bash
python eval/adaptive_behavior_feature_scorer_eval.py \
  --log ~/experiments_hermes/hermes_feature_residual_real_outcomes.jsonl \
  --out-json ~/experiments_hermes/hermes_feature_residual_global_scorer_results.json \
  --out-md ~/experiments_hermes/HERMES_FEATURE_RESIDUAL_GLOBAL_SCORER_REPORT.md
```

Then run the hybrid residual scorer:

```bash
python eval/adaptive_behavior_feature_scorer_hybrid_eval.py \
  --log ~/experiments_hermes/hermes_feature_residual_real_outcomes.jsonl \
  --out-json ~/experiments_hermes/hermes_feature_residual_hybrid_scorer_results.json \
  --out-md ~/experiments_hermes/HERMES_FEATURE_RESIDUAL_HYBRID_SCORER_REPORT.md
```

## Success Criteria

This is still report-only. Do not enable learned runtime control.

The result becomes a serious promotion candidate only if:

- the log is independent real Hermes behavior;
- at least 80 ask/feedback pairs exist;
- every evaluated ask has `evidence_context_features`;
- the hybrid scorer beats symbolic on holdout;
- harmful overrides are zero or clearly lower than helpful overrides;
- the result repeats on a second independent log.

## What To Send Back

Send Codex these files:

```text
~/experiments_hermes/hermes_feature_residual_real_outcomes.jsonl
~/experiments_hermes/HERMES_FEATURE_RESIDUAL_REAL_LOG_REPORT.md
~/experiments_hermes/hermes_feature_residual_calibration_results.json
~/experiments_hermes/HERMES_FEATURE_RESIDUAL_CALIBRATION_REPORT.md
~/experiments_hermes/hermes_feature_residual_global_scorer_results.json
~/experiments_hermes/HERMES_FEATURE_RESIDUAL_GLOBAL_SCORER_REPORT.md
~/experiments_hermes/hermes_feature_residual_hybrid_scorer_results.json
~/experiments_hermes/HERMES_FEATURE_RESIDUAL_HYBRID_SCORER_REPORT.md
```

Codex will compare the real Hermes result against the local generated challenge result and decide whether the learned residual controller should remain research-only or move toward a guarded promotion profile.
