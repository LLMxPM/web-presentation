"""文件功能：验证页面版本链写入的并发边界，确保重点快照标记与新版保存不会互相覆盖。

SQLite 夹具只有单写者，两个协程的写事务无法真正交错，因此本文件验证并发调用后的
终态语义与版本链可还原性；写-写交错的真并发证据需要在具备独立 PostgreSQL 测试库时
补跑，`backend/tests/unit/test_page_version_write_serialization.py` 守住加锁顺序。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.enums import PageFileType
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.user import User
from app.services.page_version_service import PageVersionService

pytestmark = pytest.mark.integration

_CONTENTS = [
    "<template><div>并发版本一</div></template>\n",
    "<template><div>并发版本二</div></template>",
    "<template><div>并发版本三</div></template>\n",
]


async def _seed_versions(document_client: AsyncClient) -> tuple[int, int, int]:
    """通过页面更新接口准备三个内容不同的版本，返回页面 ID 与操作者 ID。"""

    workspace = await document_client.post("/api/workspaces", json={"name": "并发版本空间", "status": "active"})
    assert workspace.status_code == 200, workspace.text
    project = await document_client.post(
        "/api/projects",
        json={"workspace_id": workspace.json()["id"], "name": "并发版本项目", "status": "active"},
    )
    assert project.status_code == 200, project.text
    page = await document_client.post(
        "/api/pages",
        json={
            "page_content": _CONTENTS[0],
            "file_type": "vue",
            "title": "并发版本页面",
            "speaker_notes": "第一版备注",
            "status": "active",
            "workspace_id": workspace.json()["id"],
            "project_id": project.json()["id"],
        },
    )
    assert page.status_code == 200, page.text
    page_id = page.json()["id"]
    for index in (1, 2):
        updated = await document_client.patch(
            f"/api/pages/{page_id}",
            json={"page_content": _CONTENTS[index], "file_type": "vue", "speaker_notes": f"第{index + 1}版备注"},
        )
        assert updated.status_code == 200, updated.text

    session_factory = get_session_factory()
    async with session_factory() as session:
        operator = await session.scalar(select(User).where(User.username == "admin"))
        assert operator is not None
        return page_id, operator.id, workspace.json()["id"]


async def test_concurrent_snapshot_and_new_version_keep_important_mark(
    authenticated_client: AsyncClient,
) -> None:
    """快照标记与新版本保存并发时，重点标记不丢失且版本链仍可完整还原。"""

    page_id, operator_id, _workspace_id = await _seed_versions(authenticated_client)
    session_factory = get_session_factory()

    async def mark_snapshot() -> None:
        """在独立事务中把最新版本标记为重点快照。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).create_snapshot(page, 3, "并发确认版")
            await session.commit()

    async def save_next_version() -> None:
        """在独立事务中保存下一个版本，触发旧最新版本的存储形态下调。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).save_new_version(
                page=page,
                page_content="<template><div>并发版本四</div></template>",
                file_type=PageFileType.VUE,
                operator_id=operator_id,
                speaker_notes="第四版备注",
            )
            await session.commit()

    await asyncio.gather(mark_snapshot(), save_next_version())

    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(PageVersion).where(PageVersion.page_id == page_id).order_by(PageVersion.version_no)
                )
            ).all()
        )
        page = await session.get(Page, page_id)
        assert page is not None

        marked = next(item for item in versions if item.version_no == 3)
        assert marked.is_important is True
        assert marked.snapshot_name == "并发确认版"
        assert marked.storage_type == "snapshot"
        assert marked.content == _CONTENTS[2]

        assert [item.version_no for item in versions] == [1, 2, 3, 4]
        assert page.current_version_no == 4
        contents = PageVersionService(session)._materialize_contents(sorted(versions, key=lambda item: -item.version_no))
        assert contents[3] == _CONTENTS[2]
        assert contents[4] == "<template><div>并发版本四</div></template>"


async def test_two_concurrent_snapshots_allocate_distinct_labels(
    authenticated_client: AsyncClient,
) -> None:
    """同一页面两个版本并发标记时，展示版号不重复且两个标记都保留。"""

    page_id, _operator_id, _workspace_id = await _seed_versions(authenticated_client)
    session_factory = get_session_factory()

    async def mark(version_no: int, name: str) -> None:
        """在独立事务中标记指定版本为重点快照。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).create_snapshot(page, version_no, name)
            await session.commit()

    await asyncio.gather(mark(1, "并发快照一"), mark(2, "并发快照二"))

    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(PageVersion).where(PageVersion.page_id == page_id).order_by(PageVersion.version_no)
                )
            ).all()
        )
        marked: list[Any] = [item for item in versions if item.is_important]
        assert [item.version_no for item in marked] == [1, 2]
        labels = [item.version_label for item in marked]
        assert len(set(labels)) == 2
        assert all(item.storage_type == "snapshot" for item in marked)
        assert [item.snapshot_name for item in marked] == ["并发快照一", "并发快照二"]


