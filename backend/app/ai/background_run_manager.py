"""文件功能：管理与 SSE 请求生命周期解耦的进程内智能体运行任务。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress


logger = logging.getLogger(__name__)

RunWorkerFactory = Callable[[], Awaitable[None]]
SessionRunKey = tuple[str, str]


class AgentBackgroundRunManager:
    """按 run 和会话登记后台任务，并提供取消与应用关闭收敛能力。"""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._session_runs: dict[SessionRunKey, str] = {}
        self._guard = asyncio.Lock()
        self._closing = False

    async def start(
        self,
        *,
        run_id: str,
        session_id: str,
        agent_id: str,
        worker_factory: RunWorkerFactory,
    ) -> None:
        """原子登记并启动后台任务；同一会话同一时间只允许一个执行器。"""

        key = (session_id, agent_id)
        async with self._guard:
            if self._closing:
                raise RuntimeError("AI_BACKGROUND_RUN_MANAGER_STOPPING")
            existing_task = self._tasks.get(run_id)
            if existing_task is not None and not existing_task.done():
                return
            existing_run_id = self._session_runs.get(key)
            if existing_run_id is not None and existing_run_id != run_id:
                raise ValueError("AI_SESSION_RUN_ACTIVE")
            task = asyncio.create_task(
                self._run_worker(run_id=run_id, key=key, worker_factory=worker_factory),
                name=f"ai-agent-run-{run_id}",
            )
            self._tasks[run_id] = task
            self._session_runs[key] = run_id

    async def cancel(self, run_id: str) -> bool:
        """取消当前进程持有的目标任务；终态由任务自身的取消处理写入。"""

        async with self._guard:
            task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        return True

    async def wait(self, run_id: str) -> None:
        """等待目标 Run 当前执行阶段退出，供 paused Run 安全提交下一阶段。"""

        async with self._guard:
            task = self._tasks.get(run_id)
        if task is not None and task is not asyncio.current_task():
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        """停止接受新任务，并等待所有后台任务完成取消收敛。"""

        async with self._guard:
            self._closing = True
            tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_worker(
        self,
        *,
        run_id: str,
        key: SessionRunKey,
        worker_factory: RunWorkerFactory,
    ) -> None:
        """执行单个后台任务，并在任何退出路径清理进程内登记。"""

        try:
            await worker_factory()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception(
                "Unhandled agent background run error",
                extra={"event": "ai.agent_run.background_unhandled", "run_id": run_id},
            )
        finally:
            async with self._guard:
                current_task = asyncio.current_task()
                if self._tasks.get(run_id) is current_task:
                    self._tasks.pop(run_id, None)
                if self._session_runs.get(key) == run_id:
                    self._session_runs.pop(key, None)
