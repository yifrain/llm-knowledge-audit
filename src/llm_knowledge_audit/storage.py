"""Content-addressed cache and exclusive artifact writes.

按内容寻址的缓存与独占式工件写入（原子发布、禁止覆盖）。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now() -> str:
    """当前 UTC 时间戳（ISO 8601 字符串）。"""
    return datetime.now(UTC).isoformat()


def digest(value: Any) -> str:
    """对任意 JSON 可序列化值做确定性 SHA-256 哈希（键排序、保留非 ASCII 字符）。"""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def read_json(path: Path) -> Any:
    """读取 JSON 文件。"""
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件，跳过空行。"""
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_new(path: Path, value: Any) -> None:
    """Atomic publication with no overwrite, including concurrent writers.

    原子化发布且禁止覆盖：先写入同目录临时文件并 fsync，再用硬链接
    os.link 原子地"发布"到目标路径——目标已存在会抛 FileExistsError，
    因此并发写入者中只有第一个成功。绝不产生半成品文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)
    finally:
        os.unlink(temp)


def write_jsonl_new(path: Path, rows: list[dict[str, Any]]) -> None:
    """独占模式（"x"）写入 JSONL：目标已存在则失败，保证不覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


class Cache:
    """按 key 寻址的 JSON 文件缓存（如公开知识库响应的本地缓存）。"""

    def __init__(self, root: Path):
        self.root = root

    def get(self, key: str) -> Any:
        path = self.root / f"{key}.json"
        return read_json(path) if path.exists() else None

    def put(self, key: str, value: Any) -> None:
        try:
            write_new(self.root / f"{key}.json", value)
        except FileExistsError:
            pass  # First completed response wins, immutable across runs.
            # 首次完成的响应胜出：缓存条目一旦写入便不可变，跨运行保持一致。
