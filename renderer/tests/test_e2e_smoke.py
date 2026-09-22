"""文件功能：Renderer 真实 Chromium e2e 入口占位，保证 -m e2e 可收集并可扩展。"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.e2e
def test_e2e_entry_is_wired() -> None:
    """e2e 标记入口存在；未配置真实执行环境时跳过，避免空集退出码失败。"""

    if os.environ.get("RENDER_E2E_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("设置 RENDER_E2E_ENABLED=1 并启动 Runtime/Renderer 后运行真实 e2e。")
    assert True
