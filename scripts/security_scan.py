"""安全扫描模块。"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_SUFFIXES = {".py", ".toml", ".yaml", ".yml", ".sh", ".ps1", ".json", ".env"}
SKIP_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".venv", "dist", "build"}
SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{24,}"),
    "github_token": re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
}


def _files() -> list[Path]:
    """处理文件。

    Returns:
        结果列表。
    """
    result: list[Path] = []
    for base in (
        ROOT / "agentforge",
        ROOT / "deploy",
        ROOT / "configs",
        ROOT / "scripts",
        ROOT / "templates",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix in SCAN_SUFFIXES or path.name == ".env.example":
                result.append(path)
    return result


def scan() -> dict[str, object]:
    """执行扫描。

    Returns:
        结构化结果字典。
    """
    findings: list[dict[str, str]] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "type": name,
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": str(text[: match.start()].count(chr(10)) + 1),
                    }
                )
        if path.suffix == ".py":
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                findings.append(
                    {
                        "type": "syntax_error",
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": str(exc.lineno or 1),
                    }
                )
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    findings.append(
                        {
                            "type": f"dangerous_{node.func.id}",
                            "file": path.relative_to(ROOT).as_posix(),
                            "line": str(node.lineno),
                        }
                    )
                if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "run",
                    "Popen",
                    "call",
                    "check_output",
                }:
                    for keyword in node.keywords:
                        if (
                            keyword.arg == "shell"
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True
                        ):
                            findings.append(
                                {
                                    "type": "subprocess_shell_true",
                                    "file": path.relative_to(ROOT).as_posix(),
                                    "line": str(node.lineno),
                                }
                            )
    try:
        tracked_env = subprocess.check_output(
            ["git", "ls-files", ".env", ".env.local"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        tracked_env = ""
    if tracked_env:
        findings.append({"type": "tracked_env_file", "file": tracked_env, "line": "1"})
    return {"ok": not findings, "files_scanned": len(_files()), "findings": findings}


def main() -> None:
    """执行主流程。

    Raises:
        SystemExit: 操作无法完成时抛出。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "security-scan.json")
    args = parser.parse_args()
    report = scan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
