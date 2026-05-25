"""文件功能：识别和格式化数据库连接类异常，输出可排查且不泄露凭据的日志。"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


class DatabaseConnectivityError(RuntimeError):
    """表示 Backend 当前无法建立或复用数据库连接。"""


_CONNECTION_KEYWORDS = (
    "connection refused",
    "connect call failed",
    "could not connect",
    "could not translate host name",
    "name or service not known",
    "nodename nor servname",
    "server closed the connection",
    "temporary failure in name resolution",
    "too many connections",
)
_TIMEOUT_KEYWORDS = (
    "connection timed out",
    "connect timed out",
    "connect timeout",
    "timed out",
)


def is_database_connectivity_error(error: BaseException) -> bool:
    """判断异常是否属于数据库连接不可用，避免把普通 SQL 语法错误误报为连库问题。"""

    if isinstance(error, DatabaseConnectivityError):
        return True
    if not isinstance(error, SQLAlchemyError):
        return False

    if bool(getattr(error, "connection_invalidated", False)):
        return True

    if any(isinstance(item, (ConnectionError, TimeoutError, OSError)) for item in _iter_exception_chain(error)):
        return True

    normalized = _collect_exception_text(error).lower()
    return any(keyword in normalized for keyword in (*_CONNECTION_KEYWORDS, *_TIMEOUT_KEYWORDS))


def format_database_connectivity_error(error: BaseException, database_url: str, *, phase: str) -> str:
    """生成数据库连接错误日志；输入原始异常和 URL，输出隐藏敏感信息后的中文说明。"""

    reason = "数据库连接超时" if is_database_timeout_error(error) else "数据库连接失败"
    target = describe_database_target(database_url)
    detail = _summarize_error(error)
    return (
        f"{phase}{reason}：{detail}；目标={target}。"
        "请检查 DATABASE_URL、数据库服务状态、容器网络/防火墙，以及 DATABASE_CONNECT_TIMEOUT_SECONDS 配置。"
    )


def is_database_timeout_error(error: BaseException) -> bool:
    """识别数据库连接超时，用于在日志中区分超时和拒绝连接等故障。"""

    if any(type(item).__name__.lower().endswith("timeouterror") for item in _iter_exception_chain(error)):
        return True
    normalized = _collect_exception_text(error).lower()
    return any(keyword in normalized for keyword in _TIMEOUT_KEYWORDS)


def describe_database_target(database_url: str) -> str:
    """从数据库 URL 提取非敏感目标信息，避免日志打印用户名、密码或完整连接串。"""

    try:
        url = make_url(database_url)
    except Exception:  # noqa: BLE001
        return "driver=<无法解析> host=<无法解析> port=<无法解析> database=<无法解析>"

    if url.drivername.startswith("sqlite"):
        return f"driver={url.drivername} database={url.database or ':memory:'}"

    host = url.host or "<未配置>"
    port = str(url.port or "<默认>")
    database = url.database or "<未配置>"
    return f"driver={url.drivername} host={host} port={port} database={database}"


def _iter_exception_chain(error: BaseException) -> Iterable[BaseException]:
    """遍历异常链，兼容 SQLAlchemy 对底层驱动异常的包装方式。"""

    pending: list[BaseException] = [error]
    visited: set[int] = set()
    while pending:
        current = pending.pop(0)
        if id(current) in visited:
            continue
        visited.add(id(current))
        yield current
        for related in (current.__cause__, current.__context__, getattr(current, "orig", None)):
            if isinstance(related, BaseException) and id(related) not in visited:
                pending.append(related)


def _collect_exception_text(error: BaseException) -> str:
    """合并异常链中的类名和文本，供连接错误关键字匹配使用。"""

    return " ".join(f"{type(item).__name__}: {item}" for item in _iter_exception_chain(error))


def _summarize_error(error: BaseException) -> str:
    """取异常链中最靠近驱动层的一段信息，控制单条日志长度。"""

    chain = list(_iter_exception_chain(error))
    leaf = chain[-1] if chain else error
    text = str(leaf).strip() or type(leaf).__name__
    collapsed = " ".join(text.split())
    if len(collapsed) > 240:
        return f"{collapsed[:237]}..."
    return collapsed
