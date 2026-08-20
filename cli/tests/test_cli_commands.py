"""文件功能：测试 CLI 命令行工具 (wp) 的命令注册、参数解析、格式化输出与错误处理。"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保能定位到 cli/src
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from click.testing import CliRunner
from wp.cli import main


def test_cli_help() -> None:
    """测试 CLI 顶层与子命令帮助信息输出。"""

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Web Presentation 官方命令行工具 (wp)" in result.output
    assert "workspace" in result.output
    assert "project" in result.output
    assert "page" in result.output
    assert "component" in result.output
    assert "asset" in result.output
    assert "build" in result.output
    assert "validate" in result.output
    assert "doctor" in result.output
    assert "screenshot" in result.output



def test_cli_doctor_unconfigured() -> None:
    """测试在未配置环境时的 doctor 输出。"""

    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "CLI 诊断检查报告" in result.output
    assert "CLI 版本" in result.output


def test_cli_json_mode() -> None:
    """测试全局 --json 选项。"""

    runner = CliRunner()
    result = runner.invoke(main, ["--json", "doctor"])
    assert result.exit_code == 0
    assert "[" in result.output
    assert "CLI 版本" in result.output
