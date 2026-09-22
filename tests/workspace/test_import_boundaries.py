"""文件功能：验证所有 Python 成员共装时的模块解析和根目录 Backend CLI 入口。"""
from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("directory", [".", "backend", "renderer"])
def test_workspace_members_import_together(directory: str) -> None:
    """在三个常见启动位置使用同一虚拟环境，同时加载各成员而不依赖 sys.path 注入。"""

    completed = subprocess.run(
        [sys.executable, "-c", "import app, wp_renderer, render_contracts; print(app.__file__); print(wp_renderer.__file__); print(render_contracts.__file__)"],
        cwd=REPO_ROOT / directory,
        text=True,
        capture_output=True,
        check=True,
    )
    locations = [Path(line).resolve() for line in completed.stdout.splitlines()]
    assert locations == [
        REPO_ROOT / "backend/app/__init__.py",
        REPO_ROOT / "renderer/wp_renderer/__init__.py",
        REPO_ROOT / "packages/render-contracts/src/render_contracts/__init__.py",
    ]


def test_backend_cli_can_start_from_repo_root() -> None:
    """只请求诊断帮助，验证根目录 CLI 能解析 Backend，不访问数据库。"""

    completed = subprocess.run(
        [sys.executable, "-m", "app.scripts.diagnose_ai_run", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--run-id" in completed.stdout
