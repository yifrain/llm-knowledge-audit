"""Local secret loading from a gitignored .env file.

从被 git 忽略的 .env 载入密钥，只写入**进程环境变量**。

设计约束（与项目整体一致）：
- 密钥绝不进入 Config 对象——因为 Config 会被 dump 进 manifest.json，
  而 manifest 是不可变的审计工件，一旦写入就永久留痕；
- 已存在的环境变量优先：shell 里显式 export 的值、CI 注入的值始终胜过 .env；
- 仅由 CLI 边界调用，库代码不隐式读取当前目录（避免意外的副作用）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 最近一次 load_local_env() 的结果：(文件路径, 载入的变量名)。
# 只记录"从哪来、载入了哪些名字"，**绝不含值**——网页端要据此显示
# "服务器启动时载入了 /path/.env（LLMKA_API_KEY）"，但不该看到任何密钥内容。
_loaded: tuple[Path | None, tuple[str, ...]] = (None, ())


def loaded_env() -> tuple[Path | None, tuple[str, ...]]:
    """返回上次 load_local_env() 的记录：(文件路径, 变量名元组)。

    未载入（无 .env、读失败、或尚未调用）时为 (None, ())。
    """
    return _loaded


def parse_env(text: str) -> dict[str, str]:
    """解析 .env 文本，返回 {变量名: 值}。

    规则（与常见 dotenv 行为一致）：
    - 忽略空行、以 # 开头的注释行、以及不含 = 的行；
    - 允许 `export KEY=VALUE` 写法；
    - 值两侧的空白会被去除，配套的成对引号（单/双）会被剥掉；
    - 空值不收集：`KEY=` 视为"未设置"，而不是"设置为空字符串"。
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if value:
            values[key] = value
    return values


def load_env(path: Path) -> list[str]:
    """把 .env 载入 os.environ，返回实际载入的变量名列表。

    只补充缺失的变量（相当于 setdefault），不覆盖已存在的同名变量。
    返回值只含变量名、绝不含值——便于调用方记录"载入了哪些密钥"而不泄漏内容。
    """
    if not path.is_file():
        return []
    loaded: list[str] = []
    # utf-8-sig：容忍编辑器写入的 BOM，否则首个变量名会被 BOM 污染而静默失效
    for key, value in parse_env(path.read_text(encoding="utf-8-sig")).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def env_candidates() -> list[Path]:
    """按优先级返回候选 .env 路径：当前工作目录，其次是本包的仓库根目录。"""
    return [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]


def load_local_env() -> list[str]:
    """CLI 边界：载入第一个存在的候选 .env，返回载入的变量名列表。

    失败绝不中断命令——.env 不可读（权限、编码）只打印警告并返回空列表。
    这一点很关键：加载发生在每条命令（含 `llmka ui`）的最前面，
    任何异常都会让整个 CLI 与网页端无法启动。

    无论走哪条分支都会覆写模块级 _loaded，因此 loaded_env() 始终反映最近一次
    真实结果（成功=路径+名字，失败或没有候选=(None, ())），测试无需额外清理。
    """
    global _loaded
    for candidate in env_candidates():
        if candidate.is_file():
            try:
                names = load_env(candidate)
            except (OSError, UnicodeDecodeError) as exc:
                print(f"warning: 无法读取 {candidate}（已忽略）：{exc}", file=sys.stderr)
                _loaded = (None, ())
                return []
            _loaded = (candidate, tuple(names))
            return names
    _loaded = (None, ())
    return []
