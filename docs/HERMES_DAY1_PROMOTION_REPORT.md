# Hermes Day 1 Promotion Report

Date: 2026-05-21

## Status

The Day 1 Hermes policy-shadow test is clean on commit:

`f789fd6382824e584e4fbea27ec71012d2de5cf2`

Recommendation: **PROMOTE**

## Evidence

Hermes ran the latest GitHub version after these two coordinated fixes:

- `9a6ad28 Guard selector policy filename queries`
- `f789fd6 Respect broad policy answer requests`

Hermes live-server results:

- Day 0 baselines: 5/5 passed
- Day 1 policy boundary queries: 30/30 passed
- Day 1 unrelated queries: 12/12 passed
- Total live shadow result: 42/42 passed
- Sessions covered: morning, middle, end-of-day
- Unrelated policy leakage: 0

External Hermes artifacts:

- `C:\Users\victo\Documents\GitHub\experiments\hermes_policy_shadow_day1_results.json`
- `C:\Users\victo\Documents\GitHub\experiments\hermes_policy_shadow_day1_report.md`
- `C:\Users\victo\Documents\3030. Clean pass..txt`

## What Was Proven

The current architecture correctly separates these policy-adjacent memory types during retrieval and answer construction:

- GitHub upload policy
- GitHub upload report filename
- Calendar change policy
- Broad/general policy note
- Unrelated user/project/tool facts

The important result is not just top-1 retrieval. Hermes also verified that `/ask` used the correct answer evidence source, which was the main failure mode in the previous runs.

## Fixed Failure Modes

### GitHub Filename Versus Upload Policy

Before the fix, filename questions such as `What GitHub upload report filename should be used?` could rank `github_upload_policy` above `github_upload_filename`.

Resolution:

- Selector answer-type rules now support `query_excludes_any`.
- `github_upload_policy` opts out when a query asks for `filename`, `file`, or `report`.

### Calendar Policy Versus Broad Policy Note

Before the fix, calendar policy retrieval could rank correctly but `/ask` could still answer from `broad_policy_note`.

Resolution:

- Resolver evidence ordering now respects answer type, rank, selector signal, and specific-vs-broad evidence more strongly.

### Broad Policy Note Versus Calendar Policy

Before the fix, a broad policy query such as `General policy note: changes should be recorded.` could drift into calendar evidence because generic notes were penalized too aggressively.

Resolution:

- Resolver now detects explicit broad/general policy-note questions.
- Broad generic evidence remains penalized for specific questions, but not when the query explicitly asks for broad/general policy evidence.

## Current Promotion Boundary

Promote the Day 1 policy-shadow behavior as a guarded architecture milestone.

This does not mean the architecture is complete. It means the current selector plus resolver stack is stable enough to move from fixed Day 1 replay into longer, noisier, and more realistic agent-memory tests.

## Next Best Test Stage

Run a Day 2 long-condition shadow test with the latest GitHub commit. The goal is to test whether the promoted Day 1 behavior survives more realistic memory pressure.

Recommended Day 2 additions:

1. Paraphrase expansion
   - Ask each policy boundary question with looser wording.
   - Include synonyms such as `log`, `record`, `document`, `permission`, `approval`, `meeting edit`, `repo publish`, and `upload artifact`.

2. Multi-intent queries
   - Ask combined questions such as:
     - `What file should the GitHub report use, and can Hermes upload it automatically?`
     - `Can Hermes change meetings, and where should approvals be documented?`
   - Expected behavior: answer should preserve both relevant memories without letting one source overwrite the other.

3. Session pressure
   - Add more unrelated memories before and between policy queries.
   - Include near-topic distractors about reports, calendars, approvals, filenames, and GitHub that are not the target policy memories.

4. Correction pressure
   - Correct unrelated memories repeatedly, as Day 1 did.
   - Add at least one correction near a policy topic that should not override the policy source.

5. Evidence stability
   - Check not only top-1 retrieval but also `/ask` top evidence and answer text.
   - Fail if answer text uses a non-target source even when retrieval rank is correct.

6. Regression carry-forward
   - Keep all Day 1 cases in the Day 2 harness.
   - Day 2 passes only if Day 1 remains 42/42 and new Day 2 cases pass.

## Development Direction

The architecture worth continuing is:

- Configurable selector rules for low-cost symbolic disambiguation.
- Claim-scope and answer-type scores as lightweight cognitive control signals.
- Resolver evidence ordering that treats selector scores as evidence-routing signals, not only retrieval metadata.
- Outcome-driven promotion gates that turn live failures into small official regressions.

This is still aligned with the original CSD/G-CL direction: use structured memory signals and gated continual adaptation to reduce reliance on brute-force model scaling.

