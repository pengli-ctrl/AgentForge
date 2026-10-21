"""构建模块。"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict[str, str]:
    """执行项目。

    Returns:
        结构化结果字典。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    name = re.search(r'^name = "([^"]+)"$', text, re.MULTILINE)
    description = re.search(r'^description = "([^"]+)"$', text, re.MULTILINE)
    dependencies_block = re.search(r"dependencies = \[(.*?)\]", text, re.DOTALL)
    dependencies = (
        re.findall(r'"([^"]+)"', dependencies_block.group(1)) if dependencies_block else []
    )
    if not version or not name:
        raise RuntimeError("project name/version missing")
    return {
        "name": name.group(1),
        "version": version.group(1),
        "description": description.group(1) if description else "",
        "dependencies": dependencies,
    }


def _epoch() -> int:
    """执行时间戳。

    Returns:
        整数结果。
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw and raw.isdigit():
        return int(raw)
    try:
        return int(
            subprocess.check_output(
                ["git", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True
            ).strip()
        )
    except Exception:
        return 0


def _digest(data: bytes) -> str:
    """执行摘要。

    Args:
        data: 待处理数据。

    Returns:
        字符串结果。
    """
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _zip_info(name: str, epoch: int) -> zipfile.ZipInfo:
    """构建确定性的 ZIP 条目元数据。

    Args:
        name: 资源或对象名称。
        epoch: 输入参数。

    Returns:
        ZIP结果。
    """
    moment = datetime.fromtimestamp(max(epoch, 315532800), tz=timezone.utc)
    info = zipfile.ZipInfo(name, date_time=moment.timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def build(output_dir: Path) -> tuple[Path, Path]:
    """构建对象。

    Args:
        output_dir: 输出目录。

    Returns:
        结果元组。
    """
    project = _project()
    name = project["name"]
    version = project["version"]
    dist_info = f"{name}-{version}.dist-info"
    wheel_name = f"{name}-{version}-py3-none-any.whl"
    output_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = output_dir / wheel_name
    epoch = _epoch()
    package_files = sorted(
        path
        for path in (ROOT / "agentforge").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    metadata = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
        f"Summary: {project['description']}",
        "Requires-Python: >=3.10",
        "License: MIT",
    ]
    metadata.extend(f"Requires-Dist: {dependency}" for dependency in project["dependencies"])
    wheel_metadata = [
        "Wheel-Version: 1.0",
        "Generator: agentforge-release-builder",
        "Root-Is-Purelib: true",
        "Tag: py3-none-any",
    ]
    files: list[tuple[str, bytes]] = []
    for path in package_files:
        files.append((path.relative_to(ROOT).as_posix(), path.read_bytes()))
    files.extend(
        [
            (f"{dist_info}/METADATA", (chr(10).join(metadata) + chr(10)).encode("utf-8")),
            (f"{dist_info}/WHEEL", (chr(10).join(wheel_metadata) + chr(10)).encode("utf-8")),
            (f"{dist_info}/top_level.txt", b"agentforge" + bytes([10])),
            (
                f"{dist_info}/entry_points.txt",
                b"[console_scripts]"
                + bytes([10])
                + b"agentforge = agentforge.cli.main:main"
                + bytes([10]),
            ),
        ]
    )
    record_buffer = io.StringIO()
    writer = csv.writer(record_buffer, lineterminator=chr(10))
    for archive_name, content in files:
        writer.writerow([archive_name, f"sha256={_digest(content)}", str(len(content))])
    writer.writerow([f"{dist_info}/RECORD", "", ""])
    files.append((f"{dist_info}/RECORD", record_buffer.getvalue().encode("utf-8")))
    with zipfile.ZipFile(wheel_path, "w") as archive:
        for archive_name, content in sorted(files):
            archive.writestr(
                _zip_info(archive_name, epoch), content, compress_type=zipfile.ZIP_DEFLATED
            )
    checksum = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    checksum_path = wheel_path.with_suffix(wheel_path.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {wheel_name}" + chr(10), encoding="utf-8")
    return wheel_path, checksum_path


def main() -> None:
    """执行主流程。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "python")
    args = parser.parse_args()
    wheel, checksum = build(args.output_dir)
    print(wheel)
    print(checksum)


if __name__ == "__main__":
    main()
