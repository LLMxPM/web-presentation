"""文件功能：在慢操作边界读取 Runtime 发布身份，数据库提交阶段只消费已核实的身份。"""

import httpx

from app.core.config import get_settings

_identity = "unknown"


def current_runtime_release_identity() -> str:
    """供同步指纹计算读取最近核实的 Runtime 构建身份。"""
    return _identity


async def refresh_runtime_release_identity() -> str:
    """从受信预览源站获取构建；不可用时写 unknown，防止沿用旧图片身份。"""
    global _identity
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.runtime_request_timeout_seconds) as client:
            response = await client.get(f"{settings.resolve_runtime_role_base_url('preview')}/__runtime_healthz")
            response.raise_for_status()
            data = response.json()
        kit, build = data.get("runtime_kit_version"), data.get("build_id")
        _identity = f"{kit}+{build}" if kit and build else "unknown"
    except (httpx.HTTPError, ValueError, AttributeError):
        _identity = "unknown"
    return _identity
