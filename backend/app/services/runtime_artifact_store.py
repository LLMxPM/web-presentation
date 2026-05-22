"""文件功能：用 Redis 保存 Runtime 临时预览 artifact 与构建运行态。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.services.redis_runtime_client import RedisRuntimeClient, get_redis_runtime_client


class RuntimeArtifactStore:
    """封装 Runtime 临时 artifact 在 Redis 中的读写协议。"""

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
            pipe = self.runtime.client.pipeline()
            pipe.set(self._manifest_key(resolved_artifact_id), self.runtime.dumps(manifest_payload), ex=ttl)
            pipe.set(self._config_key(resolved_artifact_id), self.runtime.dumps(config_bundle), ex=ttl)
            pipe.hset(self._meta_key(resolved_artifact_id), mapping=meta_payload)
            pipe.expire(self._meta_key(resolved_artifact_id), ttl)
            if module_mapping:
                pipe.hset(self._modules_key(resolved_artifact_id), mapping=module_mapping)
            pipe.expire(self._modules_key(resolved_artifact_id), ttl)
            pipe.execute()

        await asyncio.to_thread(write)
        return resolved_artifact_id

    async def get_manifest(self, artifact_id: str) -> dict[str, Any] | None:
        """读取 Runtime artifact manifest，缺失时返回 None。"""

        raw = await asyncio.to_thread(self.runtime.client.get, self._manifest_key(artifact_id))
        value = self.runtime.loads(raw, default=None)
        return value if isinstance(value, dict) else None

    async def get_config_bundle(self, artifact_id: str) -> dict[str, Any] | None:
        """读取 Runtime artifact config bundle，缺失时返回 None。"""

        raw = await asyncio.to_thread(self.runtime.client.get, self._config_key(artifact_id))
        value = self.runtime.loads(raw, default=None)
        return value if isinstance(value, dict) else None

    async def get_module(self, artifact_id: str, logical_path: str) -> str | None:
        """读取 Runtime artifact 中指定逻辑模块源码。"""

        value = await asyncio.to_thread(self.runtime.client.hget, self._modules_key(artifact_id), logical_path)
        return str(value) if value is not None else None

    async def put_build_state(self, *, job_id: int, mapping: dict[str, Any], ttl_seconds: int | None = None) -> None:
        """写入或更新构建任务的 Redis 运行态。"""

        ttl = ttl_seconds or get_settings().runtime_build_state_ttl_seconds
        payload = {str(key): "" if value is None else str(value) for key, value in mapping.items()}

        def write() -> None:
            pipe = self.runtime.client.pipeline()
            pipe.hset(self._build_key(job_id), mapping=payload)
            pipe.expire(self._build_key(job_id), ttl)
            pipe.execute()

        await asyncio.to_thread(write)

    async def get_build_state(self, *, job_id: int) -> dict[str, str]:
        """读取构建任务 Redis 运行态。"""

        return await asyncio.to_thread(self.runtime.client.hgetall, self._build_key(job_id))

    def _manifest_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:manifest")

    def _config_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:config_bundle")

    def _modules_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:modules")

    def _meta_key(self, artifact_id: str) -> str:
        return self.runtime.key(f"runtime:artifact:{artifact_id}:meta")

    def _build_key(self, job_id: int) -> str:
        return self.runtime.key(f"runtime:build:{job_id}")
