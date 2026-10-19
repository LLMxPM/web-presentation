"""文件功能：装配 backend pytest 夹具与目录级 marker 规则。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.fixtures.app import *  # noqa: F401,F403


@pytest.fixture
def open_audio_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 M2 三个音频能力标记为已开放，供 cue/旁白写入正例复用。"""

    from app.schemas import audio as audio_schema

    monkeypatch.setattr(
        audio_schema,
        "AUDIO_OPEN_CAPABILITIES",
        frozenset(
            {
                audio_schema.AUDIO_CAPABILITY_AUDIO_ASSETS,
                audio_schema.AUDIO_CAPABILITY_PAGE_NARRATION,
                audio_schema.AUDIO_CAPABILITY_AUDIO_CUES,
            }
        ),
    )


@pytest.fixture
def build_worker_credential(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """注入测试用 Runtime Build Worker 共享凭证，并在结束时清理 settings 缓存。"""

    from app.core.config import get_settings

    credential = "test-build-worker-credential"
    monkeypatch.setenv("RUNTIME_BUILD_WORKER_CREDENTIAL", credential)
    get_settings.cache_clear()
    yield credential
    get_settings.cache_clear()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """根据测试文件目录自动补充 pytest marker，统一根仓测试入口筛选语义。"""

    marker_rules = {
        "unit": pytest.mark.unit,
        "api": pytest.mark.api,
        "integration": pytest.mark.integration,
        "contracts": pytest.mark.contract,
    }

    for item in items:
        relative_parts = Path(str(item.fspath)).parts
        for directory_name, marker in marker_rules.items():
            if directory_name in relative_parts:
                item.add_marker(marker)
                break
