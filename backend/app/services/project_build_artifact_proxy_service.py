"""文件功能：按静态站点方式代理项目构建 ZIP 产物中的文件。"""

from __future__ import annotations

import mimetypes
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.project_build_job import ProjectBuildJob
from app.services.object_storage_service import ObjectStorageService


@dataclass(slots=True, frozen=True)
class BuildArtifactProxyResult:
    """构建产物代理结果，包含响应体、类型和缓存头。"""

    content: bytes
    media_type: str
    headers: dict[str, str]


class ProjectBuildArtifactProxyService:
    """从构建任务 ZIP 归档中读取静态站点文件。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.object_storage = ObjectStorageService()

    async def get_artifact_file(
        self,
        *,
        project_id: int,
        job_id: int,
        request_path: str = "",
    ) -> BuildArtifactProxyResult:
        """读取构建产物中的目标文件；页面路由缺失时回退到入口 HTML。"""

        job = await self.get_job_or_raise(project_id=project_id, job_id=job_id)
        normalized_request_path = self.normalize_request_path(request_path)
        entry_file = self.normalize_entry_file(job.artifact_entry_file)

        try:
            async with self.resolve_archive_path(job) as archive_path:
                with ZipFile(archive_path) as archive:
                    member_map = self.build_zip_member_map(archive)
                    member_name = self.resolve_member_name(
                        member_map=member_map,
                        request_path=normalized_request_path,
                        entry_file=entry_file,
                    )
                    content = archive.read(member_name)
        except BadZipFile as exc:
            raise AppException(status_code=409, code="BUILD_ARTIFACT_INVALID", detail="构建产物归档格式非法。") from exc

        media_type = self.guess_media_type(member_name)
        return BuildArtifactProxyResult(
            content=content,
            media_type=media_type,
            headers=self.build_response_headers(media_type=media_type),
        )

    async def get_job_or_raise(self, *, project_id: int, job_id: int) -> ProjectBuildJob:
        """按项目与任务 ID 查询构建任务，避免公开入口跨项目访问。"""

        stmt = select(ProjectBuildJob).where(
            ProjectBuildJob.id == job_id,
            ProjectBuildJob.project_id == project_id,
        )
        job = (await self.session.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise AppException(status_code=404, code="BUILD_JOB_NOT_FOUND", detail="构建任务不存在。")
        return job

    @asynccontextmanager
    async def resolve_archive_path(self, job: ProjectBuildJob):
        """解析并校验构建 ZIP 归档路径。"""

        if not job.artifact_storage_key:
            raise AppException(status_code=404, code="BUILD_ARTIFACT_NOT_FOUND", detail="当前构建任务尚未生成可代理产物。")

        async with self.object_storage.open_object_for_read(
            job.artifact_storage_key,
            expected_sha256=job.artifact_sha256,
            expected_size=job.artifact_size_bytes,
        ) as archive_path:
            if not Path(archive_path).is_file():
                raise AppException(status_code=404, code="BUILD_ARTIFACT_NOT_FOUND", detail="构建产物文件不存在。")
            yield archive_path

    @staticmethod
    def normalize_request_path(request_path: str) -> str:
        """规范化浏览器请求路径，拒绝目录跳转和绝对路径。"""

        raw_path = str(request_path or "").strip()
        if "\\" in raw_path:
            raise AppException(status_code=400, code="BUILD_ARTIFACT_PATH_INVALID", detail="构建产物访问路径不合法。")

        if raw_path.startswith("/"):
            raise AppException(status_code=400, code="BUILD_ARTIFACT_PATH_INVALID", detail="构建产物访问路径不合法。")

        normalized = raw_path
        if not normalized:
            return ""

        parts = PurePosixPath(normalized).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise AppException(status_code=400, code="BUILD_ARTIFACT_PATH_INVALID", detail="构建产物访问路径不合法。")
        return "/".join(parts)

    @staticmethod
    def normalize_entry_file(raw_entry_file: str | None) -> str:
        """规范化入口 HTML 文件；任务未记录时默认使用 index.html。"""

        normalized = str(raw_entry_file or "index.html").strip().replace("\\", "/").lstrip("/")
        parts = PurePosixPath(normalized).parts
        if not normalized or any(part in {"", ".", ".."} for part in parts):
            raise AppException(status_code=409, code="BUILD_ARTIFACT_ENTRY_FILE_INVALID", detail="构建产物入口文件路径不合法。")
        return "/".join(parts)

    @classmethod
    def build_zip_member_map(cls, archive: ZipFile) -> dict[str, str]:
        """建立规范化路径到 ZIP 原始成员名的映射。"""

        member_map: dict[str, str] = {}
        for item in archive.infolist():
            if item.is_dir():
                continue
            normalized_name = cls.normalize_zip_member_name(item.filename)
            if not normalized_name:
                continue
            member_map.setdefault(normalized_name, item.filename)
        return member_map

    @staticmethod
    def normalize_zip_member_name(member_name: str) -> str:
        """规范化 ZIP 成员路径，忽略归档内不安全成员。"""

        normalized = str(member_name or "").replace("\\", "/").lstrip("/")
        if not normalized:
            return ""
        parts = PurePosixPath(normalized).parts
        if any(part in {"", ".", ".."} for part in parts):
            return ""
        return "/".join(parts)

    @classmethod
    def resolve_member_name(
        cls,
        *,
        member_map: dict[str, str],
        request_path: str,
        entry_file: str,
    ) -> str:
        """解析最终读取的 ZIP 成员；页面路径缺失时回退入口文件。"""

        target_path = entry_file if not request_path else request_path
        if target_path in member_map:
            return member_map[target_path]

        if request_path and cls.should_return_not_found(request_path):
            raise AppException(status_code=404, code="BUILD_ARTIFACT_FILE_NOT_FOUND", detail="构建产物文件不存在。")

        if entry_file not in member_map:
            raise AppException(status_code=404, code="BUILD_ARTIFACT_ENTRY_NOT_FOUND", detail="构建产物入口文件不存在。")
        return member_map[entry_file]

    @staticmethod
    def should_return_not_found(request_path: str) -> bool:
        """判断缺失路径是否应返回 404；带扩展名的静态资源不做 SPA 回退。"""

        return bool(PurePosixPath(request_path).suffix)

    @staticmethod
    def guess_media_type(member_name: str) -> str:
        """根据 ZIP 成员名推断响应 MIME 类型。"""

        media_type, _ = mimetypes.guess_type(member_name)
        return media_type or "application/octet-stream"

    @staticmethod
    def build_response_headers(*, media_type: str) -> dict[str, str]:
        """为 HTML 与静态资源设置差异化缓存策略。"""

        if media_type == "text/html":
            return {"Cache-Control": "no-cache"}
        return {"Cache-Control": "public, max-age=31536000, immutable"}
