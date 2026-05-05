from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat_smoke.db"
        commands = "\n".join(
            [
                "/teach Project label memory: Cerulean Keystone is the private label for the adaptive memory brain experiment.",
                "What is Cerulean Keystone?",
                "/correct Cerulean Keystone was renamed Amber Compass for the adaptive memory brain experiment.",
                "What should I remember about that label?",
                "/history",
                "/quit",
                "",
            ]
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "chat.py"),
                "--fast-hash",
                "--db-path",
                str(db_path),
                "--agent-id",
                "chat_smoke_agent",
                "--top-k",
                "3",
            ],
            input=commands,
            text=True,
            capture_output=True,
            cwd=ROOT,
            check=False,
        )

    stdout = completed.stdout
    stderr = completed.stderr
    assert completed.returncode == 0, stderr or stdout
    assert "Memory chat ready" in stdout
    assert "taught memory:" in stdout
    assert "Relevant memory indicates: Project label memory" in stdout
    assert "corrected memory:" in stdout
    assert "Amber Compass" in stdout
    assert "turns:" in stdout
    print(
        json.dumps(
            {
                "ok": True,
                "stdout_excerpt": "\n".join(stdout.splitlines()[:24]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
