"""文件功能：领域调用方统一入口，创建渲染请求并等待远端执行结果。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.services.rendering.coordinator import RenderCoordinator, get_render_coordinator
from app.services.rendering.credentials import RenderCredentialService
from app.services.rendering.errors import render_error_to_app_exception
from app.services.rendering.layout_contract import normalize_layout_analysis
from app.services.rendering.request_service import RenderRequestService
from app.services.rendering.sanitize import sanitize_error_message
from app.services.rendering.snapshot_service import RenderSnapshotService
from app.services.rendering.target_resolver import RenderTargetResolver
from render_contracts.constants import (
    OPERATION_PAGE_CAPTURE,
    OPERATION_PAGE_DIAGNOSE,
)
from render_contracts.errors import (
    ERROR_CODE_DEADLINE_EXCEEDED,
    ERROR_CODE_INTERNAL_ERROR,
    ERROR_CODE_SERVICE_UNAVAILABLE,
    RenderError,
    RenderExecutionError,
)
from render_contracts.tokens import sha256_hex

logger = logging.getLogger(__name__)


class RenderDomainFacade:
    """把截图、页面诊断、组件诊断统一走远程渲染执行链路。"""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        coordinator: RenderCoordinator | None = None,
        owns_session: bool | None = None,
    ) -> None:
        self.settings = get_settings()
        self._external_session = session
        self.session = session
        self.owns_session = session is None if owns_session is None else owns_session
        self.coordinator = coordinator or get_render_coordinator()
        self.targets = RenderTargetResolver(self.settings)
        self.credentials = RenderCredentialService(self.settings)

    async def capture_page_preview(
        self,
        *,
        preview_url: str,
        viewport: Mapping[str, int | float],
        logical_owner_key: str,
        business_stage: str = "page.screenshot",
        workspace_id: int,
        project_id: int | None = None,
        page_id: int | None = None,
        artifact_id: str | None = None,
        preview_token: str | None = None,
        extra_http_headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> bytes:
        """执行 page.capture 并返回 PNG 字节。"""

        payload = await self._execute(
            operation=OPERATION_PAGE_CAPTURE,
            logical_owner_key=logical_owner_key,
            business_stage=business_stage,
            workspace_id=workspace_id,
            project_id=project_id,
            page_id=page_id,
            component_id=None,
            preview_url=preview_url,
            viewport=dict(viewport),
            artifact_id=artifact_id,
            preview_token=preview_token,
            extra_http_headers=extra_http_headers,
            # 鉴权头不进入 operation_options，避免明文落库。
            operation_options={
                "capture": "png",
            },
            timeout_seconds=timeout_seconds,
        )
        object_refs = payload.get("_object_refs") or {}
        png_ref = object_refs.get("page.png") or object_refs.get("screenshot.png")
        if isinstance(png_ref, dict):
            storage_key = png_ref.get("storage_key")
            if storage_key:
                from app.services.object_storage_service import ObjectStorageService

                return await ObjectStorageService().read_object(str(storage_key))
            if png_ref.get("content"):
                return bytes.fromhex(str(png_ref["content"]))
        raise AppException(
            status_code=502,
            code="RENDER_RESULT_LOST",
            detail="渲染成功但未返回可用截图产物。",
        )

    async def diagnose_page_preview(
        self,
        *,
        preview_url: str,
        viewport: Mapping[str, int | float],
        logical_owner_key: str,
        workspace_id: int,
        project_id: int | None = None,
        page_id: int | None = None,
        artifact_id: str | None = None,
        preview_token: str | None = None,
        source_override: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        """执行 page.diagnose 并返回布局分析与 warning。"""

        try:
            payload = await self._execute(
                operation=OPERATION_PAGE_DIAGNOSE,
                logical_owner_key=logical_owner_key,
                business_stage="page.render.diagnostics",
                workspace_id=workspace_id,
                project_id=project_id,
                page_id=page_id,
                component_id=None,
                preview_url=preview_url,
                viewport=dict(viewport),
                artifact_id=artifact_id,
                preview_token=preview_token,
                source_override=source_override,
                operation_options={},
                timeout_seconds=timeout_seconds,
            )
        except AppException as exc:
            if _is_infrastructure_error(exc.code):
                return self._page_unavailable_result(
                    exc.detail,
                    defer_artifact_cleanup=exc.code == ERROR_CODE_DEADLINE_EXCEEDED,
                )
            raise

        layout = payload.get("layout") or payload.get("layout_analysis") or {}
        diagnostics = list(payload.get("diagnostics") or [])
        return {
            "status": "ok",
            "retryable": False,
            "diagnostics": diagnostics,
            "layout_analysis": normalize_layout_analysis(layout),
            "environment_summary": payload.get("environment_summary") or {},
        }

    async def _execute(
        self,
        *,
        operation: str,
        logical_owner_key: str,
        business_stage: str,
        workspace_id: int,
        project_id: int | None,
        page_id: int | None,
        component_id: str | None,
        preview_url: str,
        viewport: dict[str, Any],
        artifact_id: str | None,
        preview_token: str | None,
        operation_options: dict[str, Any],
        timeout_seconds: float | None,
        extra_http_headers: Mapping[str, str] | None = None,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        """创建幂等渲染请求并等待协调器提交结果。"""

        read_session, owns = await self._acquire_session()
        write_session = get_session_factory()()
        owns_write = True
        try:
            if workspace_id is None or int(workspace_id) <= 0:
                raise AppException(
                    status_code=500,
                    code="RENDER_INTERNAL_ERROR",
                    detail="渲染请求必须提供合法 workspace_id。",
                )
            request_service = RenderRequestService(write_session)
            snapshot_service = RenderSnapshotService(read_session)
            resolved_token = preview_token or _extract_preview_token(preview_url) or ""
            resolved_artifact = artifact_id or _extract_artifact_id(preview_url)
            if not resolved_artifact:
                # 仅在完全缺失时生成稳定标识；截图/诊断主路径必须传入真实 Runtime artifact_id。
                resolved_artifact = _stable_artifact_fallback(preview_url, resolved_token)
            # 渲染请求写入独立会话：外部会话可能仍带调用方未提交业务写入，不得被顺带 commit。
            if page_id:
                snapshot = await snapshot_service.build_page_snapshot(
                    page_id=int(page_id),
                    artifact_id=resolved_artifact,
                    preview_token=resolved_token,
                    viewport=viewport,
                    operation_options=operation_options,
                    preview_url=preview_url,
                    extra_http_headers=extra_http_headers,
                    source_override=source_override,
                )
            else:
                snapshot = {
                    "artifact_id": resolved_artifact,
                    "input_digest": sha256_hex(
                        f"{sanitize_owner_key(preview_url)}|{resolved_artifact}|{viewport}|{operation}|{operation_options}"
                    ),
                    "preview_credentials": self.credentials.encrypt_sensitive_payload(
                        {
                            "preview_token": resolved_token,
                            "extra_http_headers": dict(extra_http_headers or {}),
                            "preview_url": preview_url,
                        }
                    ),
                    "viewport": viewport,
                    "operation_options": operation_options,
                    # 与 snapshot_service 一致：预览授权必须覆盖渲染总预算，禁止写成“现在”。
                    "expires_at": (
                        datetime.now(UTC)
                        + timedelta(seconds=self.settings.runtime_preview_artifact_ttl_seconds)
                    ).isoformat(),
                    "storage_kind": "runtime_artifact",
                }
            request, _created = await request_service.get_or_create_request(
                logical_owner_key=logical_owner_key,
                business_stage=business_stage,
                operation=operation,
                workspace_id=int(workspace_id),
                project_id=project_id,
                page_id=page_id,
                component_id=component_id,
                owner_kind="domain_facade",
                owner_ref=logical_owner_key,
                snapshot_ref=snapshot,
                input_digest=str(snapshot.get("input_digest") or ""),
                operation_options=operation_options,
                viewport=viewport,
                render_profile_digest=str(self.settings.render_profile_digest or "profile.v1"),
                trace_id=str(uuid.uuid4()),
                timeout_seconds=timeout_seconds,
            )
            # 独立会话提交，保证协调器可见且不污染调用方事务。
            await write_session.commit()
            request_id = int(request.id)
        except Exception:
            if owns_write and write_session is not None:
                await write_session.close()
            if owns and read_session is not None:
                await read_session.close()
            raise

        try:
            payload = await self.coordinator.wait_for_terminal(
                request_id,
                timeout_seconds=timeout_seconds,
                drive_dispatch=True,
            )
        except RenderExecutionError as exc:
            if exc.error.code == ERROR_CODE_DEADLINE_EXCEEDED:
                # 等待方超时不等于 Renderer 已停止；先持久化取消，阻止排队任务继续派发，
                # 让在途 attempt 由协调器/租约流程收敛，避免调用方立刻删除其输入 artifact。
                await self._cancel_request_after_timeout(request_id)
            raise render_error_to_app_exception(
                RenderError.from_code(
                    exc.error.code,
                    message=sanitize_error_message(exc.error.message),
                    stage=exc.error.stage,
                    retryable=exc.error.retryable,
                    trace_id=exc.error.trace_id,
                )
            ) from exc
        finally:
            # 等待段任何出口（含 CancelledError）都必须关闭会话，避免泄漏。
            if owns_write and write_session is not None:
                await write_session.close()
            if owns and read_session is not None:
                await read_session.close()
        # 消费标记使用独立短会话，不复用已关闭的 write_session。
        consume_session = get_session_factory()()
        try:
            await RenderRequestService(consume_session).mark_result_consumed(request_id)
            await consume_session.commit()
        except Exception:  # noqa: BLE001
            logger.warning("渲染结果消费标记失败。", extra={"request_id": request_id}, exc_info=True)
            try:
                await consume_session.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            await consume_session.close()
        return payload

    async def _cancel_request_after_timeout(self, request_id: int) -> None:
        """等待超时时持久化取消标记，避免后台继续使用已结束调用方的输入。"""

        cancel_session = get_session_factory()()
        try:
            await RenderRequestService(cancel_session).cancel_request(request_id)
            await cancel_session.commit()
        except Exception:  # noqa: BLE001
            logger.warning(
                "渲染等待超时后的取消标记写入失败。",
                extra={"event": "render.request.cancel_after_timeout.failed", "request_id": request_id},
                exc_info=True,
            )
            try:
                await cancel_session.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            await cancel_session.close()

    async def _acquire_session(self) -> tuple[AsyncSession, bool]:
        """复用外部会话或创建短生命周期会话。"""

        if self._external_session is not None:
            return self._external_session, False
        factory = get_session_factory()
        return factory(), True

    @staticmethod
    def _page_unavailable_result(
        message: str,
        *,
        defer_artifact_cleanup: bool = False,
    ) -> dict[str, object]:
        """页面校验执行不可用，不映射为源码有错。"""

        from app.services.rendering.layout_contract import empty_layout_analysis
        from app.services.rendering.sanitize import sanitize_error_message

        result: dict[str, object] = {
            "status": "unavailable",
            "retryable": True,
            "diagnostics": [
                {
                    "severity": "warning",
                    "stage": "render",
                    "source": "infrastructure",
                    "code": ERROR_CODE_SERVICE_UNAVAILABLE,
                    "message": f"页面渲染诊断执行不可用：{sanitize_error_message(message)}",
                }
            ],
            "layout_analysis": empty_layout_analysis(
                message="渲染执行不可用，未产出布局分析。",
                truncated=True,
            ),
        }
        if defer_artifact_cleanup:
            result["_render_artifact_cleanup_deferred"] = True
        return result



def _stable_artifact_fallback(preview_url: str, preview_token: str) -> str:
    """缺失 artifact_id 时生成稳定标识，禁止随机 UUID 破坏幂等。"""

    return sha256_hex(f"{sanitize_owner_key(preview_url)}|{preview_token}")[:32]


def _is_infrastructure_error(code: str) -> bool:
    """判断是否属于执行基础设施/资源问题，不应映射为内容有错。"""

    return code in {
        ERROR_CODE_SERVICE_UNAVAILABLE,
        ERROR_CODE_INTERNAL_ERROR,
        "RENDER_ASSET_NOT_READY",
        "RENDER_BROWSER_LOST",
        "RENDER_QUEUE_FULL",
        "RENDER_WORKER_BUSY",
        "RENDER_DEADLINE_EXCEEDED",
        "RENDER_RESULT_LOST",
    }


def _sanitize_owner_key(raw: str) -> str:
    """去掉预览地址查询串中的 token，避免敏感信息进入幂等 owner。"""

    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(raw)
        if parts.query or parts.fragment:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:  # noqa: BLE001
        pass
    return raw[:128]


sanitize_owner_key = _sanitize_owner_key


def _extract_artifact_id(preview_url: str) -> str | None:
    """从预览地址中提取 artifact 标识。"""

    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(preview_url).query)
    values = query.get("artifact") or query.get("artifact_id")
    return values[0] if values else None


def _extract_preview_token(preview_url: str) -> str | None:
    """从预览地址中提取 preview token。"""

    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(preview_url).query)
    values = query.get("token") or query.get("preview_token")
    return values[0] if values else None
