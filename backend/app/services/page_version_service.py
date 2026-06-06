"""文件功能：封装页面版本链的核心算法，支持源码与演讲备注的最新基线、向后 diff、重点快照与版本恢复。"""

from __future__ import annotations

import json
from datetime import datetime
from difflib import SequenceMatcher, restore, unified_diff
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.core.time_utils import format_in_app_timezone, utc_now
from app.models.enums import PageFileType, PageVersionStorageType
from app.models.page import Page
from app.models.page_version import PageVersion
from app.repositories.page_version_repository import PageVersionRepository
from app.schemas.page import PageVersionContent, PageVersionListItem
from app.services.component_dependency_service import ComponentDependencyService
from app.services.page_component_index_service import PageComponentIndexService


class _SpeakerNotesUnset:
    """演讲备注未传入标记，区别于显式传入 None 清空备注。"""


_SPEAKER_NOTES_UNSET: Final = _SpeakerNotesUnset()


class PageVersionService:
    """页面版本服务，负责维护版本链和版本内容的物化恢复。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = PageVersionRepository(session)
        self.component_index_service = PageComponentIndexService(session)
        self.dependency_service = ComponentDependencyService(session)

    @staticmethod
    def _build_timestamp_label(dt: datetime | None = None) -> str:
        """为普通保存版本生成年月日加时分秒的展示版号，时间基于业务时区。"""

        return format_in_app_timezone(dt, "%Y%m%d-%H%M%S")

    async def initialize_page_version(self, page: Page, operator_id: int, change_note: str | None = "初始版本") -> PageVersion:
        """为新页面创建第一个完整快照版本。"""

        normalized_page_content = normalize_text_to_lf(page.page_content)
        page.page_content = normalized_page_content
        created_at = utc_now()
        version = PageVersion(
            page_id=page.id,
            version_no=page.current_version_no,
            version_label=self._build_timestamp_label(created_at),
            file_type=page.file_type,
            storage_type=PageVersionStorageType.SNAPSHOT.value,
            content=normalized_page_content,
            speaker_notes=page.speaker_notes,
            is_important=False,
            change_note=change_note,
            created_by=operator_id,
            created_at=created_at,
            updated_at=created_at,
        )
        await self.repository.create(version)
        await self.component_index_service.rebuild_page_version_index(
            page=page,
            page_version=version,
            page_content=normalized_page_content,
            file_type=page.file_type,
        )
        await self.dependency_service.rebuild_page_version_dependencies(
            page=page,
            page_version=version,
            page_content=normalized_page_content,
            file_type=page.file_type,
        )
        return version

    async def save_new_version(
        self,
        page: Page,
        page_content: str,
        file_type: PageFileType,
        operator_id: int,
        speaker_notes: str | None | _SpeakerNotesUnset = _SPEAKER_NOTES_UNSET,
        change_note: str | None = None,
    ) -> PageVersion | None:
        """保存页面新版本，并将旧最新版本降级为向后 diff 或保留为重点快照。"""

        normalized_page_content = normalize_text_to_lf(page_content)
        normalized_existing_content = normalize_text_to_lf(page.page_content)
        normalized_existing_speaker_notes = (
            normalize_text_to_lf(page.speaker_notes) if page.speaker_notes is not None else None
        )
        if speaker_notes is _SPEAKER_NOTES_UNSET:
            normalized_speaker_notes = normalized_existing_speaker_notes
        elif speaker_notes is None:
            normalized_speaker_notes = None
        else:
            normalized_speaker_notes = normalize_text_to_lf(str(speaker_notes))
        normalized_file_type = file_type.value
        if (
            normalized_existing_content == normalized_page_content
            and page.file_type == normalized_file_type
            and normalized_existing_speaker_notes == normalized_speaker_notes
        ):
            return None

        latest_version = await self.repository.get_latest_by_page_id(page.id)
        if latest_version is None:
            latest_version = await self.initialize_page_version(page, operator_id)

        old_latest_content = normalized_existing_content
        if not latest_version.is_important:
            latest_version.storage_type = PageVersionStorageType.DIFF.value
            latest_version.content = self._build_backward_diff(
                newer_content=normalized_page_content,
                older_content=old_latest_content,
            )

        created_at = utc_now()
        new_version = PageVersion(
            page_id=page.id,
            version_no=page.current_version_no + 1,
            version_label=self._build_timestamp_label(created_at),
            file_type=normalized_file_type,
            storage_type=PageVersionStorageType.SNAPSHOT.value,
            content=normalized_page_content,
            speaker_notes=normalized_speaker_notes,
            is_important=False,
            change_note=change_note,
            created_by=operator_id,
            created_at=created_at,
            updated_at=created_at,
        )
        await self.repository.create(new_version)
        await self.component_index_service.rebuild_page_version_index(
            page=page,
            page_version=new_version,
            page_content=normalized_page_content,
            file_type=normalized_file_type,
        )
        await self.dependency_service.rebuild_page_version_dependencies(
            page=page,
            page_version=new_version,
            page_content=normalized_page_content,
            file_type=normalized_file_type,
        )

        page.page_content = normalized_page_content
        page.file_type = normalized_file_type
        page.speaker_notes = normalized_speaker_notes
        page.current_version_no = new_version.version_no
        return new_version

    async def list_versions(self, page: Page) -> list[PageVersionListItem]:
        """列出页面所有版本，并计算每个版本恢复后的真实内容大小。"""

        versions = await self.repository.list_by_page_id(page.id, descending=True)
        materialized = self._materialize_contents(versions)
        return [
            PageVersionListItem(
                id=version.id,
                page_id=version.page_id,
                version_no=version.version_no,
                version_label=version.version_label,
                file_type=version.file_type,
                storage_type=version.storage_type,
                is_important=version.is_important,
                is_current=version.version_no == page.current_version_no,
                snapshot_name=version.snapshot_name,
                change_note=version.change_note,
                content_size=len(materialized[version.version_no]),
                created_at=version.created_at,
                created_by=version.created_by,
            )
            for version in versions
        ]

    async def get_version_content(self, page: Page, version_no: int) -> PageVersionContent:
        """读取指定页面版本内容；diff 版本返回可读 diff，另附恢复后的完整源码。"""

        versions = await self.repository.list_by_page_id(page.id, descending=True)
        materialized = self._materialize_contents(versions)
        target = next((item for item in versions if item.version_no == version_no), None)
        if target is None:
            raise AppException(status_code=404, code="PAGE_VERSION_NOT_FOUND", detail="页面版本不存在。")

        resolved_content = materialized[target.version_no]
        content_mode = "full"
        display_content = resolved_content
        if target.storage_type == PageVersionStorageType.DIFF.value:
            content_mode = "diff"
            newer_version = next((item for item in versions if item.version_no == version_no + 1), None)
            newer_content = materialized.get(version_no + 1, "")
            newer_label = newer_version.version_label if newer_version is not None else f"{target.version_label}-next"
            display_content = self._format_backward_diff(
                target_label=target.version_label,
                newer_label=newer_label,
                older_content=resolved_content,
                newer_content=newer_content,
            )

        return PageVersionContent(
            page_id=page.id,
            version_no=target.version_no,
            version_label=target.version_label,
            file_type=target.file_type,
            storage_type=target.storage_type,
            is_important=target.is_important,
            snapshot_name=target.snapshot_name,
            change_note=target.change_note,
            speaker_notes=target.speaker_notes,
            content_mode=content_mode,
            content=display_content,
            resolved_content=resolved_content,
            created_at=target.created_at,
            created_by=target.created_by,
        )

    async def create_snapshot(
        self,
        page: Page,
        version_no: int,
        snapshot_name: str | None,
    ) -> PageVersionContent:
        """将指定版本提升为重点快照，必要时把 diff 物化为完整内容。"""

        versions = await self.repository.list_by_page_id(page.id, descending=True)
        materialized = self._materialize_contents(versions)
        target = next((item for item in versions if item.version_no == version_no), None)
        if target is None:
            raise AppException(status_code=404, code="PAGE_VERSION_NOT_FOUND", detail="页面版本不存在。")

        if not target.is_important:
            target.version_label = self._build_snapshot_label(versions=versions, target_version_no=version_no)
        target.storage_type = PageVersionStorageType.SNAPSHOT.value
        target.content = materialized[target.version_no]
        target.is_important = True
        target.snapshot_name = snapshot_name

        return PageVersionContent(
            page_id=page.id,
            version_no=target.version_no,
            version_label=target.version_label,
            file_type=target.file_type,
            storage_type=target.storage_type,
            is_important=target.is_important,
            snapshot_name=target.snapshot_name,
            change_note=target.change_note,
            speaker_notes=target.speaker_notes,
            content_mode="full",
            content=target.content,
            resolved_content=target.content,
            created_at=target.created_at,
            created_by=target.created_by,
        )

    async def restore_version(
        self,
        page: Page,
        version_no: int,
        operator_id: int,
        change_note: str | None = None,
    ) -> PageVersion | None:
        """将历史版本恢复为当前最新版本，并保留恢复动作自身的版本记录。"""

        target = await self.get_version_content(page, version_no)
        restore_note = change_note or f"恢复到 {target.version_label}"
        return await self.save_new_version(
            page=page,
            page_content=target.resolved_content,
            file_type=target.file_type,
            operator_id=operator_id,
            speaker_notes=target.speaker_notes,
            change_note=restore_note,
        )

    @staticmethod
    def _build_backward_diff(newer_content: str, older_content: str) -> str:
        """生成从较新版本回放到较旧版本的紧凑反向 patch。"""

        newer_lines = newer_content.splitlines(keepends=True)
        older_lines = older_content.splitlines(keepends=True)
        matcher = SequenceMatcher(a=newer_lines, b=older_lines, autojunk=False)
        operations: list[list[object]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                operations.append(["=", i2 - i1])
            elif tag == "delete":
                operations.append(["-", i2 - i1])
            elif tag == "insert":
                operations.append(["+", older_lines[j1:j2]])
            elif tag == "replace":
                operations.append(["~", i2 - i1, older_lines[j1:j2]])

        return json.dumps(
            {"format": "reverse_patch_v1", "ops": operations},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _apply_backward_diff(newer_content: str, diff_content: str) -> str:
        """基于较新内容和向后 diff 恢复出较旧版本内容。"""

        payload = json.loads(diff_content)
        if isinstance(payload, list):
            return "".join(restore(payload, 2))

        if not isinstance(payload, dict) or payload.get("format") != "reverse_patch_v1":
            raise AppException(status_code=500, code="PAGE_VERSION_DIFF_INVALID", detail="页面版本 diff 数据格式不受支持。")

        newer_lines = newer_content.splitlines(keepends=True)
        cursor = 0
        restored_lines: list[str] = []
        for operation in payload.get("ops", []):
            tag = operation[0]
            if tag == "=":
                keep_count = int(operation[1])
                restored_lines.extend(newer_lines[cursor: cursor + keep_count])
                cursor += keep_count
            elif tag == "-":
                cursor += int(operation[1])
            elif tag == "+":
                restored_lines.extend(operation[1])
            elif tag == "~":
                cursor += int(operation[1])
                restored_lines.extend(operation[2])
            else:
                raise AppException(status_code=500, code="PAGE_VERSION_DIFF_INVALID", detail="页面版本 diff 指令不受支持。")

        return "".join(restored_lines)

    @staticmethod
    def _format_backward_diff(target_label: str, newer_label: str, older_content: str, newer_content: str) -> str:
        """根据新旧完整内容生成适合历史查看的统一 diff 文本。"""

        return "".join(
            unified_diff(
                older_content.splitlines(keepends=True),
                newer_content.splitlines(keepends=True),
                fromfile=target_label,
                tofile=newer_label,
            )
        )

    def _materialize_contents(self, versions: list[PageVersion]) -> dict[int, str]:
        """按版本链顺序还原每个版本的完整内容。"""

        if not versions:
            return {}

        materialized: dict[int, str] = {}
        newer_content = ""
        previous_version_no: int | None = None

        for version in versions:
            if previous_version_no is not None and previous_version_no - version.version_no != 1:
                raise AppException(status_code=500, code="PAGE_VERSION_CHAIN_BROKEN", detail="页面版本链不连续，无法恢复。")

            if version.storage_type == PageVersionStorageType.SNAPSHOT.value:
                current_content = version.content
            else:
                current_content = self._apply_backward_diff(newer_content, version.content)

            materialized[version.version_no] = current_content
            newer_content = current_content
            previous_version_no = version.version_no

        return materialized

    def _build_snapshot_label(self, versions: list[PageVersion], target_version_no: int) -> str:
        """按主快照与子快照规则，为新快照分配展示版号。"""

        important_versions = sorted(
            [item for item in versions if item.is_important and item.version_no != target_version_no],
            key=lambda item: item.version_no,
        )
        if not important_versions:
            return "V1"

        latest_important = important_versions[-1]
        max_major = max(self._parse_major_no(item.version_label) for item in important_versions)
        if target_version_no > latest_important.version_no:
            return f"V{max_major + 1}"

        anchor_major = self._find_anchor_major(important_versions, target_version_no)
        if anchor_major is None:
            return "V1.1"

        next_major = self._find_next_major(important_versions, anchor_major.version_no)
        interval_children = [
            item
            for item in important_versions
            if item.version_no > anchor_major.version_no
            and (next_major is None or item.version_no < next_major.version_no)
        ]
        previous_child = next((item for item in reversed(interval_children) if item.version_no < target_version_no), None)
        next_child = next((item for item in interval_children if item.version_no > target_version_no), None)

        previous_suffix = self._parse_snapshot_suffix(previous_child.version_label) if previous_child else ""
        next_suffix = self._parse_snapshot_suffix(next_child.version_label) if next_child else None
        new_suffix = self._allocate_snapshot_suffix(previous_suffix, next_suffix)
        return f"{self._parse_major_no(anchor_major.version_label)}.{new_suffix}"

    @staticmethod
    def _parse_major_no(version_label: str) -> int:
        """从快照版号中提取主版本号。"""

        if version_label.startswith("V"):
            return int(version_label.removeprefix("V").split(".", maxsplit=1)[0])
        return int(version_label.split(".", maxsplit=1)[0])

    @staticmethod
    def _parse_snapshot_suffix(version_label: str) -> str:
        """提取子快照后缀，主快照返回空串。"""

        normalized = version_label.removeprefix("V")
        return normalized.split(".", maxsplit=1)[1] if "." in normalized else ""

    @staticmethod
    def _allocate_snapshot_suffix(previous_suffix: str, next_suffix: str | None) -> str:
        """在同一主快照区间内分配子版本号，优先生成 1.1、1.11 这类层级编号。"""

        if not previous_suffix and next_suffix is None:
            return "1"

        if next_suffix is None:
            return f"{previous_suffix}1" if previous_suffix else "1"

        if not previous_suffix:
            candidate = "1"
            if candidate < next_suffix:
                return candidate

            candidate = "01"
            while candidate >= next_suffix:
                candidate = f"0{candidate}"
            return candidate

        candidate = f"{previous_suffix}1"
        if candidate < next_suffix:
            return candidate

        candidate = f"{previous_suffix}01"
        while candidate >= next_suffix:
            candidate = f"{previous_suffix}0{candidate[len(previous_suffix):]}"
        return candidate

    @staticmethod
    def _find_anchor_major(important_versions: list[PageVersion], target_version_no: int) -> PageVersion | None:
        """找到目标版本之前最近的主快照，用于生成子快照编号。"""

        majors = [item for item in important_versions if item.version_label.startswith("V")]
        return next((item for item in reversed(majors) if item.version_no < target_version_no), None)

    @staticmethod
    def _find_next_major(important_versions: list[PageVersion], current_major_version_no: int) -> PageVersion | None:
        """找到当前主快照之后的下一个主快照。"""

        majors = [item for item in important_versions if item.version_label.startswith("V")]
        return next((item for item in majors if item.version_no > current_major_version_no), None)
