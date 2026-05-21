# Claim Scope Alias Candidates V2 Handover

Date: 2026-05-20

This handover is for the selector-module session. The memory-program session generated a larger linked-feedback outcome sample and reran the claim-scope alias miner.

## Generated Files

```text
../experiments/claim_scope_alias_candidates_v2.json
../experiments/claim_scope_alias_candidates_v2_report.md
```

Source log:

```text
logs/memory_outcomes.jsonl
```

## Event Counts

The V2 batch appended 114 new events to the outcome log:

- Ask events: 36
- Linked feedback events: 66
- Selector explanation events: 12
- Explicit near-topic/distractor feedback rows: about 30
- Query families covered: 14

The full log used by the V2 miner now contains:

- Ask events: 54
- Feedback events: 83
- Linked feedback events: 83
- Candidate slots: 13

## Query Families Covered

- `method`
- `filename`
- `status`
- `codename`
- `backend_port`
- `backend_host`
- `mechanism_gcl`
- `mechanism_csd`
- `policy_github`
- `policy_calendar`
- `owner`
- `deadline`
- `decision`
- `near_topic`

## Stronger Candidates

These look most useful for selector-side A/B validation:

- `method`
  - aliases: `accuweather`, `weather`, `url`, `choice`, `radar_method`
  - excluded: `report`, `filename`, `accuweather_radar_report`
  - positive: 4
  - negative: 3
  - note: Good evidence for separating method/tool questions from filename/report memories.

- `status`
  - aliases: `longer`, `linked-feedback`, `testing`, `outcome`, `logging`
  - excluded: `codename`, `cedar`, `map`, `dashboard`, `color`
  - positive: 4
  - negative: 3
  - note: Useful for status versus codename, but review aliases like `outcome`/`logging` before general promotion.

- `backend_port`
  - aliases: `8765`
  - excluded: `host`, `remain`, `127`, `local`, `testing`
  - positive: 4
  - negative: 6
  - note: Confirms the selector-side `backend_port` promotion remains useful and should stay narrow.

- `codename`
  - aliases: `cedar`, `map`, `guardrails`, `enabled`
  - excluded: `status`
  - positive: 4
  - negative: 4
  - note: `cedar`, `map`, and `alpha`-style terms may be useful, but `guardrails`/`enabled` are project-state leakage.

- `deadline`
  - aliases: `friday`, `deadline_report`, `selector`, `due`
  - excluded: `note`, `owner`, `mina`, `owns`, `draft`
  - positive: 2
  - negative: 2
  - note: Promising new family, but sample is still small.

## Candidates Requiring Caution

- `policy`
  - positive: 5
  - negative: 4
  - aliases include both GitHub and calendar policy evidence.
  - avoid promoting broad aliases like `explicitly`, `conversation`, `confirmation`, `changing`.
  - recommendation: split into domain-specific slots such as `github_upload_policy` and `calendar_change_policy`.

- `mechanism`
  - positive: 5
  - negative: 3
  - aliases include broad CSD/G-CL technical terms.
  - recommendation: split into narrower `gcl_mechanism`, `csd_signal`, and `contradiction_mechanism` before promotion.

- `filename`
  - positive: 6
  - negative: 8
  - aliases include correct `accuweather_radar_report`, but also leaked deadline/report terms from deadline and CSD-report cases.
  - recommendation: selector A/B should test a narrow `radar_report_filename` slot instead of general `filename`.

- `general_claim`
  - broad and noisy.
  - recommendation: do not promote.

- `owner`
  - mixed with codename and report-owner cases.
  - recommendation: collect more clean owner-only examples before promotion.

## Aliases To Avoid For Now

Avoid broad terms that lifted distractors or mixed families:

```text
policy, confirmation, changing, conversation, discussion, automatic,
mechanism, domain, helps, selector, report, due, owner, note
```

Avoid promoting `policy` as one broad slot from the current evidence. The V2 data supports domain-specific policy slots better than a universal policy slot.

## Retrieval Failures Observed

The V2 sample intentionally included imperfect cases. Five answers missed expected terms:

- `backend_host`: host query did not reliably surface `127.0.0.1`.
- `owner`: project-belongs-to-Hermes query mixed with other ownership facts.
- `near_topic`: calendar color, CSD report owner, and backend badge color were noisy by design.

These failures are useful negative examples for the selector parser, but they should not be used as proof that a broad alias should be promoted.

## Recommended Selector-Session Next Step

Run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_candidate_ab_eval.py
```

using:

```text
../experiments/claim_scope_alias_candidates_v2.json
```

Recommended first A/B targets:

1. `method` versus `radar_report_filename`
2. `status` versus `codename`
3. narrow `backend_port`
4. split `github_upload_policy` and `calendar_change_policy`
5. split `gcl_mechanism` and `csd_signal`

Promote only candidates that improve target ranking without raising near-topic distractor claim-scope by `0.25` or more.
