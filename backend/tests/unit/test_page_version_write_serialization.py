"""文件功能：守住页面版本链写入的串行化锚点，避免重点快照标记与新版保存各自读旧状态后互相覆盖。"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.models.enums import PageFileType
from app.models.page import Page
from app.services import page_version_service as version_module
from app.services.page_version_service import PageVersionService

pytestmark = pytest.mark.unit


class _RecordingSession:
    """仅记录调用顺序的最小会话替身，避免单元测试搭建完整数据库。"""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def flush(self) -> None:
        """记录写入刷新，用于确认加锁发生在版本链读取之前。"""

        self.events.append("flush")

    async def refresh(self, obj: object) -> None:
        """记录锁后基线刷新，确保并发写入不再使用加锁前的过期页面状态。"""

        self.events.append(f"refresh:{getattr(obj, 'id', None)}")


@pytest.fixture
def lock_recorder(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """把页面行锁替换为可观测事件，断言两条写路径都先加锁再读版本链。"""

    events: list[str] = []

    async def _record_lock(session: object, model: object, row_id: int) -> None:
        events.append(f"lock:{model.__name__}:{row_id}")

    monkeypatch.setattr(version_module, "acquire_row_write_lock", _record_lock)
    return events


async def test_save_new_version_acquires_page_lock_before_reading_chain(
    lock_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存新版本必须先取得页面行锁，再读取最新版本决定可否下调为 diff。"""

    service = PageVersionService.__new__(PageVersionService)
    service.session = _RecordingSession(lock_recorder)
    service.component_index_service = None
    service.dependency_service = None

    page = Page(
        id=17,
        code="lock-page",
        page_content="<template><div>旧</div></template>",
        current_version_no=2,
        file_type=PageFileType.VUE.value,
        title="加锁页面",
    )

    class _Repository:
        async def get_latest_by_page_id(self, page_id: int):
            """在读取版本链时记录事件，暴露是否先加锁。"""

            lock_recorder.append(f"read:{page_id}")
            return None

        async def create(self, version_model: object):
            """记录新版本落库，不写真实数据库。"""

            lock_recorder.append("create")
            return version_model

    async def _initialize(page_model: Page, operator_id: int, change_note: str | None = None):
        """替身初始化版本，保持版本号链路连续。"""

        lock_recorder.append("initialize")
        raise RuntimeError("测试替身不执行初始化")

    service.repository = _Repository()
    service._ensure_model_view_options_valid = lambda content: None
    service._ensure_audio_options_valid = lambda content: None
    service.initialize_page_version = _initialize

    with pytest.raises(RuntimeError):
        await service.save_new_version(
            page=page,
            page_content="<template><div>新</div></template>",
            file_type=PageFileType.VUE,
            operator_id=3,
        )

    assert lock_recorder[0] == "lock:Page:17"
    assert lock_recorder[1] == "refresh:17"
    assert lock_recorder[2] == "read:17"


async def test_save_new_version_rechecks_unchanged_baseline_after_lock(
    lock_recorder: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """锁前相同的快速返回路径也必须基于锁后刷新的页面基线判断。"""

    service = PageVersionService.__new__(PageVersionService)
    service.session = _RecordingSession(lock_recorder)
    service.component_index_service = None
    service.dependency_service = None

    page = Page(
        id=18,
        code="nochange-page",
        page_content="<template><div>同一份</div></template>",
        current_version_no=1,
        file_type=PageFileType.VUE.value,
        title="无变更页面",
    )

    class _Repository:
        async def get_latest_by_page_id(self, page_id: int):
            """无变更路径不应读取版本链；读取即说明判断顺序错误。"""

            lock_recorder.append(f"read:{page_id}")
            return None

    service.repository = _Repository()
    service._ensure_model_view_options_valid = lambda content: None
    service._ensure_audio_options_valid = lambda content: None

    result = await service.save_new_version(
        page=page,
        page_content="<template><div>同一份</div></template>",
        file_type=PageFileType.VUE,
        operator_id=3,
    )

    assert result is None
    assert lock_recorder == ["lock:Page:18", "refresh:18"]


async def test_create_snapshot_acquires_page_lock_before_materializing(
    lock_recorder: list[str],
) -> None:
    """标记重点快照同样先加页面行锁，避免并发分配重复展示版号。"""

    service = PageVersionService.__new__(PageVersionService)
    service.session = _RecordingSession(lock_recorder)

    page = Page(
        id=23,
        code="snapshot-page",
        page_content="<template><div>内容</div></template>",
        current_version_no=1,
        file_type=PageFileType.VUE.value,
        title="快照页面",
    )

    class _Repository:
        async def list_by_page_id(self, page_id: int, descending: bool = True):
            """空版本链直接触发 404，用于确认加锁顺序。"""

            lock_recorder.append(f"list:{page_id}")
            return []

    service.repository = _Repository()

    with pytest.raises(AppException):
        await service.create_snapshot(page, 1, "并发确认版")

    assert lock_recorder == ["lock:Page:23", "refresh:23", "list:23"]
