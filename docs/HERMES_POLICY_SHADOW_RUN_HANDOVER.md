# Hermes Handover: Policy-Split Shadow Run

## Mission

Run a Hermes shadow test of the current selector architecture after the promotion of the live answer-type policy rules.

The specific question to test is:

> Can the memory selector keep narrow operational policy memories separate from broad policy notes and filename memories during continued agent work?

This test should focus on the selector module in this repository. The broader memory-program session should continue owning unrelated memory-program changes. If Hermes finds a bug in shared endpoints or the wider memory system, report it separately so Victor can decide whether the selector session or the memory-program session should implement the fix.

## What Changed In This Version

The selector now has:

- configurable nested `claim_scope` rules,
- configurable `answer_type` rules,
- live `github_upload_policy` and `calendar_change_policy` answer-type rules,
- a policy split regression,
- a hard policy shadow smoke harness,
- promotion gate checks that include policy split, outcome replay, candidate A/B, config parsing, and selector guards.

The live policy rules should separate these cases:

- GitHub upload policy vs GitHub upload filename,
- GitHub upload policy vs calendar change policy,
- calendar change policy vs broad policy notes,
- calendar event/change questions vs GitHub upload memories.

## Setup

Use the latest GitHub version:

```bash
git clone https://github.com/victorhamfler/clc-gcl-memory-core.git
cd clc-gcl-memory-core
```

If the repo already exists:

```bash
cd clc-gcl-memory-core
git pull origin main
```

Use the normal Python environment for this project. On Victor's Windows machine the environment may be:

```powershell
..\.venv-torch\Scripts\python.exe
```

On WSL, use the Python environment Hermes normally uses for this repo.

Do not commit generated DBs, logs, reports, caches, or local experiment outputs unless Victor explicitly asks.

## Day 0 Required Baseline

Run these from the repo root:

```bash
python eval/config_nested_parser_regression.py
python eval/answer_type_policy_split_probe.py
python eval/hermes_policy_shadow_smoke.py
python eval/claim_scope_promotion_gate.py --include-selector-guards --candidates test_corpora/claim_scope_alias_candidates_policy_split_v1.json
```

Expected baseline:

```text
config_nested_parser_regression: ok true
answer_type_policy_split_probe: ok true
hermes_policy_shadow_smoke: ok true
claim_scope_promotion_gate: ok true
```

If Hermes has access to Victor's local `../experiments/claim_scope_alias_candidates_v12.json`, it can also rerun the gate with that larger mined candidate file. The checked-in `test_corpora/claim_scope_alias_candidates_policy_split_v1.json` fixture is the reproducible fresh-clone baseline.

If any baseline fails, stop and return:

- console output,
- generated JSON report,
- generated Markdown report,
- current `config.yaml`,
- `git status --short`.

## Optional Existing Hermes Server Smoke

If Hermes already has a memory-core server running:

```bash
python eval/hermes_policy_shadow_smoke.py --base-url http://127.0.0.1:8765 --namespace hermes_policy_shadow_live_probe
```

This version teaches the policy boundary fixtures into the selected namespace on that server, so use a disposable namespace.

## Multi-Day Shadow Protocol

Run the shadow test for at least 3 days. Five days is better.

Use these namespaces:

```text
hermes_policy_shadow_day1
hermes_policy_shadow_day2
hermes_policy_shadow_day3
hermes_policy_shadow_continuous
```

Each day, create at least three sessions:

- morning,
- middle,
- end-of-day.

Each session should include:

- 3 to 5 clean teaches,
- 2 compatible updates,
- 2 direct corrections,
- 1 correction chain,
- 4 policy-boundary questions,
- 4 unrelated topic-switch questions,
- `/retrieve` for every policy-boundary question,
- `/ask` for every policy-boundary question,
- `/selector_explain` for at least 5 important questions per session.

## Required Policy Boundary Cases

Use varied wording, but include these exact classes:

1. GitHub upload policy:

```text
What GitHub upload policy should Hermes follow?
What should happen before uploading to GitHub?
Can Hermes upload to GitHub automatically?
```

2. GitHub filename distractor:

```text
What GitHub upload report filename should be used?
What file should the GitHub upload report use?
```

3. Calendar change policy:

```text
What calendar change policy should Hermes follow?
What should happen before changing calendar events?
Can Hermes change meetings automatically?
```

4. Broad policy distractor:

```text
Broad policy note: approvals should be documented.
General policy note: changes should be recorded.
```

## What To Record

For every policy-boundary query, save:

- query,
- namespace,
- `/retrieve` top 8 rows,
- `/ask` evidence,
- answer text,
- `claim_scope_score`,
- `answer_type_score`,
- source path,
- memory id,
- authority state,
- whether the top answer was correct,
- whether a broad policy note outranked a narrow policy memory,
- whether a filename memory outranked a policy memory,
- whether a GitHub memory outranked a calendar memory or the reverse.

For `/selector_explain`, save:

- decision,
- reason,
- confidence,
- nearest samples,
- diagnostics,
- retrieval rows if included.

## Failure Labels

Use these labels:

```text
policy_split_github_filename_wins
policy_split_broad_policy_wins
policy_split_cross_domain_github_calendar
policy_split_answer_type_missing
policy_split_claim_scope_leak
selector_false_aggressive
selector_false_protect
current_memory_missing
stale_memory_dominates
unrelated_memory_dominates
```

## Success Criteria

The run is considered successful if:

- `answer_type_policy_split_probe` stays green,
- `hermes_policy_shadow_smoke` stays green,
- the promotion gate stays green after collected outcomes are replayed,
- no broad policy note becomes top-1 for a narrow policy query,
- no filename memory becomes top-1 for a policy query,
- GitHub upload policy and calendar change policy do not cross-contaminate,
- negative answer-type violations remain `0`,
- negative claim-lift violations remain `0`.

## Final Report To Return

Write a Markdown report and a JSON summary under Hermes' experiment folder.

The Markdown report should include:

- commit SHA tested,
- environment details,
- dates covered,
- commands run,
- baseline results,
- number of teaches/corrections/asks/retrieves/selector explanations,
- pass/fail summary by failure label,
- 10 best successful boundary examples,
- all failures with full request/response,
- recommendation: promote, keep guarded, or revise.

The JSON summary should include machine-readable counters and the raw failure list.

Return those files to Victor/Codex for the next selector-stage development decision.
