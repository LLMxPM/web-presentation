"""文件功能：提供统一对象存储抽象，覆盖本地磁盘与 S3 兼容存储。"""

from __future__ import annotations

import hashlib
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote

from app.core.config import get_settings
from app.core.exceptions import AppException

try:
    import aioboto3
except ImportError:  # pragma: no cover - 依赖缺失时在启用 S3 的路径中报错
    aioboto3 = None

try:
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - botocore 随 aioboto3 安装，缺失时仅影响 S3 路径
    ClientError = None


class ObjectStorageService:
    """统一管理平台对象文件的上传、读取、删除与本地可读路径获取。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.driver = self.settings.asset_storage_driver
        self.local_root = self.settings.page_screenshot_local_root_path
        self.cache_root = self.local_root / "_object-cache"

    async def put_object(
        self,
        storage_key: str,
        content: bytes,
        content_type: str | None = None,
        *,
        bucket_name: str | None = None,
    ) -> str:
        """保存对象内容，并返回规范化后的 storage key。"""

        normalized_key = self.normalize_storage_key(storage_key)
        if not content:
            raise AppException(status_code=400, code="OBJECT_CONTENT_EMPTY", detail="对象内容不能为空。")

        if self.driver == "s3":
            await self._put_s3_object(normalized_key, content, content_type, bucket_name=bucket_name)
            return normalized_key

        target_path = self.resolve_local_path(normalized_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        return normalized_key

    async def read_object(self, storage_key: str, *, bucket_name: str | None = None) -> bytes:
        """读取对象原始内容。"""

        normalized_key = self.normalize_storage_key(storage_key)
        if self.driver == "s3":
            if bucket_name is not None:
                return await self._read_s3_object(normalized_key, bucket_name=bucket_name)
            return await self._read_s3_object(normalized_key)

        file_path = self.resolve_local_path(normalized_key)
        if not file_path.is_file():
            raise AppException(status_code=404, code="OBJECT_NOT_FOUND", detail="对象文件不存在。")
        return file_path.read_bytes()

    async def delete_object(self, storage_key: str, *, bucket_name: str | None = None) -> None:
        """删除对象；对象不存在时保持幂等。"""

        normalized_key = self.normalize_storage_key(storage_key)
        if self.driver == "s3":
            await self._delete_s3_object(normalized_key, bucket_name=bucket_name)
            return

        file_path = self.resolve_local_path(normalized_key)
        if file_path.exists():
            file_path.unlink()

    @asynccontextmanager
    async def open_object_for_read(
        self,
        storage_key: str,
        *,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        bucket_name: str | None = None,
    ) -> AsyncIterator[Path]:
        """返回对象的本地可读路径；S3 对象会下载到后端临时缓存后再返回。"""

        normalized_key = self.normalize_storage_key(storage_key)
        if self.driver != "s3":
            file_path = self.resolve_local_path(normalized_key)
            if not file_path.is_file():
                raise AppException(status_code=404, code="OBJECT_NOT_FOUND", detail="对象文件不存在。")
            yield file_path
            return

        self.sweep_object_cache_if_needed()
        cache_path = await self._ensure_s3_cache_file(
            normalized_key,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
            bucket_name=bucket_name,
        )
        self._touch_cache_file(cache_path)
        yield cache_path

    def sweep_object_cache_if_needed(self) -> None:
        """按配置的扫描间隔机会式清理 S3 本地派生缓存。"""

        interval_seconds = int(self.settings.object_cache_sweep_interval_seconds)
        if interval_seconds <= 0:
            return

        marker_path = self.cache_root / ".last_sweep"
        now = time.time()
        try:
            if marker_path.is_file() and now - marker_path.stat().st_mtime < interval_seconds:
                return
            self.sweep_object_cache(now=now)
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.touch()
        except OSError:
            return

    def sweep_object_cache(self, *, now: float | None = None) -> None:
        """清理超过闲置期或总容量上限的对象缓存文件。"""

        if not self.cache_root.exists():
            return

        current_time = now if now is not None else time.time()
        idle_seconds = int(self.settings.object_cache_idle_days) * 24 * 60 * 60
        max_bytes = int(self.settings.object_cache_max_bytes)
        cache_files = self._list_cache_files()

        for file_path in cache_files:
            try:
                if current_time - file_path.stat().st_mtime > idle_seconds:
                    file_path.unlink(missing_ok=True)
            except OSError:
                continue

        remaining_files = self._list_cache_files()
        sized_files: list[tuple[Path, float, int]] = []
        total_bytes = 0
        for file_path in remaining_files:
            try:
                stat = file_path.stat()
            except OSError:
                continue
            total_bytes += stat.st_size
            sized_files.append((file_path, stat.st_mtime, stat.st_size))

        for file_path, _, file_size in sorted(sized_files, key=lambda item: item[1]):
            if total_bytes <= max_bytes:
                break
            try:
                file_path.unlink(missing_ok=True)
                total_bytes -= file_size
            except OSError:
                continue

        self._remove_empty_cache_dirs()

    def resolve_local_path(self, storage_key: str) -> Path:
        """把对象 key 映射成本地磁盘路径。"""

        normalized_key = self.normalize_storage_key(storage_key)
        return self.ensure_local_root() / Path(normalized_key)

    def ensure_local_root(self) -> Path:
        """确保本地对象根目录存在。"""

        self.local_root.mkdir(parents=True, exist_ok=True)
        return self.local_root

    def build_media_url(self, storage_key: str | None) -> str | None:
        """为本地静态挂载构造 /media URL。"""

        if not storage_key:
            return None
        return f"/media/{quote(self.normalize_storage_key(storage_key), safe='/')}"

    async def generate_presigned_url(
        self,
        storage_key: str,
        *,
        original_name: str | None = None,
        download: bool = False,
        expires_in: int = 3600,
        bucket_name: str | None = None,
    ) -> str | None:
        """为 S3 对象生成即时预签名 URL；本地存储返回 None。"""

        if self.driver != "s3":
            return None
        normalized_key = self.normalize_storage_key(storage_key)
        resolved_bucket = self._resolve_s3_bucket_name(bucket_name)
        self._ensure_s3_config(resolved_bucket)
        async with self._s3_client() as client:
            params = {
                "Bucket": resolved_bucket,
                "Key": normalized_key,
            }
            if download and original_name:
                encoded_name = quote(original_name)
                params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{encoded_name}"
            return await client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)

    async def _put_s3_object(
        self,
        storage_key: str,
        content: bytes,
        content_type: str | None,
        *,
        bucket_name: str | None = None,
    ) -> None:
        """上传对象到 S3 兼容存储。"""

        resolved_bucket = self._resolve_s3_bucket_name(bucket_name)
        self._ensure_s3_config(resolved_bucket)
        put_kwargs: dict[str, object] = {
            "Bucket": resolved_bucket,
            "Key": storage_key,
            "Body": content,
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        async with self._s3_client() as client:
            await client.put_object(**put_kwargs)

    async def _read_s3_object(self, storage_key: str, *, bucket_name: str | None = None) -> bytes:
        """从 S3 兼容存储读取对象。"""

        resolved_bucket = self._resolve_s3_bucket_name(bucket_name)
        self._ensure_s3_config(resolved_bucket)
        async with self._s3_client() as client:
            try:
                response = await client.get_object(Bucket=resolved_bucket, Key=storage_key)
            except Exception as error:
                self._raise_s3_read_error(error, storage_key)
            return await response["Body"].read()

    @staticmethod
    def _raise_s3_read_error(error: Exception, storage_key: str) -> None:
        """将 S3 读取异常转换为平台统一对象存储错误。"""

        if ClientError is not None and isinstance(error, ClientError):
            error_payload = getattr(error, "response", {}) or {}
            error_info = error_payload.get("Error", {}) if isinstance(error_payload, dict) else {}
            error_code = str(error_info.get("Code") or "").strip()
            if error_code in {"NoSuchKey", "404", "NotFound"}:
                raise AppException(
                    status_code=404,
                    code="OBJECT_NOT_FOUND",
                    detail=f"对象文件不存在：{storage_key}。",
                ) from error

        raise error

    async def _delete_s3_object(self, storage_key: str, *, bucket_name: str | None = None) -> None:
        """从 S3 兼容存储删除对象。"""

        resolved_bucket = self._resolve_s3_bucket_name(bucket_name)
        self._ensure_s3_config(resolved_bucket)
        async with self._s3_client() as client:
            await client.delete_object(Bucket=resolved_bucket, Key=storage_key)

    async def _ensure_s3_cache_file(
        self,
        storage_key: str,
        *,
        expected_sha256: str | None,
        expected_size: int | None,
        bucket_name: str | None,
    ) -> Path:
        """确保 S3 对象已下载到本地缓存，并校验声明的 hash 与大小。"""

        cache_path = self._build_cache_path(storage_key, expected_sha256, expected_size, bucket_name)
        if self._is_valid_cache_file(cache_path, expected_sha256, expected_size):
            self._touch_cache_file(cache_path)
            return cache_path

        if bucket_name is None:
            content = await self._read_s3_object(storage_key)
        else:
            content = await self._read_s3_object(storage_key, bucket_name=bucket_name)
        self._validate_object_bytes(content, expected_sha256, expected_size)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        self._touch_cache_file(cache_path)
        return cache_path

    def _build_cache_path(
        self,
        storage_key: str,
        expected_sha256: str | None,
        expected_size: int | None,
        bucket_name: str | None,
    ) -> Path:
        """根据 key、hash 与大小构造稳定缓存文件名。"""

        fingerprint = hashlib.sha256(
            f"{bucket_name or ''}:{storage_key}:{expected_sha256 or ''}:{expected_size or ''}".encode("utf-8")
        ).hexdigest()
        suffix = Path(storage_key).suffix or ".bin"
        return self.cache_root / f"{fingerprint}{suffix}"

    def _list_cache_files(self) -> list[Path]:
        """列出缓存根目录下的普通文件，排除扫描标记。"""

        if not self.cache_root.exists():
            return []
        return [
            file_path
            for file_path in self.cache_root.rglob("*")
            if file_path.is_file() and file_path.name != ".last_sweep"
        ]

    def _remove_empty_cache_dirs(self) -> None:
        """删除缓存清理后留下的空目录。"""

        if not self.cache_root.exists():
            return
        for dir_path in sorted((path for path in self.cache_root.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            try:
                dir_path.rmdir()
            except OSError:
                continue

    @staticmethod
    def _touch_cache_file(file_path: Path) -> None:
        """更新缓存文件访问时间，供闲置清理判断。"""

        try:
            if file_path.is_file():
                file_path.touch()
        except OSError:
            pass

    @staticmethod
    def _is_valid_cache_file(cache_path: Path, expected_sha256: str | None, expected_size: int | None) -> bool:
        """判断缓存文件是否满足本次读取约束。"""

        if not cache_path.is_file():
            return False
        content = cache_path.read_bytes()
        try:
            ObjectStorageService._validate_object_bytes(content, expected_sha256, expected_size)
        except AppException:
            return False
        return True

    @staticmethod
    def _validate_object_bytes(content: bytes, expected_sha256: str | None, expected_size: int | None) -> None:
        """校验对象 bytes 的 sha256 与大小，避免缓存污染。"""

        if expected_size is not None and len(content) != int(expected_size):
            raise AppException(status_code=409, code="OBJECT_SIZE_MISMATCH", detail="对象大小与记录不一致。")
        normalized_sha256 = str(expected_sha256 or "").strip().lower()
        if normalized_sha256 and hashlib.sha256(content).hexdigest() != normalized_sha256:
            raise AppException(status_code=409, code="OBJECT_SHA256_MISMATCH", detail="对象校验和与记录不一致。")

    def _s3_client(self):
        """创建 S3 client；调用方负责在 async with 中使用。"""

        if not aioboto3:
            raise AppException(status_code=500, code="S3_LIB_MISSING", detail="未安装 aioboto3，无法启用 S3 存储。")
        return aioboto3.Session().client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        )

    def _resolve_s3_bucket_name(self, bucket_name: str | None = None) -> str | None:
        """解析本次 S3 操作使用的 bucket 名称。"""

        return str(bucket_name or self.settings.s3_bucket or "").strip() or None

    def _ensure_s3_config(self, bucket_name: str | None = None) -> None:
        """校验 S3 必要配置完整。"""

        missing = [
            name
            for name, value in {
                "S3_ACCESS_KEY": self.settings.s3_access_key,
                "S3_SECRET_KEY": self.settings.s3_secret_key,
                "S3_BUCKET": bucket_name or self.settings.s3_bucket,
            }.items()
            if not str(value or "").strip()
        ]
        if missing:
            raise AppException(
                status_code=500,
                code="S3_CONFIG_INCOMPLETE",
                detail=f"S3 配置缺失：{', '.join(missing)}。",
            )

    @staticmethod
    def normalize_storage_key(storage_key: str) -> str:
        """规范化对象 key，拒绝空值、绝对路径和目录跳转。"""

        normalized = str(storage_key or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            raise AppException(status_code=400, code="OBJECT_STORAGE_KEY_REQUIRED", detail="storage_key 不能为空。")

        segments = [segment for segment in normalized.split("/") if segment]
        if not segments or any(segment in {".", ".."} for segment in segments):
            raise AppException(status_code=400, code="OBJECT_STORAGE_KEY_INVALID", detail="storage_key 不能包含目录跳转。")
        return "/".join(segments)
