from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = REPO_ROOT / "experiments" / "adaptive_behavior_candidate_profile_results.json"
OUT_JSON = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_results.json"
OUT_MD = REPO_ROOT / "experiments" / "adaptive_behavior_profile_memory_bank_report.md"


def parse_paths(values: list[str] | None) -> list[Path]:
    paths: list[Path] = []
    for value in values or []:
        for part in str(value).split(","):
            if part.strip():
                paths.append(Path(part.strip()))
    return paths


def read_profile(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Profile must be a JSON object: {path}")
    if value.get("schema") != "adaptive_behavior_candidate_profile/v1":
        raise ValueError(f"Unsupported adaptive behavior profile schema in {path}: {value.get('schema')}")
    return value


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def proposal_key(proposal: dict[str, Any]) -> str:
    proposal_id = normalize_text(proposal.get("id"))
    family = normalize_text(proposal.get("behavior_family"))
    return f"{family}:{proposal_id}"


def cluster_readiness(
    proposals: list[dict[str, Any]],
    *,
    ready_profiles: int,
    candidate_profiles: int,
) -> str:
    statuses = {normalize_text(item.get("status")) for item in proposals}
    sources = {str(item.get("_profile_source")) for item in proposals if item.get("_profile_source")}
    if statuses and statuses <= {"hold"}:
        return "hold"
    if len(sources) >= ready_profiles and any(status == "candidate" for status in statuses):
        return "recurrence_ready"
    if len(sources) >= candidate_profiles:
        return "recurrence_candidate"
    return "hold"


def freeze_cluster(
    key: str,
    proposals: list[dict[str, Any]],
    *,
    ready_profiles: int,
    candidate_profiles: int,
) -> dict[str, Any]:
    sources = sorted({str(item.get("_profile_source")) for item in proposals if item.get("_profile_source")})
    statuses = Counter(normalize_text(item.get("status")) for item in proposals)
    families = sorted({normalize_text(item.get("behavior_family")) for item in proposals})
    deltas = [item.get("suggested_profile_delta") for item in proposals if isinstance(item.get("suggested_profile_delta"), dict)]
    match_rates = []
    for item in proposals:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        try:
            match_rates.append(float(evidence.get("family_match_rate")))
        except (TypeError, ValueError):
            pass
    return {
        "key": key,
        "behavior_family": families[0] if len(families) == 1 else "mixed",
        "proposal_ids": sorted({normalize_text(item.get("id")) for item in proposals if item.get("id")}),
        "support": len(proposals),
        "distinct_profiles": len(sources),
        "profile_sources": sources,
        "status_counts": dict(sorted(statuses.items())),
        "min_family_match_rate": round(min(match_rates), 6) if match_rates else None,
        "max_family_match_rate": round(max(match_rates), 6) if match_rates else None,
        "readiness": cluster_readiness(
            proposals,
            ready_profiles=ready_profiles,
            candidate_profiles=candidate_profiles,
        ),
        "suggested_profile_deltas": deltas[:5],
        "examples": [
            {
                "profile_source": item.get("_profile_source"),
                "status": item.get("status"),
                "rationale": item.get("rationale"),
                "evidence": item.get("evidence"),
            }
            for item in proposals[:5]
        ],
    }


def build_bank(
    profile_paths: list[Path],
    *,
    ready_profiles: int = 2,
    candidate_profiles: int = 2,
) -> dict[str, Any]:
    profiles = []
    proposals = []
    for path in profile_paths:
        profile = read_profile(path)
        profile_proposals = [item for item in profile.get("proposals") or [] if isinstance(item, dict)]
        profiles.append(
            {
                "path": str(path),
                "source_calibration": profile.get("source_calibration"),
                "source_match_rate": profile.get("source_match_rate"),
                "proposal_count": len(profile_proposals),
            }
        )
        for proposal in profile_proposals:
            item = dict(proposal)
            item["_profile_source"] = str(path)
            proposals.append(item)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in proposals:
        grouped[proposal_key(item)].append(item)
    clusters = [
        freeze_cluster(
            key,
            items,
            ready_profiles=max(1, int(ready_profiles)),
            candidate_profiles=max(1, int(candidate_profiles)),
        )
        for key, items in sorted(grouped.items())
    ]
    readiness_counts = Counter(cluster["readiness"] for cluster in clusters)
    return {
        "schema": "adaptive_behavior_profile_memory_bank/v1",
        "description": "Report-only multi-log memory bank for adaptive behavior candidate profiles.",
        "profile_count": len(profiles),
        "profiles": profiles,
        "proposal_count": len(proposals),
        "cluster_count": len(clusters),
        "ready_thresholds": {
            "ready_profiles": max(1, int(ready_profiles)),
            "candidate_profiles": max(1, int(candidate_profiles)),
        },
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "clusters": clusters,
        "ok": bool(profiles) and bool(clusters),
        "report_only": True,
        "mutates_config": False,
        "mutates_runtime": False,
    }


def clean_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("|", "\\|").replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def write_bank(bank: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(bank, indent=2), encoding="utf-8")
    lines = [
        "# Adaptive Behavior Profile Memory Bank",
        "",
        "This artifact is report-only. It does not promote adaptive behavior config or runtime behavior.",
        "",
        f"Passed: **{bank['ok']}**",
        f"Profiles: `{bank['profile_count']}`",
        f"Proposals: `{bank['proposal_count']}`",
        f"Clusters: `{bank['cluster_count']}`",
        "",
        "## Readiness Counts",
        "",
        "```json",
        json.dumps(bank["readiness_counts"], indent=2),
        "```",
        "",
        "## Clusters",
        "",
        "| readiness | key | family | support | profiles | status counts |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for cluster in bank.get("clusters") or []:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | `{}` |".format(
                cluster.get("readiness"),
                clean_cell(cluster.get("key")),
                cluster.get("behavior_family"),
                cluster.get("support"),
                cluster.get("distinct_profiles"),
                clean_cell(json.dumps(cluster.get("status_counts"), sort_keys=True)),
            )
        )
    lines.extend(["", "## Profiles", ""])
    for profile in bank.get("profiles") or []:
        lines.append(f"- `{profile['path']}`")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate adaptive behavior candidate profiles across logs/runs.")
    parser.add_argument("--profile", action="append", help="adaptive_behavior_candidate_profile/v1 JSON path. May repeat.")
    parser.add_argument("--ready-profiles", type=int, default=2)
    parser.add_argument("--candidate-profiles", type=int, default=2)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    paths = parse_paths(args.profile) or [DEFAULT_PROFILE]
    bank = build_bank(paths, ready_profiles=args.ready_profiles, candidate_profiles=args.candidate_profiles)
    write_bank(bank, args.out_json, args.out_md)
    print(
        json.dumps(
            {
                "ok": bank["ok"],
                "profile_count": bank["profile_count"],
                "readiness_counts": bank["readiness_counts"],
                "json": str(args.out_json),
            },
            indent=2,
        )
    )
    return 0 if bank["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
