"""文件功能：用运行态存储保存 Runtime 临时预览 artifact、模板预览资源与构建运行态。"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.redis_runtime_client import (
    RedisRuntimeClient,
    RuntimeStateCapacityError,
    RuntimeStateUnavailableError,
    get_redis_runtime_client,
)


logger = logging.getLogger(__name__)


class RuntimeArtifactStore:
    """封装 Runtime 临时 artifact 在运行态存储中的读写协议。"""

    def __init__(self, runtime_client: RedisRuntimeClient | None = None) -> None:
        self.runtime = runtime_client or get_redis_runtime_client()

    async def put_artifact(
        self,
        *,
        tenant_id: str,
        workspace_id: int | None,
        project_id: int | None,
        artifact_kind: str,
        manifest: dict[str, Any],
        config_bundle: dict[str, Any],
        modules_data: list[dict[str, Any]],
        ttl_seconds: int | None = None,
        artifact_id: str | None = None,
    ) -> str:
        """写入一个短生命周期 Runtime artifact，并返回字符串 artifact_id。"""

        settings = get_settings()
        ttl = ttl_seconds or settings.runtime_preview_artifact_ttl_seconds
        resolved_artifact_id = artifact_id or f"rt_{uuid4().hex}"
        now = datetime.now(tz=UTC)
        expires_at = now + timedelta(seconds=ttl)
        manifest_payload = {
            **manifest,
            "artifact_id": resolved_artifact_id,
            "version": str(manifest.get("version") or "redis-preview-artifact"),
        }
        meta_payload = {
            "artifact_id": resolved_artifact_id,
            "artifact_kind": artifact_kind,
            "tenant_id": tenant_id,
            "workspace_id": "" if workspace_id is None else str(workspace_id),
            "project_id": "" if project_id is None else str(project_id),
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        module_mapping = {
            str(item["logical_path"]): str(item.get("content") or "")
            for item in modules_data
            if str(item.get("logical_path") or "").strip()
        }

        def write() -> None:
            pipe = self.runtime.batch()
            pipe.set(self._manifest_key(resolved_artifact_id), self.runtime.dumps(manifest_payload), ex=ttl)
            pipe.set(self._config_key(resolved_artifact_id), self.runtime.dumps(config_bundle), ex=ttl)
            pipe.hset(self._meta_key(resolved_artifact_id), meta_payload)
            pipe.expire(self._meta_key(resolved_artifact_id), ttl)
            if module_mapping:
                pipe.hset(self._modules_key(resolved_artifact_id), module_mapping)
            pipe.expire(self._modules_key(resolved_artifact_id), ttl)
            pipe.execute()

        await self._run_state_write(write, action="创建预览")
        return resolved_artifact_id

    async def get_manifest(self, artifact_id: str) -> dict[str, Any] | None:
        """读取 Runtime artifact manifest，缺失时返回 None。"""

        raw = await self._run_state_read(lambda: self.runtime.get(self._manifest_key(artifact_id)), action="读取预览")
        value = self.runtime.loads(raw, default=None)
        return value if isinstance(value, dict) else None

    async def get_config_bundle(self, artifact_id: str) -> dict[str, Any] | None:
        """读取 Runtime artifact config bundle，缺失时返回 None。"""

        raw = await self._run_state_read(lambda: self.runtime.get(self._config_key(artifact_id)), action="读取预览")
        value = self.runtime.loads(raw, default=None)
        return value if isinstance(value, dict) else None

    async def get_module(self, artifact_id: str, logical_path: str) -> str | None:
        """读取 Runtime artifact 中指定逻辑模块源码。"""

        value = await self._run_state_read(
            lambda: self.runtime.hget(self._modules_key(artifact_id), logical_path),
            action="读取预览模块",
        )
        return str(value) if value is not None else None

    async def get_modules(self, artifact_id: str, logical_paths: list[str]) -> dict[str, str] | None:
        """批量读取模块源码；artifact 不存在或任一模块缺失时返回 None。"""

        if not logical_paths:
            return {}
        values = await self._run_state_read(
            lambda: self.runtime.hmget(self._modules_key(artifact_id), logical_paths),
            action="读取预览模块",
        )
        if not isinstance(values, (list, tuple)) or len(values) != len(logical_paths) or any(value is None for value in values):
            return None
        return {path: str(value) for path, value in zip(logical_paths, values, strict=True)}

    async def put_asset_blobs(
        self,
        *,
        artifact_id: str,
        assets: dict[str, dict[str, Any]],
        ttl_seconds: int | None = None,
    ) -> None:
        """写入模板包预览使用的短生命周期资源内容。

        assets 的 key 是 file_hash，value 至少包含 content bytes，可选 content_type 和 original_name。
        """

        if not assets:
            return
        ttl = ttl_seconds or get_settings().runtime_preview_artifact_ttl_seconds
        mapping: dict[str, str] = {}
        for file_hash, item in assets.items():
            content = item.get("content")
            if not isinstance(content, bytes):
                continue
            mapping[str(file_hash)] = self.runtime.dumps(
                {
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "content_type": str(item.get("content_type") or ""),
                    "original_name": str(item.get("original_name") or ""),
                }
            )
        if not mapping:
            return

        def write() -> None:
            pipe = self.runtime.batch()
            pipe.hset(self._assets_key(artifact_id), mapping)
            pipe.expire(self._assets_key(artifact_id), ttl)
            pipe.execute()

        await self._run_state_write(write, action="创建模板预览")

    async def get_asset_blob(self, artifact_id: str, file_hash: str) -> dict[str, Any] | None:
        """读取模板包预览资源内容，缺失时返回 None。"""

        raw = await self._run_state_read(
            lambda: self.runtime.hget(self._assets_key(artifact_id), file_hash),
            action="读取模板预览资源",
        )
        payload = self.runtime.loads(raw, default=None)
        if not isinstance(payload, dict):
            return None
        try:
            content = base64.b64decode(str(payload.get("content_base64") or ""))
        except ValueError:
            return None
        return {
            "content": content,
            "content_type": str(payload.get("content_type") or ""),
            "original_name": str(payload.get("original_name") or ""),
        }

    async def delete_artifact(self, artifact_id: str) -> int:
        """显式删除完整 Runtime artifact，供诊断链路在 finally 中及时释放内存。"""

        keys = (
            self._manifest_key(artifact_id),
            self._config_key(artifact_id),
            self._modules_key(artifact_id),
            self._assets_key(artifact_id),
            self._meta_key(artifact_id),
        )
        return int(await asyncio.to_thread(self.runtime.delete, *keys))

    async def sweep_expired(self) -> int:
        """触发内存运行态的全局 TTL 清理；真实 Redis 调用会直接返回零。"""

        return int(await asyncio.to_thread(self.runtime.sweep_expired))

    async def put_build_state(self, *, job_id: int, mapping: dict[str, Any], ttl_seconds: int | None = None) -> None:
        """写入或更新构建任务的运行态缓存。

        构建任务、产物元数据与 Release 的事实源在数据库；缓存不可用时只告警，
        不能让已经提交的构建任务被接口错误地宣称为未创建。
        """

        ttl = ttl_seconds or get_settings().runtime_build_state_ttl_seconds
        payload = {str(key): "" if value is None else str(value) for key, value in mapping.items()}

        def write() -> None:
            pipe = self.runtime.batch()
            pipe.hset(self._build_key(job_id), payload)
            pipe.expire(self._build_key(job_id), ttl)
            pipe.execute()

        try:
            await asyncio.to_thread(write)
        except (RuntimeStateUnavailableError, RuntimeStateCapacityError) as exc:
            logger.warning(
                "构建任务运行态缓存写入失败，状态以数据库为准。",
                extra={
                    "event": "project.build.state.cache_failed",
                    "job_id": job_id,
                    "error": str(exc),
                },
            )

    async def _run_state_write(self, operation: Callable[[], Any], *, action: str) -> Any:
        """执行运行态写入，并把故障与容量拒绝转换为稳定业务错误。"""

        try:
            return await asyncio.to_thread(operation)
        except RuntimeStateCapacityError as exc:
            _raise_runtime_state_capacity(action, exc)
        except RuntimeStateUnavailableError as exc:
            _raise_runtime_state_unavailable(action, exc)

    async def _run_state_read(self, operation: Callable[[], Any], *, action: str) -> Any:
        """执行运行态读取，把后端不可用转换为可重试的业务错误。"""

        try:
            return await asyncio.to_thread(operation)
        except RuntimeStateUnavailableError as exc:
            _raise_runtime_state_unavailable(action, exc)

    def _manifest_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:manifest")

    def _config_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:config_bundle")

    def _modules_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:modules")

    def _assets_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:assets")

    def _meta_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:meta")

    def _build_key(self, job_id: int) -> str:
        return self.runtime.key(f"runtime:build:{job_id}")


def _raise_runtime_state_capacity(action: str, error: Exception) -> NoReturn:
    """把进程内 payload 预算拒绝转换为带重试与缩减建议的业务错误。"""

    logger.warning(
        "运行态存储容量不足。",
        extra={"event": "runtime_state.capacity_rejected", "action": action, "error": str(error)},
    )
    raise AppException(
        status_code=503,
        code="RUNTIME_STATE_CAPACITY_EXCEEDED",
        detail="运行时缓存容量已满，暂时无法完成本次请求。请稍后重试；若反复出现，请减少模板或页面中的大体积资源后重试。",
    ) from error


def _raise_runtime_state_unavailable(action: str, error: Exception) -> NoReturn:
    """把运行态后端不可用转换为可重试的业务错误。"""

    logger.warning(
        "运行态存储不可用。",
        extra={"event": "runtime_state.unavailable", "action": action, "error": str(error)},
    )
    raise AppException(
        status_code=503,
        code="RUNTIME_STATE_UNAVAILABLE",
        detail="运行时缓存暂不可用，请稍后重试。",
    ) from error


async def run_runtime_artifact_sweeper() -> None:
    """按配置周期清理进程内运行态过期键；单次失败记录事件后继续重试。"""

    settings = get_settings()
    interval = max(1.0, float(settings.runtime_artifact_sweep_interval_seconds))
    store = RuntimeArtifactStore()
    if not store.runtime.ephemeral:
        logger.info(
            "运行态后端由服务端管理 TTL，跳过进程内过期扫描。",
            extra={"event": "runtime_state.sweep.skipped", "runtime_state_backend": store.runtime.backend_kind},
        )
        return
    while True:
        await asyncio.sleep(interval)
        try:
            await store.sweep_expired()
        except Exception:  # noqa: BLE001
            # 清扫失败不能让后台任务静默退出：记录事件后按同一有界间隔重试，
            # 惰性过期仍由各读命令兜底，数据有效期不因扫描延迟而延长。
            store.runtime.record_sweep_failure()
            logger.warning(
                "运行态过期扫描失败，将在下一周期重试。",
                extra={
                    "event": "runtime_state.sweep.failed",
                    "runtime_state_backend": store.runtime.backend_kind,
                },
                exc_info=True,
            )
