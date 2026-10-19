"""文件功能：回收过期未发布截图和诊断临时 PNG，覆盖取消、提交失败与进程崩溃。"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import String, cast, delete, select

from app.core.time_utils import utc_now
from app.models.page_screenshot_artifact import PageScreenshotArtifact
from app.models.render_execution import RenderResult
from app.services.object_storage_service import ObjectStorageService

logger = logging.getLogger(__name__)


async def cleanup_validation_screenshots(session_factory) -> int:
    """只清理已过期且未绑定页面的对象；存储删除失败保留记录供下轮重试。"""
    now = utc_now()
    candidates = []
    async with session_factory() as session:
        rows = list(await session.scalars(select(PageScreenshotArtifact).where(
            PageScreenshotArtifact.page_id.is_(None), PageScreenshotArtifact.expires_at <= now).limit(100)))
        candidates = [(row.artifact_id, row.storage_key) for row in rows]
        results = list(await session.scalars(select(RenderResult).where(RenderResult.operation == "page.diagnose",
                    cast(RenderResult.object_refs, String).notin_(("{}", "null")),
                    RenderResult.created_at <= now - timedelta(minutes=10)).limit(100)))
        result_refs = [(row.id, dict(row.object_refs or {})) for row in results]
    storage, removed = ObjectStorageService(), 0
    for artifact_id, key in candidates:
        try:
            # 发布入口拒绝过期对象；删除存储不与任何有效发布并发。
            await storage.delete_object(key)
            async with session_factory() as session:
                await session.execute(delete(PageScreenshotArtifact).where(PageScreenshotArtifact.artifact_id == artifact_id,
                                      PageScreenshotArtifact.page_id.is_(None), PageScreenshotArtifact.expires_at <= now))
                await session.commit()
            removed += 1
        except Exception:
            logger.warning("过期截图对象回收失败，保留下轮重试。", exc_info=True)
    for result_id, refs in result_refs:
        expired = [name for name, ref in refs.items() if ref.get("expires_at") and datetime.fromisoformat(ref["expires_at"]) <= now]
        deleted = []
        for name in expired:
            try:
                await storage.delete_object(refs[name]["storage_key"])
                deleted.append(name)
                removed += 1
            except Exception:
                logger.warning("诊断临时图片回收失败，保留下轮重试。", exc_info=True)
        if deleted:
            async with session_factory() as session:
                row = await session.get(RenderResult, result_id)
                if row:
                    row.object_refs = {name: ref for name, ref in (row.object_refs or {}).items() if name not in deleted}
                    await session.commit()
    return removed
