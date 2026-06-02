from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
TARGET = ROOT / "eval" / "canonical_ogcf_shadow_coverage_regression.py"
OUT_JSON = REPO_ROOT / "experiments" / "portable_gate_dependency_regression_results.json"
OUT_MD = REPO_ROOT / "experiments" / "portable_gate_dependency_regression_report.md"

FORBIDDEN_IMPORT_PREFIXES = (
    "core.",
    "eval.canonical_ogcf_production_shadow_eval",
    "numpy",
    "storage.",
)
ALLOWED_IMPORTS = {
    "__future__",
    "json",
    "sys",
    "pathlib",
}


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return sorted(set(modules))


def main() -> int:
    imports = imported_modules(TARGET)
    forbidden = [
        module
        for module in imports
        if module in FORBIDDEN_IMPORT_PREFIXES
        or any(module.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES)
    ]
    unexpected = [
        module
        for module in imports
        if module not in ALLOWED_IMPORTS
        and not any(module.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES)
    ]
    checks = {
        "target_exists": TARGET.exists(),
        "no_heavy_or_project_imports": not forbidden,
        "only_expected_stdlib_imports": not unexpected,
        "coverage_regression_remains_self_contained": imports == sorted(ALLOWED_IMPORTS),
    }
    report = {
        "schema": "portable_gate_dependency_regression/v1",
        "description": "Guards the portable shadow coverage regression against heavy production/runtime imports.",
        "ok": all(checks.values()),
        "checks": checks,
        "target": str(TARGET),
        "imports": imports,
        "forbidden_imports": forbidden,
        "unexpected_imports": unexpected,
        "json": str(OUT_JSON),
        "markdown": str(OUT_MD),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Portable Gate Dependency Regression",
        "",
        f"Passed: **{report['ok']}**",
        "",
        "| check | pass |",
        "| --- | --- |",
    ]
    for key, value in checks.items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Imports",
            "",
            "```json",
            json.dumps(imports, indent=2),
            "```",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "checks": checks, "json": str(OUT_JSON)}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
