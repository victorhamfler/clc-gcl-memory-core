# Hermes Day 2 Shadow Run Handover

Date: 2026-05-21

This handover is for the Hermes agent. Day 1 is promoted cleanly at 42/42. The next stage is a Day 2 long-condition policy-shadow run that keeps all Day 1 boundaries and adds paraphrase, multi-intent, distractor, correction-pressure, and evidence-stability checks.

## Current GitHub State

Pull the latest repository before running:

```powershell
git pull origin main
```

The expected latest commit should include:

- `aed2ac6 Record Hermes Day 1 promotion`
- `f789fd6 Respect broad policy answer requests`
- `9a6ad28 Guard selector policy filename queries`
- `ac4c52b Guard memory answer source selection`

## New Repo-Owned Harness

Run:

```powershell
python eval/hermes_policy_shadow_run_day2.py --base-url http://127.0.0.1:8765
```

The script uses a timestamped namespace by default, so repeated runs should not contaminate each other.

Optional fixed namespace:

```powershell
python eval/hermes_policy_shadow_run_day2.py --base-url http://127.0.0.1:8765 --namespace hermes_policy_shadow_day2_manual
```

Optional faster run without local baselines:

```powershell
python eval/hermes_policy_shadow_run_day2.py --base-url http://127.0.0.1:8765 --skip-baselines
```

## Outputs

The harness writes:

- `experiments/hermes_policy_shadow_day2_results.json`
- `experiments/hermes_policy_shadow_day2_report.md`

Please also send Codex the terminal summary and the Markdown report.

## What Day 2 Tests

Day 2 carries forward the Day 1 boundaries:

- GitHub upload policy
- GitHub upload report filename
- Calendar change policy
- Broad/general policy note
- Unrelated user/project/tool facts

It adds harder pressure:

- paraphrase queries using terms such as `repo publish`, `upload artifact`, `markdown name`, `meeting edit`, `event reschedule`, and `approval log`
- multi-intent queries that should preserve two relevant memories in the answer evidence
- near-topic distractors about reports, GitHub issues, calendars, approvals, filenames, and repo drafts
- repeated corrections to unrelated and near-topic memories
- `/ask` answer evidence checks, not just top-1 retrieval checks

## Pass Criteria

The run is clean only if:

- all local baselines pass
- all policy queries pass in all three sessions
- all unrelated queries pass in all three sessions
- no unrelated query leaks policy memories into top retrieval or answer evidence
- multi-intent queries keep all expected memories in top evidence
- answer text contains required target facts and avoids forbidden source text

## If It Fails

Do not edit core code in the Hermes copy unless specifically asked.

If Day 2 fails, report:

- failing case id
- query
- expected refs
- retrieval top refs
- answer evidence refs
- answer text
- failure labels
- whether the failure appeared in morning, middle, end-of-day, or all sessions

The selector/memory sessions will then decide whether the failure belongs to:

- selector scoring/config
- resolver evidence ordering
- answer snippet selection
- live-server/session behavior
- test expectation that is too strict

## Expected Value

Day 2 is meant to find the next boundary after Day 1 promotion. A clean Day 2 would support moving toward a multi-day continuous working-condition test. A failure is also useful if it reveals a stable class of edge case that can be converted into a smaller official regression.

