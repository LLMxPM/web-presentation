"""文件功能：提供工作空间资源的本地与 S3 对象存储驱动。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings
from app.core.exceptions import AppException
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
        """用户资产统一进入私有 bucket，禁止按 .woff2 等后缀自动分流到公共桶 (W08,W11)。"""

        settings = self.object_storage.settings
        return str(settings.s3_bucket or "").strip() or None

    def _build_public_font_url(self, workspace_id: int, file_name: str) -> str | None:
        """用户字体与资源文件默认私有，不生成公开直连 URL。"""

        return None


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
        """私有桶未命中时，仅对旧字体执行受控复制迁移。"""
        try:
            return await self.object_storage.read_object(
                self._get_s3_key(workspace_id, file_name), bucket_name=self._resolve_bucket_name(file_name),
            )
        except AppException as exc:
            if exc.code != "OBJECT_NOT_FOUND":
                raise
        return await self._migrate_legacy_font(workspace_id, file_name)

    async def _migrate_legacy_font(self, workspace_id: int, file_name: str) -> bytes:
        """服务端读取旧字体桶并校验后复制到私有桶；不公开链接，不删除原件。"""
        import hashlib
        import mimetypes

        legacy = str(self.object_storage.settings.s3_public_bucket or "").strip()
        private = self._resolve_bucket_name(file_name)
        if not legacy or legacy == private or not file_name.lower().endswith(self.PUBLIC_FONT_SUFFIXES):
            raise AppException(404, "OBJECT_NOT_FOUND", "对象文件不存在。")
        key = self._get_s3_key(workspace_id, file_name)
        content = await self.object_storage.read_object(key, bucket_name=legacy)
        digest = Path(file_name).stem
        if len(digest) == 64 and hashlib.sha256(content).hexdigest() != digest:
            raise AppException(409, "OBJECT_SHA256_MISMATCH", "存量字体内容与登记身份不一致。")
        await self.object_storage.put_object(key, content, mimetypes.guess_type(file_name)[0], bucket_name=private)
        return content

    @asynccontextmanager
    async def open_for_read(
        self,
        workspace_id: int,
        file_name: str,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> AsyncIterator[Path]:
        """打开私有桶缓存；旧字体仅在对象不存在时迁移后重试。"""
        async with AsyncExitStack() as stack:
            try:
                file_path = await stack.enter_async_context(self.object_storage.open_object_for_read(
                    self._get_s3_key(workspace_id, file_name), expected_sha256=expected_sha256,
                    expected_size=expected_size, bucket_name=self._resolve_bucket_name(file_name),
                ))
            except AppException as exc:
                if exc.code != "OBJECT_NOT_FOUND":
                    raise
                await self._migrate_legacy_font(workspace_id, file_name)
                file_path = await stack.enter_async_context(self.object_storage.open_object_for_read(
                    self._get_s3_key(workspace_id, file_name), expected_sha256=expected_sha256,
                    expected_size=expected_size, bucket_name=self._resolve_bucket_name(file_name),
                ))
            # 只捕获打开阶段的缺失，不能把响应消费期间的业务异常解释成字体迁移。
            yield file_path


def get_driver() -> BaseStorageDriver:
    """根据配置选择资产存储驱动。"""

    settings = get_settings()
    if settings.asset_storage_driver == "s3":
        return S3StorageDriver()
    return LocalStorageDriver()


