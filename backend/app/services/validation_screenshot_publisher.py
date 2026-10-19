"""文件功能：在事务外持久化校验附图，事务内复核候选身份并与页面/任务原子发布。"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.page import Page
from app.models.page_screenshot_artifact import PageScreenshotArtifact
from app.services.code_check_fingerprint import CodeCheckFingerprintBuilder
from app.services.code_check_result_cache import compute_check_fingerprint
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_fingerprint_service import PageScreenshotFingerprintService
from render_contracts.tokens import sha256_hex

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedValidationScreenshot:
    """截图字节不进入业务编排；仅携带已经落盘的临时对象及待复核身份。"""

    artifact_id: str
    identity: str
    workspace_id: int
    sha256: str
    width: int
    height: int


def screenshot_status(*, version_no: int, reason: str, skipped: bool = False) -> dict:
    """pending 仅表示待后续按需生成，不宣称已入队。"""
    return {"status": "skipped" if skipped else "pending", "version_no": version_no, "reason_code": reason}


async def prepare_validation_screenshot(validation: dict, *, workspace_id: int) -> PreparedValidationScreenshot | None:
    """在业务事务之外读取并存储 PNG，先登记 TTL 持有以覆盖存储成功后崩溃。"""
    ref = validation.get("_candidate_screenshot")
    if not isinstance(ref, dict) or (validation.get("_screenshot_phase") or {}).get("status") != "available":
        return None
    try:
        from app.services.runtime_release_identity import refresh_runtime_release_identity
        if await refresh_runtime_release_identity() == "unknown":
            return None
        if int(ref.get("workspace_id") or 0) != workspace_id or not validation.get("_capture_identity"):
            return None
        if datetime.fromisoformat(ref["expires_at"]) <= utc_now():
            return None
        store = ObjectStorageService()
        content = await store.read_object(ref["storage_key"])
        if len(content) != ref["byte_length"] or sha256_hex(content) != ref["sha256"]:
            return None
        artifact_id = uuid.uuid4().hex
        key = f"page-screenshots/staged/{workspace_id}/{artifact_id}/{ref['sha256']}.png"
        async with get_session_factory()() as session:
            session.add(PageScreenshotArtifact(artifact_id=artifact_id, workspace_id=workspace_id,
                        sha256=ref["sha256"], storage_key=key, expires_at=utc_now() + timedelta(minutes=10)))
            await session.commit()
        await store.put_object(key, content=content, content_type="image/png")
        return PreparedValidationScreenshot(artifact_id, validation["_capture_identity"], workspace_id,
                                            ref["sha256"], int(ref["width"]), int(ref["height"]))
    except Exception:
        logger.warning("校验附图准备失败，页面仍可按校验门禁保存。", extra={"event": "validation.screenshot.prepare.failed"}, exc_info=True)
        return None


async def publish_validation_screenshot(session: AsyncSession, *, page: Page, validation: dict,
                                        prepared: PreparedValidationScreenshot | None) -> dict:
    """调用方先持有 Job/页面围栏；同事务核验最终源码、依赖与渲染上下文后发布指针。"""
    if prepared is None:
        phase = validation.get("_screenshot_phase") or {}
        return screenshot_status(version_no=page.current_version_no, reason=phase.get("reason_code") or "SCREENSHOT_NOT_AVAILABLE",
                                  skipped="_capture_identity" not in validation)
    if prepared.workspace_id != page.workspace_id:
        return screenshot_status(version_no=page.current_version_no, reason="SCREENSHOT_SCOPE_MISMATCH")
    base = await CodeCheckFingerprintBuilder(session).build_page_fingerprint(
        workspace_id=page.workspace_id, project_id=page.project_id, source=page.page_content,
        importer_module_path=f"src/views/{page.code}.{page.file_type}",
        page_metadata={"code": page.code, "title": page.title, "speaker_notes": page.speaker_notes})
    identity = compute_check_fingerprint({"diagnostics": base, "capture_screenshot": True, "capture_policy": "page-static-capture.v1"})
    if identity != prepared.identity:
        logger.info("页面渲染输入变化，拒绝发布候选图。", extra={"event": "validation.screenshot.stale", "page_id": page.id})
        return screenshot_status(version_no=page.current_version_no, reason="SCREENSHOT_INPUT_CHANGED")
    artifact = await session.get(PageScreenshotArtifact, prepared.artifact_id, populate_existing=True)
    if (artifact is None or artifact.expires_at is None or artifact.expires_at <= utc_now() or artifact.page_id is not None):
        return screenshot_status(version_no=page.current_version_no, reason="SCREENSHOT_CANDIDATE_EXPIRED")
    snapshot = await PageScreenshotFingerprintService(session).build_page_snapshot(page)
    if (prepared.width, prepared.height) != (snapshot.page_config.width, snapshot.page_config.height):
        return screenshot_status(version_no=page.current_version_no, reason="SCREENSHOT_VIEWPORT_CHANGED")
    artifact.page_id, artifact.version_no, artifact.expires_at = page.id, page.current_version_no, None
    page.screenshot_storage_key = artifact.storage_key
    page.screenshot_version_no = page.current_version_no
    page.screenshot_config_hash = snapshot.config_hash
    page.screenshot_viewport_width, page.screenshot_viewport_height = prepared.width, prepared.height
    page.screenshot_updated_at = utc_now()
    await session.flush()
    return {"status": "ready", "version_no": page.current_version_no, "screenshot_id": prepared.sha256,
            "width": prepared.width, "height": prepared.height, "reason_code": None}
