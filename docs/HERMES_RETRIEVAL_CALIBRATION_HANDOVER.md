# Hermes Handover: Retrieval-Derived CLC Selector Calibration

## Goal

Test the next development direction for the CSD/G-CL/CLC memory architecture: calibrating the retrieval-derived selector features against a larger set of real memory-pipeline cases.

The architecture now converts retrieved memory rows into selector features. The important question for this test is whether those features and the learned selector choose the right policy when retrieval contains:

- stale memory corrected by current memory
- chained corrections
- clean current memories
- unrelated clutter
- stale memories that should not affect the current query

This is not only a pass/fail smoke test. It is a calibration test. Mismatches are valuable because they tell us whether the architecture is under-detecting stale conflict or over-escalating clean contexts.

## Repository Setup

Install or update the project from GitHub:

```bash
git clone https://github.com/victorhamfler/clc-gcl-memory-core.git
cd clc-gcl-memory-core
```

If the repo already exists:

```bash
cd clc-gcl-memory-core
git pull origin main
```

The required new files are on GitHub after commit `58e1daa` plus the current handover/calibration update. No extra local Windows-only file is required for this test.

The test defaults to the portable hash embedding backend so it can run on WSL without needing the local Gemma embedding model. If the local Gemma/llama.cpp sidecar environment is healthy, an optional second run can use `--embedding-backend config`.

## Required Command

Run the calibration eval:

```bash
python eval/selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
```

If Python is not configured, create or activate a virtual environment first, then run the same command from the repository root.

Optional config/Gemma run:

```bash
python eval/selector_retrieval_calibration_eval.py --embedding-backend config --top-k 8
```

Only do the config/Gemma run if the model path and sidecar Python from `config.yaml` are available in your WSL environment.

## Output Files

The eval writes:

```text
../experiments/selector_retrieval_calibration_eval_results.json
../experiments/selector_retrieval_calibration_eval_report.md
```

Return both files to Victor/Codex after the run.

## What The Eval Does

The script creates temporary isolated memory databases and runs six cases:

| Case | Target Behavior | Purpose |
|---|---|---|
| `direct_preference_correction` | aggressive | direct stale/current correction |
| `chained_project_codename_correction` | aggressive | multi-step correction chain |
| `clean_weather_procedure` | protect | clean procedural memory should avoid escalation |
| `clean_multi_topic_clutter` | protect | clean G-CL memory with unrelated clutter |
| `food_preference_correction_with_clutter` | aggressive | same-domain stale correction with clutter |
| `unrelated_stale_memory_should_not_escalate` | protect | stale memory exists but query targets another domain |

For each case it:

1. Creates a temporary memory DB.
2. Teaches and/or corrects memories through `MemoryPipeline`.
3. Retrieves live rows from the real pipeline.
4. Converts retrieval rows into selector features with `selector_features_from_retrieval_context`.
5. Runs the learned selector explanation.
6. Compares the selected policy and hard/non-hard diagnostic against the target behavior.

## How To Interpret Results

Important fields in the JSON:

- `alignment_rate`: total aligned cases divided by total cases.
- `cases[].policy_matches_target`: whether the selected policy matched aggressive/protect expectation.
- `cases[].hard_matches_target`: whether the retrieval-derived `hard` diagnostic matched expectation.
- `cases[].diagnostics`: feature bridge measurements such as stale ratio, current ratio, contradiction, CSD ratio, and hard flag.
- `cases[].retrieval_rows`: the actual memory rows that caused the feature values.
- `cases[].nearest_samples`: selector training examples that influenced the policy.

Use this reading:

- Aggressive target but protect policy: selector underfires or learned nearest neighbors are pulling too strongly toward periodic.
- Protect target but aggressive policy: selector overfires on clean context, probably because the learned selector currently maps standard contexts toward long-severe too often.
- Expected hard false but actual hard true: retrieval feature formulas are too sensitive.
- Expected hard true but actual hard false: retrieval feature formulas are missing stale/current conflict.

## Local Baseline From Codex

A local hash-backend run before this handover produced:

```text
alignment_rate: 0.5
aligned_cases: 3 / 6
```

Mismatches:

```text
chained_project_codename_correction:
  target aggressive, actual hard true, policy periodic_baseline

clean_weather_procedure:
  target protect, actual hard false, policy long_severe_r16_overwrite

unrelated_stale_memory_should_not_escalate:
  target protect, actual hard false, policy long_severe_r16_overwrite
```

This suggests the retrieval feature bridge is detecting hardness reasonably, but the learned selector needs better calibration around chained corrections and clean standard contexts.

## Hermes Task

Run the required hash calibration test and inspect the generated Markdown and JSON. Then write a short report answering:

1. Did your run reproduce the same alignment rate and mismatches?
2. For each mismatch, is the problem in retrieval rows, feature conversion, or learned selector voting?
3. Which feature should be tuned first?
4. Should the next implementation change be:
   - adjust retrieval feature formulas,
   - add more training samples to the learned selector report,
   - add a guardrail that protects clean non-hard contexts,
   - or separate retrieval hard-detection from policy selection?

## Recommended Next Fix To Evaluate

If your results match the local baseline, the most likely next development step is a clean-context guard:

```text
If retrieval-derived diagnostics say hard=false, stale_ratio=0, contradiction_peak=0, and stale_current_conflict=0,
prefer PROTECT_PERIODIC unless budget pressure or explicit condition says hard/long.
```

That guard should be tested against the same calibration file before changing the default architecture.
