"""文件功能：在Backend启动时收敛无法跨进程恢复的普通智能体Run。

多副本语义：只收敛「无主遗留」与「本机已死进程」的 Run，禁止全局扫杀其它副本
正在执行的活跃 Run。产品决策（H1）承诺普通 Run「会丢」，因此不做跨进程续跑；
已登记进程实例由 `process_reaper` 按存活租约独立收敛；本模块处理历史未登记 owner。
"""

from __future__ import annotations

import os
import socket

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.platform_runtime import PlatformAgentRuntimeStore
from app.db.profile import resolve_deployment_profile
from app.models.ai_agent_runtime import AiAgentRun
from app.models.ai_process_owner import AiAgentProcessOwner


def parse_process_owner(owner: str | None) -> tuple[str, int] | None:
    """解析 process_owner（hostname:pid:uuid）为 (hostname, pid)；解析失败返回 None。"""

    normalized = str(owner or "").strip()
    if not normalized:
        return None
    parts = normalized.rsplit(":", 2)
    if len(parts) != 3:
        return None
    host, pid_text, _instance = parts
    try:
        pid = int(pid_text)
    except ValueError:
        return None
    if pid <= 0 or not host:
        return None
    return host, pid


def process_is_alive(pid: int) -> bool:
    """判断本机进程是否仍存活；禁止在 Windows 上用 os.kill(pid, 0)（会直接杀进程）。"""

    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000，仅查询不终止。
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 存在但无权限发送信号，视为仍存活。
        return True
    except OSError:
        return False
    return True


def should_recover_run(
    *,
    process_owner: str | None,
    local_hostname: str,
    current_pid: int,
    include_unowned: bool,
) -> bool:
    """判定启动恢复是否允许收敛该 Run。

    规则：
    - 无主（历史数据/未打标）Run：仅在 `include_unowned` 时收敛，多副本默认拒绝。
    - 主机名不属于本机：一律跳过，保护其它副本活跃 Run。
    - 本机且进程仍存活（含当前进程、同机 sibling worker）：跳过。
    - 本机且进程已死：收敛为进程停止终态。
    - 归属串无法解析：按无主处理，避免误杀。

    已知边界（W05/M04，详见 compatibility-matrix.md §5）：
    - 容器重建导致 hostname 改变时，原 Run 不会被新容器启动恢复收敛，
      历史未登记 owner 依赖用户 force_cancel；新实例由存活租约收敛。
    - PID 重用会把已死进程误判为存活，推迟收敛；uuid 段当前不参与存活判定。
    - 同名主机、不同 PID namespace 可能误判；多副本应保证 hostname 唯一。
    """

    parsed = parse_process_owner(process_owner)
    if parsed is None:
        return include_unowned
    owner_host, owner_pid = parsed
    if owner_host.casefold() != local_hostname.casefold():
        return False
    if owner_pid == current_pid:
        return False
    return not process_is_alive(owner_pid)


async def recover_interrupted_agent_runs_on_startup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    include_unowned: bool | None = None,
    local_hostname: str | None = None,
) -> int:
    """终态化本进程/本机遗留的普通Run；不碰其它副本活跃Run。

    - `include_unowned` 缺省时按部署画像：单进程部署收敛无主遗留，多副本部署跳过。
    - 暂停确认和持久化外部任务不属于本函数。
    """

    recovered = 0
    if include_unowned is None:
        include_unowned = not resolve_deployment_profile().multi_process_requested
    host = local_hostname if local_hostname is not None else socket.gethostname()
    current_pid = os.getpid()
    async with session_factory() as session:
        runs = list(
            (
                await session.scalars(
                    select(AiAgentRun).where(
                        AiAgentRun.status.in_(("pending", "running", "cancelling")),
                        # 已登记实例只由存活租约收敛，禁止用 PID namespace 探测覆盖它。
                        ~exists(select(AiAgentProcessOwner.owner_id).where(
                            AiAgentProcessOwner.owner_id == AiAgentRun.process_owner,
                        )),
                    )
                )
            ).all()
        )
        for run in runs:
            if not should_recover_run(
                process_owner=run.process_owner,
                local_hostname=host,
                current_pid=current_pid,
                include_unowned=include_unowned,
            ):
                continue
            store = PlatformAgentRuntimeStore(session, user_id=run.user_id)
            if run.status == "cancelling" or run.cancel_requested_at is not None:
                await store.mark_terminal(run, status="cancelled", content="Backend重启后已完成取消。")
            else:
                await store.mark_terminal(
                    run,
                    status="failed",
                    error_code="AI_RUN_PROCESS_STOPPED",
                    error_message="Backend进程已停止，当前智能体运行无法继续执行。",
                )
            recovered += 1
    return recovered
