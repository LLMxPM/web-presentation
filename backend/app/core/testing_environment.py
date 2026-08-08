"""文件功能：判定当前运行环境是否为 E2E 测试环境，为 mock 安全门与就绪端点提供指纹依据。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from app.core.config import AppSettings

E2E_DATABASE_MARKER = "_e2e"
E2E_REDIS_DATABASE_SUFFIX = "/15"
E2E_REDIS_KEY_PREFIX = "web_presentation_e2e"


def extract_database_name(database_url: str) -> str:
    """从数据库连接串提取数据库名；解析失败时返回空字符串。"""

    try:
        parsed = urlparse(str(database_url or "").strip())
    except ValueError:
        return ""
    segments = [segment for segment in parsed.path.split("/") if segment]
    return unquote(segments[-1]) if segments else ""


def is_e2e_database(settings: "AppSettings | None" = None) -> bool:
    """判断当前配置的数据库名是否带有 E2E 标记。"""

    from app.core.config import get_settings

    resolved = settings or get_settings()
    return E2E_DATABASE_MARKER in extract_database_name(resolved.database_url)


def is_e2e_redis(settings: "AppSettings | None" = None) -> bool:
    """判断当前 Redis 配置是否指向 E2E 专用库与 key 前缀。"""

    from app.core.config import get_settings

    resolved = settings or get_settings()
    redis_url = str(resolved.redis_url or "").strip()
    return redis_url.endswith(E2E_REDIS_DATABASE_SUFFIX) and resolved.redis_key_prefix == E2E_REDIS_KEY_PREFIX


def database_profile(settings: "AppSettings | None" = None) -> str:
    """返回数据库环境指纹，仅区分 e2e 与非 e2e。"""

    return "e2e" if is_e2e_database(settings) else "unknown"


def redis_profile(settings: "AppSettings | None" = None) -> str:
    """返回 Redis 环境指纹，仅区分 e2e 与非 e2e。"""

    return "e2e" if is_e2e_redis(settings) else "unknown"


def require_e2e_database() -> None:
    """供业务服务调用：非 E2E 数据库环境下拒绝 e2e-mock 专属数据写入。"""

    if is_e2e_database():
        return
    from app.core.exceptions import AppException

    raise AppException(
        status_code=400,
        code="AI_LLM_E2E_MOCK_ENVIRONMENT_REQUIRED",
        detail="e2e-mock-* 模型只能在 E2E 测试数据库中创建或选择。",
    )
