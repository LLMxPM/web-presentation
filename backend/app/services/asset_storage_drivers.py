"""文件功能：提供工作空间资源的本地与 S3 对象存储驱动。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.services.object_storage_service import ObjectStorageService


class BaseStorageDriver(Protocol):
    async def upload(self, workspace_id: int, file_hash: str, ext: str, content: bytes, content_type: str | None = None) -> str:
        """上传内容并返回保存的文件名。"""
        ...

    async def delete(self, workspace_id: int, file_name: str) -> None:
        """删除物理文件。"""
        ...

    async def get_physical_path(self, workspace_id: int, file_name: str) -> Path | None:
        """获取物理路径（若是本地存储）。"""
        ...

    async def generate_download_url(
        self,
        workspace_id: int,
        file_name: str,
        original_name: str,
        download: bool = False,
    ) -> str | None:
        """生成远程直接下载/查看链接。"""
        ...

    async def read_content(self, workspace_id: int, file_name: str) -> bytes:
        """读取已存储资源的原始内容。"""
        ...

    def open_for_read(
        self,
        workspace_id: int,
        file_name: str,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> AbstractAsyncContextManager[Path]:
        """打开资源对象的本地可读路径。"""
        ...


class LocalStorageDriver:
    """本地磁盘存储驱动。"""

    def __init__(self) -> None:
        self.object_storage = ObjectStorageService()

    def _get_workspace_asset_dir(self, workspace_id: int) -> Path:
        dir_path = self.object_storage.resolve_local_path(f"assets/{workspace_id}")
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    async def upload(self, workspace_id: int, file_hash: str, ext: str, content: bytes, content_type: str | None = None) -> str:
        save_name = f"{file_hash}{ext}"
        await self.object_storage.put_object(f"assets/{workspace_id}/{save_name}", content, content_type)
        return save_name

    async def delete(self, workspace_id: int, file_name: str) -> None:
        await self.object_storage.delete_object(f"assets/{workspace_id}/{file_name}")

    async def get_physical_path(self, workspace_id: int, file_name: str) -> Path | None:
        file_path = self._get_workspace_asset_dir(workspace_id) / file_name
        if file_path.exists():
            return file_path
        return None

    async def generate_download_url(
        self,
        workspace_id: int,
        file_name: str,
        original_name: str,
        download: bool = False,
    ) -> str | None:
        return None

    async def read_content(self, workspace_id: int, file_name: str) -> bytes:
        return await self.object_storage.read_object(f"assets/{workspace_id}/{file_name}")

    @asynccontextmanager
    async def open_for_read(
        self,
        workspace_id: int,
        file_name: str,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> AsyncIterator[Path]:
        """打开本地资源文件路径，供需要 FileResponse 的入口复用。"""

        async with self.object_storage.open_object_for_read(
            f"assets/{workspace_id}/{file_name}",
            expected_sha256=expected_sha256,
            expected_size=expected_size,
        ) as file_path:
            yield file_path


class S3StorageDriver:
    """S3 兼容的对象存储驱动。"""

    PUBLIC_FONT_SUFFIXES = (".woff2", ".woff", ".ttf", ".otf")

    def __init__(self) -> None:
        self.object_storage = ObjectStorageService()

    def _get_s3_key(self, workspace_id: int, file_name: str) -> str:
        return f"assets/{workspace_id}/{file_name}"

    def _resolve_bucket_name(self, file_name: str) -> str | None:
        """根据文件类型选择私有 bucket 或公开字体 bucket。"""

        settings = self.object_storage.settings
        public_bucket = str(settings.s3_public_bucket or "").strip()
        if public_bucket and self._is_public_font_file(file_name):
            return public_bucket
        return str(settings.s3_bucket or "").strip() or None

    def _build_public_font_url(self, workspace_id: int, file_name: str) -> str | None:
        """为公开字体 bucket 构造稳定访问 URL。"""

        if not self._is_public_font_file(file_name):
            return None
        public_base_url = str(self.object_storage.settings.s3_public_base_url or "").strip().rstrip("/")
        if not public_base_url:
            return None
        return f"{public_base_url}/{self._get_s3_key(workspace_id, file_name)}"

    @classmethod
    def _is_public_font_file(cls, file_name: str) -> bool:
        """判断文件名是否应进入公开字体资源链路。"""

        normalized_name = str(file_name or "").strip().lower()
        return normalized_name.endswith(cls.PUBLIC_FONT_SUFFIXES)

    async def upload(self, workspace_id: int, file_hash: str, ext: str, content: bytes, content_type: str | None = None) -> str:
        save_name = f"{file_hash}{ext}"
        await self.object_storage.put_object(
            self._get_s3_key(workspace_id, save_name),
            content,
            content_type,
            bucket_name=self._resolve_bucket_name(save_name),
        )
        return save_name

    async def delete(self, workspace_id: int, file_name: str) -> None:
        await self.object_storage.delete_object(
            self._get_s3_key(workspace_id, file_name),
            bucket_name=self._resolve_bucket_name(file_name),
        )

    async def get_physical_path(self, workspace_id: int, file_name: str) -> Path | None:
        return None

    async def generate_download_url(
        self,
        workspace_id: int,
        file_name: str,
        original_name: str,
        download: bool = False,
    ) -> str | None:
        public_url = None if download else self._build_public_font_url(workspace_id, file_name)
        if public_url:
            return public_url
        return await self.object_storage.generate_presigned_url(
            self._get_s3_key(workspace_id, file_name),
            original_name=original_name,
            download=download,
            bucket_name=self._resolve_bucket_name(file_name),
        )

    async def read_content(self, workspace_id: int, file_name: str) -> bytes:
        return await self.object_storage.read_object(
            self._get_s3_key(workspace_id, file_name),
            bucket_name=self._resolve_bucket_name(file_name),
        )

    @asynccontextmanager
    async def open_for_read(
        self,
        workspace_id: int,
        file_name: str,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> AsyncIterator[Path]:
        """打开 S3 资源的本地缓存路径，并沿用字体公开 bucket 分流规则。"""

        async with self.object_storage.open_object_for_read(
            self._get_s3_key(workspace_id, file_name),
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            bucket_name=self._resolve_bucket_name(file_name),
        ) as file_path:
            yield file_path


def get_driver() -> BaseStorageDriver:
    """根据配置选择资产存储驱动。"""

    settings = get_settings()
    if settings.asset_storage_driver == "s3":
        return S3StorageDriver()
    return LocalStorageDriver()


