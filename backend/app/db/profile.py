"""文件功能：派生单一部署 profile，作为数据库形态与 Backend 进程拓扑判定的唯一事实源。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.engine import make_url

from app.core.config import AppSettings, get_settings


@dataclass(frozen=True, slots=True)
class DeploymentProfile:
    """一次部署的画像：数据库形态 + Backend 进程拓扑。

    SQLite 与 PostgreSQL 不是两种平等的数据库后端，而是两种部署形态：SQLite 是单写库，
    天然只支持单 Backend 进程；多副本控制面只能由 PostgreSQL 承担。本对象把这一事实
    收敛到一处，避免各服务各自用 URL 前缀或环境变量重新推断。
    """

    is_distributed: bool
    declared_multi_instance: bool
    explicit_worker_count: tuple[str, int] | None

    @property
    def is_lite(self) -> bool:
        """是否为 SQLite Lite 形态（单写库、单 Backend 进程）。"""

        return not self.is_distributed

    @property
    def backend_multi_process_allowed(self) -> bool:
        """是否允许多 Backend 进程/副本；SQLite Lite 恒不允许。"""

        return self.is_distributed

    @property
    def multi_process_requested(self) -> bool:
        """是否已显式请求多 Backend 进程：副本声明或 worker 数 > 1。"""

        return self.declared_multi_instance or self.explicit_worker_count is not None

    @property
    def name(self) -> str:
        """返回可用于健康检查与启动日志的 profile 名称。"""

        return "postgresql-distributed" if self.is_distributed else "sqlite-lite"


def is_postgresql_database_url(database_url: str) -> bool:
    """判断数据库连接串是否指向 PostgreSQL。"""

    try:
        return make_url(str(database_url or "")).drivername.startswith("postgresql")
    except Exception:  # noqa: BLE001 - URL 非法时按非 PostgreSQL 处理，由连接阶段报错
        return False


def read_explicit_worker_count() -> tuple[str, int] | None:
    """读取显式声明的 Backend 进程数；未声明或声明为单进程时返回 None。"""

    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        try:
            workers = int(raw)
        except ValueError:
            continue
        if workers > 1:
            return key, workers
    return None


def resolve_deployment_profile(settings: AppSettings | None = None) -> DeploymentProfile:
    """派生当前部署 profile；纯配置计算，不建立数据库或 Redis 连接。

    只应在 lifespan 或请求处理中调用，不要在导入期取值：`main.py` 底部有模块级
    `create_app()`，导入期读配置会把部署校验提前到任何 `import app` 的脚本与测试上。
    """

    resolved = settings or get_settings()
    return DeploymentProfile(
        is_distributed=is_postgresql_database_url(resolved.database_url),
        declared_multi_instance=bool(resolved.backend_multi_instance),
        explicit_worker_count=read_explicit_worker_count(),
    )
