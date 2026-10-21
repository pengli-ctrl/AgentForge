"""构建释放模块。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = (
    "agentforge",
    "alembic",
    "deploy",
    "templates",
    "docs",
    "configs",
    "examples",
    "requirements",
    "scripts",
)
INCLUDE_FILES = (
    "alembic.ini",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "README.md",
    "SECURITY.md",
    "docker-compose.yml",
    "pyproject.toml",
    "requirements.txt",
)
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".venv", "dist", "build"}
EXCLUDED_PREFIXES = ("docs/delivery",)


def _read_version() -> str:
    """读取版本。

    Returns:
        字符串结果。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("project version not found")


def _git(*args: str) -> str:
    """执行 Git 操作。

    Args:
        args: 位置参数。

    Returns:
        字符串结果。
    """
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _files() -> list[Path]:
    """处理文件。

    Returns:
        结果列表。
    """
    paths: list[Path] = []
    for directory in INCLUDE_DIRS:
        base = ROOT / directory
        if base.exists():
            paths.extend(path for path in base.rglob("*") if path.is_file())
    paths.extend(ROOT / name for name in INCLUDE_FILES if (ROOT / name).exists())
    return sorted(
        {
            path
            for path in paths
            if not any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts)
            and not path.relative_to(ROOT).as_posix().startswith(EXCLUDED_PREFIXES)
        },
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def _sha256(path: Path) -> str:
    """计算指定文件的 SHA-256 摘要。

    Args:
        path: 文件或资源路径。

    Returns:
        字符串结果。
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add_bytes(archive: tarfile.TarFile, name: str, content: bytes, mtime: int) -> None:
    """添加数据。

    Args:
        archive: 待处理的归档对象。
        name: 资源或对象名称。
        content: 写入内容。
        mtime: 归档条目的修改时间戳。
    """
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = mtime
    archive.addfile(info, BytesIO(content))


def build(output_dir: Path) -> tuple[Path, Path]:
    """构建对象。

    Args:
        output_dir: 输出目录。

    Returns:
        结果元组。
    """
    version = _read_version()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_date = int(
        os.environ.get(
            "SOURCE_DATE_EPOCH",
            (
                _git("show", "-s", "--format=%ct", "HEAD")
                if _git("show", "-s", "--format=%ct", "HEAD").isdigit()
                else "0"
            ),
        )
    )
    files = _files()
    file_hashes = {path.relative_to(ROOT).as_posix(): _sha256(path) for path in files}
    commit = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    manifest = {
        "name": "agentforge-private",
        "version": version,
        "git_commit": commit,
        "working_tree_dirty": dirty,
        "source_date_epoch": source_date,
        "generated_at": datetime.fromtimestamp(source_date, tz=timezone.utc).isoformat(),
        "files": file_hashes,
    }
    archive_name = f"agentforge-private-{version}.tar.gz"
    archive_path = output_dir / archive_name
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=source_date, compresslevel=9
        ) as gz:
            with tarfile.open(fileobj=gz, mode="w") as archive:
                for path in files:
                    relative = path.relative_to(ROOT).as_posix()
                    data = path.read_bytes()
                    _add_bytes(
                        archive, f"agentforge-private-{version}/{relative}", data, source_date
                    )
                _add_bytes(
                    archive,
                    f"agentforge-private-{version}/RELEASE_MANIFEST.json",
                    json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
                    source_date,
                )
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {archive_name}" + chr(10), encoding="utf-8")
    return archive_path, checksum_path


def main() -> None:
    """执行主流程。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    archive, checksum = build(args.output_dir)
    print(json.dumps({"archive": str(archive), "checksum_file": str(checksum)}, indent=2))


if __name__ == "__main__":
    main()
