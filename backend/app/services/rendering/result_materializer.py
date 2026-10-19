"""文件功能：验证 Renderer 结果身份并持久化有界产物，单独隔离诊断附带 PNG 的失败。"""

import logging
from datetime import timedelta
from typing import Any

from render_contracts.errors import RenderError, RenderExecutionError
from render_contracts.screenshot import ScreenshotPhaseResult
from render_contracts.tokens import sha256_hex

from app.core.time_utils import utc_now
from app.services.object_storage_service import ObjectStorageService
from app.services.image_metadata import read_image_dimensions

logger = logging.getLogger(__name__)


def _invalid(message: str) -> RenderExecutionError:
    """输入身份或协议不可信时使整个 attempt 失败，不降级为图片失败。"""
    return RenderExecutionError(RenderError.from_code("RENDER_RESULT_LOST", message=message, stage="commit"))


async def materialize_result(*, client: Any, settings: Any, endpoint: Any, request: Any, attempt: Any, receipt: Any) -> dict:
    """先核验结果身份，再保存产物；诊断成功后的图片 I/O 故障只更新截图阶段。"""
    descriptor = dict(receipt.result_descriptor or {})
    payload = dict(descriptor.get("result") or descriptor)
    joint = request.operation == "page.diagnose" and bool((request.operation_options or {}).get("capture_screenshot"))
    if payload.get("request_digest") and payload["request_digest"] != request.request_digest:
        raise _invalid("Renderer request_digest 与请求不一致。")
    if joint:
        for key, expected in {"request_id": str(request.id), "attempt_id": attempt.attempt_uid,
                              "input_digest": request.input_digest, "render_profile_digest": request.render_profile_digest,
                              "request_digest": request.request_digest}.items():
            if str(payload.get(key) or "") != str(expected):
                raise _invalid(f"Renderer {key} 与当前 attempt 不一致。")
        if not isinstance(payload.get("layout"), dict):
            raise _invalid("联合结果缺少已完成的布局诊断。")
        if payload.get("screenshot") is None:
            payload["screenshot"] = ScreenshotPhaseResult("skipped", "WORKER_CAPTURE_UNSUPPORTED").to_dict()
        phase = ScreenshotPhaseResult.from_dict(payload["screenshot"])
        if phase.status != "available":
            payload["artifacts"] = []

    refs = {}
    storage = ObjectStorageService()
    try:
        for artifact in payload.get("artifacts") or []:
            ref = await _store_artifact(client=client, settings=settings, storage=storage, endpoint=endpoint,
                                        request=request, attempt=attempt, artifact=artifact, validate_png=joint)
            refs[artifact["name"]] = ref
        if joint and payload["screenshot"]["status"] == "available" and "page.png" not in refs:
            raise _invalid("截图阶段声明 available，但缺少 page.png。")
    except Exception as exc:
        if not joint:
            raise
        payload["screenshot"] = ScreenshotPhaseResult("failed", "SCREENSHOT_MATERIALIZATION_FAILED", True).to_dict()
        payload["artifacts"] = []
        logger.warning("布局诊断成功，附带图片下载或存储失败。", extra={"event": "render.screenshot.materialization.failed",
                       "request_id": request.id, "attempt_id": attempt.id}, exc_info=True)
        for ref in refs.values():
            try:
                await storage.delete_object(ref["storage_key"])
            except Exception:
                logger.warning("图片失败后的对象清理待 TTL 对账。", exc_info=True)
        refs = {}
    return {"payload": payload, "object_refs": refs, "environment_summary": dict(payload.get("environment_summary") or {})}


async def _store_artifact(*, client: Any, settings: Any, storage: Any, endpoint: Any, request: Any,
                          attempt: Any, artifact: Any, validate_png: bool) -> dict:
    """验证大小、hash、PNG 解码和视口后写入独立于输入 artifact 的临时对象。"""
    if not isinstance(artifact, dict):
        raise _invalid("Renderer 返回了非法产物描述。")
    name = str(artifact.get("name") or "")
    if not name or "/" in name or "\\" in name or ".." in name:
        raise _invalid("Renderer 返回了非法产物名称。")
    limit = int(settings.render_artifact_max_bytes)
    expected_len = int(artifact.get("byte_length") or 0)
    if expected_len < 0 or expected_len > limit:
        raise _invalid("产物描述大小超限。")
    content = await client.fetch_artifact(endpoint, attempt.attempt_uid, name)
    if len(content) > limit or len(content) != expected_len:
        raise _invalid("产物实际大小与描述不一致。")
    digest = sha256_hex(content)
    if not artifact.get("sha256") or digest != artifact["sha256"]:
        raise _invalid("产物摘要校验失败。")
    if validate_png:
        if name != "page.png" or artifact.get("content_type") != "image/png":
            raise _invalid("附带截图必须是 page.png。")
        viewport = request.viewport or {}
        dpr = float(viewport.get("device_scale_factor", 1))
        if read_image_dimensions(content, "image/png") != (int(viewport["width"] * dpr), int(viewport["height"] * dpr)):
            raise _invalid("PNG 画布与请求视口不一致。")
    storage_key = await storage.put_object(f"render-results/{request.workspace_id}/{request.id}/{attempt.id}/{name}",
                                           content=content, content_type=str(artifact.get("content_type") or "application/octet-stream"))
    return {"workspace_id": request.workspace_id, "request_id": request.id, "attempt_id": attempt.id,
            "sha256": digest, "byte_length": len(content), "content_type": artifact.get("content_type"),
            "storage_key": storage_key, "expires_at": (utc_now() + timedelta(minutes=10)).isoformat(),
            "width": artifact.get("width"), "height": artifact.get("height")}
