import subprocess
import sys


def main() -> int:
    commands: list[tuple[str, list[str]]] = [
        ("ruff check .", [sys.executable, "-m", "ruff", "check", "."]),
        ("mypy .", [sys.executable, "-m", "mypy", "."]),
        ("bandit -r api", [sys.executable, "-m", "bandit", "-r", "api"]),
        ("pip-audit", [sys.executable, "-m", "pip_audit"]),
        ("pytest -q", [sys.executable, "-m", "pytest", "-q"]),
    ]

    print("Running quality + test pipeline")
    failed = False
    for label, cmd in commands:
        print(f"\n==> {label}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            failed = True

    print("\nPipeline result: FAILED" if failed else "\nPipeline result: PASSED")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
