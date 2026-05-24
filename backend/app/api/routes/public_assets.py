"""文件功能：公开的无鉴权资源访问网关。"""

import mimetypes
import re
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.core.exceptions import AppException
from app.models.page import Page
from app.models.asset import WorkspaceAsset
from app.services.asset_service import AssetService, BaseStorageDriver
from app.services.object_storage_service import ObjectStorageService

router = APIRouter()
CACHE_CONTROL_IMMUTABLE = "public, max-age=31536000, immutable"


@router.get("/assets/{workspace_id}/{file_hash}")
async def get_public_asset(
    workspace_id: int,
    file_hash: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    download: int = Query(0, description="1 to force download")
):
    """公开获取静态资源，该入口地址可通过 manifest 的 asset_base_url 获取。"""
    
    service = AssetService(session)
    asset, driver = await service.get_asset_by_hash(workspace_id, file_hash)
    
    is_download = download == 1
    if _should_proxy_runtime_fetchable_asset(asset):
        return await _build_backend_asset_response(
            workspace_id,
            asset,
            driver,
            is_download=is_download,
        )
    
    # S3等第三方存储：如果有直接生成的下载链接，则直接302
    remote_url = await driver.generate_download_url(workspace_id, asset.file_name, asset.original_name, is_download)
    if remote_url:
        return RedirectResponse(url=remote_url)
    
    # 本地存储：获取物理路径并输出
    file_path = await driver.get_physical_path(workspace_id, asset.file_name)
    if not file_path or not file_path.exists():
        from app.core.exceptions import AppException
        raise AppException(status_code=404, code="ASSET_FILE_MISSING", detail="未找到物理文件。")
        
    media_type, _ = mimetypes.guess_type(asset.original_name)
    
    headers = _build_public_asset_headers(asset.original_name, is_download)
        
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=asset.original_name if is_download else None,
        headers=headers
    )


@router.get("/cached-assets/{workspace_id}/{file_hash}")
async def get_public_cached_asset(
    workspace_id: int,
    file_hash: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FileResponse:
    """公开读取截图专用缓存资源，S3 对象会先落到 Backend 本地派生缓存。"""

    service = AssetService(session)
    asset, driver = await service.get_asset_by_hash(workspace_id, file_hash)
    media_type, _ = mimetypes.guess_type(asset.original_name)
    headers = {"Cache-Control": CACHE_CONTROL_IMMUTABLE}

    async with driver.open_for_read(
        workspace_id,
        asset.file_name,
        expected_sha256=asset.file_hash,
        expected_size=asset.file_size,
    ) as local_file_path:
        return FileResponse(
            path=local_file_path,
            media_type=media_type or "application/octet-stream",
            headers=headers,
        )


@router.get("/page-screenshots/{page_id}")
async def get_public_page_screenshot(
    page_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    download: int = Query(0, description="1 to force download"),
) -> Response:
    """公开读取页面截图；S3 私有桶由后端代理返回图片 bytes，并支持下载响应头。"""

    page = await session.scalar(select(Page).where(Page.id == page_id))
    if page is None or not page.screenshot_storage_key:
        raise AppException(status_code=404, code="PAGE_SCREENSHOT_NOT_FOUND", detail="页面截图不存在。")

    content = await ObjectStorageService().read_object(page.screenshot_storage_key)
    headers = {
        "Cache-Control": CACHE_CONTROL_IMMUTABLE,
        "Access-Control-Allow-Origin": "*",
    }
    if download == 1:
        headers["Content-Disposition"] = _build_content_disposition(_build_page_screenshot_filename(page))

    return Response(
        content=content,
        media_type="image/png",
        headers=headers,
    )


def _should_proxy_runtime_fetchable_asset(asset: WorkspaceAsset) -> bool:
    """判断资源是否应由 Backend 直接代理，确保 Runtime 文本渲染器可稳定 fetch。"""

    asset_type = str(asset.asset_type or "").strip().lower()
    if asset_type in {"drawio", "mermaid", "chart", "formula"}:
        return True

    if asset_type != "icon":
        return False

    content_type = str(asset.content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "image/svg+xml":
        return True

    return str(asset.original_name or "").strip().lower().endswith(".svg")


async def _build_backend_asset_response(
    workspace_id: int,
    asset: WorkspaceAsset,
    driver: BaseStorageDriver,
    *,
    is_download: bool,
) -> FileResponse | Response:
    """从 Backend 返回资源内容；本地文件优先走 FileResponse，远程存储读取 bytes 后返回。"""

    media_type, _ = mimetypes.guess_type(asset.original_name)
    resolved_media_type = media_type or asset.content_type or "application/octet-stream"
    headers = _build_public_asset_headers(asset.original_name, is_download)

    local_file_path = await driver.get_physical_path(workspace_id, asset.file_name)
    if local_file_path and local_file_path.exists():
        return FileResponse(
            path=local_file_path,
            media_type=resolved_media_type,
            filename=asset.original_name if is_download else None,
            headers=headers,
        )

    content = await driver.read_content(workspace_id, asset.file_name)
    return Response(
        content=content,
        media_type=resolved_media_type,
        headers=headers,
    )


def _build_public_asset_headers(original_name: str, is_download: bool) -> dict[str, str]:
    """构建公开资源响应头，保持资源可长期缓存并按需触发下载。"""

    headers = {
        "Cache-Control": CACHE_CONTROL_IMMUTABLE,
        "Access-Control-Allow-Origin": "*",
    }
    if is_download:
        headers["Content-Disposition"] = _build_content_disposition(original_name)
    return headers


def _build_page_screenshot_filename(page: Page) -> str:
    """根据页面标题生成截图下载文件名，标题为空时回退到页面编码。"""

    raw_name = str(page.title or page.code or f"page-{page.id}").strip()
    safe_name = re.sub(r'[\\/:*?"<>|\s]+', "-", raw_name).strip("-") or f"page-{page.id}"
    version_suffix = f"-v{page.screenshot_version_no}" if page.screenshot_version_no else ""
    return f"{safe_name}{version_suffix}.png"


def _build_content_disposition(original_name: str) -> str:
    """生成兼容中文文件名的下载响应头。"""

    encoded_name = urllib.parse.quote(original_name)
    return f"attachment; filename*=UTF-8''{encoded_name}"
