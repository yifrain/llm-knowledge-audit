"""Secrets stay in the process environment and never reach a committed or saved artifact."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from llm_knowledge_audit.config import load_config
from llm_knowledge_audit.env import load_env, load_local_env, loaded_env, parse_env

ROOT = Path(__file__).resolve().parents[2]

SAMPLE = """\
# a comment line
LLMKA_API_KEY=sk-plain-value

  SPACED_KEY = spaced value
QUOTED_KEY="double quoted"
SINGLE_KEY='single quoted'
export EXPORTED_KEY=exported
NO_EQUALS_LINE
EMPTY_KEY=
"""


def test_parse_rules():
    parsed = parse_env(SAMPLE)
    assert parsed["LLMKA_API_KEY"] == "sk-plain-value"
    assert parsed["SPACED_KEY"] == "spaced value"
    assert parsed["QUOTED_KEY"] == "double quoted"
    assert parsed["SINGLE_KEY"] == "single quoted"
    assert parsed["EXPORTED_KEY"] == "exported"
    assert "NO_EQUALS_LINE" not in parsed
    # 空值视为"未设置"，而不是"设置为空字符串"
    assert "EMPTY_KEY" not in parsed


def test_load_env_does_not_override_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("LLMKA_API_KEY", "from-shell")
    path = tmp_path / ".env"
    path.write_text(SAMPLE)
    loaded = load_env(path)
    # shell 里已有的值优先，.env 不覆盖
    assert "LLMKA_API_KEY" not in loaded
    assert os.environ["LLMKA_API_KEY"] == "from-shell"
    assert "SPACED_KEY" in loaded
    assert os.environ["SPACED_KEY"] == "spaced value"


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env(tmp_path / "nope.env") == []


def test_load_env_returns_names_never_values(monkeypatch, tmp_path):
    monkeypatch.delenv("LLMKA_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("LLMKA_API_KEY=sk-super-secret\n")
    loaded = load_env(path)
    assert loaded == ["LLMKA_API_KEY"]
    assert all("sk-super-secret" != name for name in loaded)


def test_secret_value_never_enters_config_dump(monkeypatch):
    """Config 会被写进不可变的 manifest.json；密钥绝不能出现在其中。"""
    monkeypatch.setenv("LLMKA_API_KEY", "sk-must-not-be-serialized")
    cfg = load_config(ROOT / "configs/pilot.yaml")
    dumped = json.dumps(cfg.model_dump(mode="json"))
    assert "sk-must-not-be-serialized" not in dumped
    # 配置里只保存环境变量的**名字**
    assert cfg.generator.api_key_env == "LLMKA_API_KEY"


def test_bom_is_tolerated(monkeypatch, tmp_path):
    """编辑器写入 BOM 时，首个变量名不能被污染——否则密钥会静默失效。"""
    monkeypatch.delenv("LLMKA_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("LLMKA_API_KEY=sk-bom\n", encoding="utf-8-sig")
    assert load_env(path) == ["LLMKA_API_KEY"]
    assert os.environ["LLMKA_API_KEY"] == "sk-bom"


def test_unreadable_env_never_breaks_the_cli(monkeypatch, tmp_path, capsys):
    """加载发生在每条命令最前面；读失败必须降级为警告，不能中断 CLI/网页端。"""
    path = tmp_path / ".env"
    path.write_bytes(b"KEY=\xff\xfe\x00 not utf-8")
    monkeypatch.setattr("llm_knowledge_audit.env.env_candidates", lambda: [path])
    assert load_local_env() == []
    assert "无法读取" in capsys.readouterr().err


def test_loaded_env_records_success(monkeypatch, tmp_path):
    """网页端要显示"服务器启动时载入了哪个 .env、哪些变量名"，但不显示值。"""
    monkeypatch.delenv("LLMKA_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("LLMKA_API_KEY=sk-recorded\nOTHER=nope\n")
    monkeypatch.setattr("llm_knowledge_audit.env.env_candidates", lambda: [path])
    assert load_local_env() == ["LLMKA_API_KEY", "OTHER"]
    assert loaded_env() == (path, ("LLMKA_API_KEY", "OTHER"))
    # 记录里只有名字，永远没有值
    assert all("sk-recorded" not in name for name in loaded_env()[1])


def test_loaded_env_records_none_without_candidates(monkeypatch, tmp_path):
    monkeypatch.setattr("llm_knowledge_audit.env.env_candidates", lambda: [tmp_path / "absent.env"])
    assert load_local_env() == []
    assert loaded_env() == (None, ())


def test_loaded_env_records_failure(monkeypatch, tmp_path):
    """读失败时也必须把记录清空，否则网页端会显示一个早已失效的路径。"""
    path = tmp_path / ".env"
    path.write_bytes(b"KEY=\xff\xfe\x00 not utf-8")
    monkeypatch.setattr("llm_knowledge_audit.env.env_candidates", lambda: [path])
    assert load_local_env() == []
    assert loaded_env() == (None, ())


def test_env_file_stays_untracked():
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("git is unavailable")

    def ignored(name: str) -> bool:
        return (
            subprocess.run(
                [git, "check-ignore", "--quiet", name],
                cwd=ROOT,
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )

    assert ignored(".env"), ".env must stay ignored by git"
    assert ignored(".env.local"), ".env.local must stay ignored by git"
    # 模板必须可提交，否则协作者不知道要填哪些变量
    assert not ignored(".env.example"), ".env.example must stay committable"