async def test_two_concurrent_saves_allocate_sequential_versions(
    authenticated_client: AsyncClient,
) -> None:
    """两次并发保存各自拿到连续版本号，diff 链可完整还原且不依赖加锁前的页面基线。"""

    page_id, operator_id, _workspace_id = await _seed_versions(authenticated_client)
    session_factory = get_session_factory()

    async def save(content: str, note: str) -> None:
        """在独立事务中保存新版本。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).save_new_version(
                page=page,
                page_content=content,
                file_type=PageFileType.VUE,
                operator_id=operator_id,
                speaker_notes=note,
            )
            await session.commit()

    await asyncio.gather(
        save("<template><div>并发保存甲</div></template>", "甲备注"),
        save("<template><div>并发保存乙</div></template>", "乙备注"),
    )

    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(PageVersion).where(PageVersion.page_id == page_id).order_by(PageVersion.version_no)
                )
            ).all()
        )
        page = await session.get(Page, page_id)
        assert page is not None

        assert [item.version_no for item in versions] == [1, 2, 3, 4, 5]
        assert page.current_version_no == 5
        contents = PageVersionService(session)._materialize_contents(sorted(versions, key=lambda item: -item.version_no))
        assert contents[3] == _CONTENTS[2]
        assert contents[4] in {"<template><div>并发保存甲</div></template>", "<template><div>并发保存乙</div></template>"}
        assert contents[5] in {"<template><div>并发保存甲</div></template>", "<template><div>并发保存乙</div></template>"}
        assert contents[4] != contents[5]


async def test_concurrent_restore_and_save_keep_version_chain_consistent(
    authenticated_client: AsyncClient,
) -> None:
    """恢复历史版本与保存新版本并发时，版本号不重复且整链仍可还原。"""

    page_id, operator_id, _workspace_id = await _seed_versions(authenticated_client)
    session_factory = get_session_factory()

    async def restore() -> None:
        """在独立事务中恢复到版本 1。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).restore_version(page, 1, operator_id, change_note="并发恢复")
            await session.commit()

    async def save() -> None:
        """在独立事务中保存全新内容。"""

        async with session_factory() as session:
            page = await session.get(Page, page_id)
            assert page is not None
            await PageVersionService(session).save_new_version(
                page=page,
                page_content="<template><div>恢复期间的新保存</div></template>",
                file_type=PageFileType.VUE,
                operator_id=operator_id,
                speaker_notes="恢复期间备注",
            )
            await session.commit()

    await asyncio.gather(restore(), save())

    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(PageVersion).where(PageVersion.page_id == page_id).order_by(PageVersion.version_no)
                )
            ).all()
        )
        page = await session.get(Page, page_id)
        assert page is not None

        assert [item.version_no for item in versions] == [1, 2, 3, 4, 5]
        assert page.current_version_no == 5
        contents = PageVersionService(session)._materialize_contents(sorted(versions, key=lambda item: -item.version_no))
        assert contents[1] == _CONTENTS[0]
        assert {contents[4], contents[5]} == {_CONTENTS[0], "<template><div>恢复期间的新保存</div></template>"}
