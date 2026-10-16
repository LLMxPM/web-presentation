"""文件功能：按内容身份寻址页面截图，兼容旧当前指针并交付稳定 ETag 的私有响应。"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import Request

from app.core.exceptions import AppException
from app.models.page import Page
from app.services.file_auth_service import FileAuthService
from app.services.object_storage_service import ObjectStorageService


def screenshot_object_key(page_id: int, digest: str) -> str:
    """生成页面范围内的内容寻址对象键；相同 URL 永远对应相同字节。"""
    return f"page-screenshots/{int(page_id)}/objects/{digest}.png"


def screenshot_content_id(page: Page) -> str:
    """从新对象键提取内容 hash；旧数据使用可重新验证的 latest 指针。"""
    key = str(page.screenshot_storage_key or "")
    match = re.fullmatch(rf"page-screenshots/{int(page.id)}/objects/([a-f0-9]{{64}})\.png", key)
    return match.group(1) if match else "latest"


def resolve_screenshot_object(page: Page, screenshot_id: str) -> tuple[str, str]:
    """仅解析已授权页面下的当前指针或内容 hash，不把时间戳、任务 ID 冒充产物身份。"""
    clean_id = str(screenshot_id).strip()
    if clean_id in {"latest", "current"}:
        key = str(page.screenshot_storage_key or "")
    elif re.fullmatch(r"[a-f0-9]{64}", clean_id):
        key = screenshot_object_key(page.id, clean_id)
    else:
        key = ""
    if not key:
        raise AppException(404, "PAGE_SCREENSHOT_NOT_FOUND", "截图产物不存在。", headers={"Cache-Control": "no-store"})
    name = re.sub(r'[\\/:*?"<>|\s]+', '-', str(page.title or page.code or f'page-{page.id}')).strip('-')
    version = page.screenshot_version_no
    suffix = f"-v{version}" if version and clean_id in {"latest", "current", screenshot_content_id(page)} else f"-{clean_id[:8]}"
    return key, f"{name}{suffix}.png"


async def serve_screenshot(request: Request, page: Page, screenshot_id: str, *, download: bool = False) -> Any:
    """在调用方完成页面鉴权后读取截图；旧可变 key 不进入不可变对象缓存。"""
    key, filename = resolve_screenshot_object(page, screenshot_id)
    match = re.fullmatch(rf"page-screenshots/{int(page.id)}/objects/([a-f0-9]{{64}})\.png", key)
    storage = ObjectStorageService()
    if match:
        return await FileAuthService.serve_protected_file(
            request=request,
            open_file=storage.open_object_for_read(key, expected_sha256=match.group(1)),
            etag=match.group(1), media_type="image/png", original_name=filename,
            is_download=download,
        )
    # 存量对象按旧规则可能被覆盖；直接读取原件并以实际字节生成 ETag，防止缓存旧图。
    content = await storage.read_object(key)
    return FileAuthService.serve_protected_bytes(
        request=request, content=content, etag=hashlib.sha256(content).hexdigest(),
        media_type="image/png", original_name=filename, is_download=download,
    )
