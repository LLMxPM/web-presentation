"""文件功能：Renderer 内部 HTTP API：能力、接管、查询、取消、产物与消费确认。"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from wp_renderer.config import get_renderer_settings
from wp_renderer.control.slot import SlotController
from wp_renderer.security.auth import require_service_token
from render_contracts.constants import RESOURCE_STATE_RELEASED
from render_contracts.schema import ExecutionRequest

logger = logging.getLogger(__name__)

router = APIRouter()
_slot: SlotController | None = None


def get_slot() -> SlotController:
    """获取当前进程槽位控制器；未注入时创建进程内单例，避免每次请求新建状态。"""

    global _slot
    if _slot is None:
        settings = get_renderer_settings()
        _slot = SlotController(
            worker_id=settings.render_worker_id,
            worker_epoch=settings.render_worker_epoch,
        )
    return _slot


def set_slot(slot: SlotController) -> None:
    """注入槽位控制器（应用启动时调用）。"""

    global _slot
    _slot = slot


@router.get("/internal/render/v1/capabilities")
async def capabilities(_subject: str = Depends(require_service_token)) -> dict[str, Any]:
    """返回 Worker 能力、协议版本与槽位状态。"""

    return get_slot().capabilities()


@router.get("/livez")
async def livez() -> dict[str, str]:
    """控制进程存活探针。"""

    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, Any]:
    """执行环境健康探针；忙碌通过槽位状态表达，不触发重启语义。"""

    slot = get_slot()
    return {
        "status": "ok",
        "slot_state": "busy" if slot.busy else "idle",
        "worker_id": slot.worker_id,
        "worker_epoch": slot.worker_epoch,
    }


@router.post("/internal/render/v1/executions")
async def accept_execution(
    payload: dict[str, Any],
    _subject: str = Depends(require_service_token),
) -> dict[str, Any]:
    """接管 attempt；无槽位返回 429 且明确未接管。"""

    try:
        request = ExecutionRequest.from_dict(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail={"code": "RENDER_CONTRACT_MISMATCH", "message": str(exc)}) from exc
    slot = get_slot()
    status_code, receipt = await slot.accept(request)
    if status_code == 429:
        raise HTTPException(
            status_code=429,
            detail={"code": "RENDER_WORKER_BUSY", "message": "Renderer 槽位繁忙，明确未接管。"},
        )
    if status_code == 403:
        detail = receipt.error if receipt is not None else {"code": "RENDER_CONTRACT_MISMATCH"}
        raise HTTPException(status_code=403, detail=detail)
    if status_code == 409 or receipt is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "RENDER_CONTRACT_MISMATCH", "message": "相同 attempt ID 的 digest 不匹配。"},
        )
    return receipt.to_dict()


@router.get("/internal/render/v1/executions/{attempt_id}")
async def get_execution(
    attempt_id: str,
    _subject: str = Depends(require_service_token),
) -> dict[str, Any]:
    """返回执行阶段、清理状态、终态或结果描述符；未知 404，已回收 410。"""

    slot = get_slot()
    execution = slot.get_execution(attempt_id)
    if execution is None:
        if slot.was_recycled(attempt_id):
            raise HTTPException(
                status_code=410,
                detail={"code": "RENDER_RESULT_LOST", "message": "结果已回收。"},
            )
        raise HTTPException(status_code=404, detail={"code": "RENDER_RESULT_LOST", "message": "未知 attempt。"})
    return slot.build_receipt(execution).to_dict()


@router.put("/internal/render/v1/executions/{attempt_id}/cancellation")
async def cancel_execution(
    attempt_id: str,
    payload: dict[str, Any] | None = None,
    _subject: str = Depends(require_service_token),
) -> dict[str, Any]:
    """幂等取消；记录先于 POST 到达的取消标记并打断执行等待。"""

    get_slot().request_cancel(attempt_id)
    return {"attempt_id": attempt_id, "cancel_requested": True}


@router.get("/internal/render/v1/executions/{attempt_id}/artifacts/{name}")
async def get_artifact(
    attempt_id: str,
    name: str,
    _subject: str = Depends(require_service_token),
) -> Response:
    """流式读取有界产物；读取长度不超过 max_png_bytes，未知 404 / 已回收 410。"""

    settings = get_renderer_settings()
    slot = get_slot()
    execution = slot.get_execution(attempt_id)
    if execution is None:
        if slot.was_recycled(attempt_id):
            raise HTTPException(
                status_code=410,
                detail={"code": "RENDER_RESULT_LOST", "message": "结果已回收。"},
            )
        raise HTTPException(status_code=404, detail={"code": "RENDER_RESULT_LOST", "message": "未知 attempt。"})
    path = slot.artifact_path(attempt_id, name)
    if path is None or not path.exists():
        if slot.was_recycled(attempt_id) or execution.resource_state == RESOURCE_STATE_RELEASED:
            raise HTTPException(
                status_code=410,
                detail={"code": "RENDER_RESULT_LOST", "message": "产物已回收。"},
            )
        raise HTTPException(status_code=404, detail={"code": "RENDER_RESULT_LOST", "message": "产物不存在。"})
    max_bytes = int(settings.max_png_bytes)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "RENDER_RESULT_LOST", "message": "产物不存在。"},
        ) from exc
    if size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={"code": "RENDER_OUTPUT_LIMIT_EXCEEDED", "message": "产物超过 max_png_bytes 上限。"},
        )
    content = path.read_bytes()[:max_bytes]
    media_type = "image/png" if name.endswith(".png") else "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "content-length": str(len(content)),
            "x-content-sha256": hashlib.sha256(content).hexdigest(),
        },
    )


@router.put("/internal/render/v1/executions/{attempt_id}/result-consumption")
async def confirm_consumption(
    attempt_id: str,
    payload: dict[str, Any] | None = None,
    _subject: str = Depends(require_service_token),
) -> dict[str, Any]:
    """Backend 确认结果持久化，提前释放临时产物。"""

    ok = get_slot().mark_consumed(attempt_id)
    return {"attempt_id": attempt_id, "consumed": ok}
