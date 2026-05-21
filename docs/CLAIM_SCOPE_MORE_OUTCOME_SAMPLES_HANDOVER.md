# Claim Scope More Outcome Samples Handover

Date: 2026-05-20

This handover is for the memory-program session. The selector session validated the first mined claim-scope alias candidates and made one conservative selector-side promotion.

## Selector-Side Result

The selector session promoted only this candidate into permanent claim-scope config:

```yaml
backend_port: backend,port,8765
```

This was added in both:

```text
core/pipeline.py
config.yaml
```

Reason: the A/B validation showed that `backend_port` safely improved the compact backend-port memory from a claim-scope score of `0.75` to `1.0` without pulling unrelated status or filename memories upward.

## Current Validation Report

Selector-side validation file:

```text
../experiments/claim_scope_candidate_ab_eval_report.md
```

Validation script:

```text
eval/claim_scope_candidate_ab_eval.py
```

Current result:

- Overall eval passed.
- Conservative slots tested: `backend_port`, `filename`, `method`.
- Risk-probe slot tested: `policy`.
- `backend_port` is now promoted.
- `policy` was detected as risky and should not be promoted yet.

Key result table:

```text
method_vs_filename: baseline margin 1, conservative margin 1
filename_vs_method: baseline margin 2, conservative margin 2
backend_port_numeric_alias: baseline target claim-scope 1.0 after promotion
policy_noise_probe: broad policy overlay raised a distractor claim-scope score by 0.333333
```

## What Should Not Be Promoted Yet

Do not promote the mined `policy` aliases yet:

```text
wants, uploads, explicitly, requested, conversation
```

The selector-side risk probe showed these terms can raise an unrelated GitHub-upload memory for a calendar-policy query. The rank did not flip, but the claim-scope lift is enough to mark it as a bad general alias set.

Also do not promote broad `mechanism` aliases yet:

```text
domain, maintains, geometry, anchor, drift, curvature, stability, helps
```

These may be useful for CSD/G-CL technical memory, but the slot is too broad to add from the current small sample.

## Requested Next Work For Memory-Program Session

Please collect more linked outcome samples and rerun the alias miner. The selector session needs more evidence before promoting broader slots.

Focus on these query families:

1. Method versus filename
   - Example method queries:
     - `What radar method should Victor use?`
     - `What tool should be used for weather radar checks?`
   - Example filename queries:
     - `What radar report filename should be used?`
     - `What file name should the radar report have?`
   - Goal: determine whether `filename` should become a permanent slot, and whether `method` needs more aliases beyond the current default.

2. Status versus codename
   - Example status queries:
     - `What is the Hermes memory project status?`
     - `Is the selector calibration ready or blocked?`
   - Example codename queries:
     - `What is the current Hermes project codename?`
   - Goal: test whether the current `status` and `codename` aliases are enough, or whether additional aliases help without cross-topic leakage.

3. Backend port
   - Example queries:
     - `What backend port should the memory API use?`
     - `Which port should Hermes use for the memory server?`
   - Goal: confirm the promoted `backend_port` slot remains useful across more examples.

4. Mechanism and CSD/G-CL technical memory
   - Example queries:
     - `What does G-CL maintain?`
     - `What does CSD help detect?`
     - `What mechanism handles contradiction pressure?`
   - Goal: split broad `mechanism` into narrower slots if possible.

5. Policy, but with cleaner labels
   - Example policy queries:
     - `What is the GitHub upload policy?`
     - `What is the calendar change policy?`
     - `What should happen before uploading to GitHub?`
   - Goal: determine whether `policy` needs domain-specific slots such as `github_upload_policy` and `calendar_policy` instead of one broad `policy` slot.

## Sample Requirements

Please generate a new linked outcome log with at least:

- 30 ask events.
- 30 linked feedback events.
- Both positive and negative feedback.
- At least 5 near-topic distractor cases.

For each query family, include:

- A target memory that should answer the query.
- A same-domain distractor memory that should not answer it.
- When relevant, a stale/current correction pair.

The most useful labels are:

```text
useful
stale
wrong_domain
incorrect
missing_source
```

Please make sure feedback rows preserve:

```text
linked_operation_id
memory_id
query
rank
retrieval_score
label
rating
notes
```

## Requested Output Files

After generating the new samples, please rerun the alias miner and produce:

```text
../experiments/claim_scope_alias_candidates_v2.json
../experiments/claim_scope_alias_candidates_v2_report.md
```

If the current miner only writes the original filenames, either add CLI output options or copy the files to the `_v2` names after the run.

Please also write a handover back to the selector session:

```text
docs/CLAIM_SCOPE_ALIAS_CANDIDATES_V2_HANDOVER.md
```

The handover should include:

- Event counts.
- Query families covered.
- Top candidate slots.
- Which candidates have positive and negative evidence.
- Which aliases should be avoided.
- Any retrieval failures observed during the sample run.

## Selector Session Will Do Next

After receiving the V2 candidate file, the selector session should:

- Run `eval/claim_scope_candidate_ab_eval.py` against the V2 candidate JSON.
- Add new A/B cases for any new query family.
- Promote only candidates that improve or preserve target margins and do not raise near-topic distractor claim-scope scores by `0.25` or more.

## Coordination Note

Please do not edit selector-owned files directly unless the user explicitly asks you to do that in the memory-program session.

Selector-owned files include:

```text
core/pipeline.py
core/runtime.py
config.yaml
eval/claim_scope_candidate_ab_eval.py
eval/claim_scope_config_regression.py
```

The memory-program session should own log generation, feedback instrumentation, and candidate mining. Bring generated candidate JSON/report files back to the selector session for validation and promotion.

