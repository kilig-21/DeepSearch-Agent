"""config 预算常量的环境变量覆盖测试。

块 8 演示场景②(额度耗尽)需要在不改源码的前提下构造小预算;
config 在 import 时读取环境变量, 默认值与计划 §3.6 保持不变。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

API_DIR = str(Path(__file__).resolve().parents[1])


@pytest.mark.parametrize(
    ("var", "attr", "default"),
    [
        ("ORCA_BUDGET_TOTAL_LLM_TOKENS", "BUDGET_TOTAL_LLM_TOKENS", "50000"),
        ("ORCA_BUDGET_WRITER_RESERVE_TOKENS", "BUDGET_WRITER_RESERVE_TOKENS", "8000"),
        ("ORCA_BUDGET_MAX_TAVILY_CREDITS", "BUDGET_MAX_TAVILY_CREDITS", "16"),
        ("ORCA_BUDGET_MAX_PAGES", "BUDGET_MAX_PAGES", "12"),
        ("ORCA_BUDGET_TIME_S", "BUDGET_TIME_S", "480.0"),
    ],
)
def test_budget_defaults(var, attr, default):
    code = f"from orca.config import {attr}; print({attr})"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=API_DIR)
    assert out.stdout.strip() == default


@pytest.mark.parametrize(
    ("var", "attr", "value"),
    [
        ("ORCA_BUDGET_TOTAL_LLM_TOKENS", "BUDGET_TOTAL_LLM_TOKENS", "200"),
        ("ORCA_BUDGET_WRITER_RESERVE_TOKENS", "BUDGET_WRITER_RESERVE_TOKENS", "100"),
    ],
)
def test_budget_env_override(var, attr, value):
    code = f"from orca.config import {attr}; print({attr})"
    env = {**os.environ, var: value}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True, cwd=API_DIR, env=env)
    assert out.stdout.strip() == value
