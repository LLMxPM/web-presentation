"""文件功能：提供 Renderer Worker 摘除前只读核对 CLI，强制执行未释放 attempt 门禁。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.db.session import get_session_factory
from app.services.rendering.repository import RenderRepository


def load_backend_env_for_cli(env_path: Path | None = None) -> Path | None:
    """从 backend/.env 补充当前进程缺失的环境变量，支持从根仓运行 CLI。"""

    path = env_path or _default_backend_env_path()
    if not path.is_file():
        return None

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in os.environ:
            os.environ[key] = value
            loaded = True
    if loaded:
        from app.core.config import get_settings

        get_settings.cache_clear()
    return path


def _default_backend_env_path() -> Path:
    """定位 backend/.env 的默认路径。"""

    return Path(__file__).resolve().parents[2] / ".env"


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    """解析一行 env 文本，忽略注释与空行。"""

    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def _attempt_payload(attempt: Any) -> dict[str, Any]:
    """把未释放 attempt 压缩为可读摘要。"""

    return {
        "id": getattr(attempt, "id", None),
        "attempt_uid": getattr(attempt, "attempt_uid", None),
        "request_id": getattr(attempt, "request_id", None),
        "worker_id": getattr(attempt, "worker_id", None),
        "worker_epoch": getattr(attempt, "worker_epoch", None),
        "status": getattr(attempt, "status", None),
        "lease_expires_at": getattr(attempt, "lease_expires_at", None),
    }


async def check_worker_removal(worker_id: str) -> dict[str, Any]:
    """核对指定 Worker 是否可安全摘除；只读查询。"""

    normalized = str(worker_id or "").strip()
    if not normalized:
        raise ValueError("worker_id 不能为空")
    async with get_session_factory()() as session:
        repository = RenderRepository(session)
        safe, pending = await repository.can_safely_remove_worker(worker_id=normalized)
        return {
            "worker_id": normalized,
            "safe_to_remove": bool(safe),
            "unreleased_attempt_count": len(pending),
            "unreleased_attempts": [_attempt_payload(item) for item in pending],
        }


def _print_summary(payload: dict[str, Any]) -> None:
    """输出人类可读摘要。"""

    if payload["safe_to_remove"]:
        print(f"worker {payload['worker_id']} 可安全摘除：无未释放 attempt。")
        return
    print(
        f"worker {payload['worker_id']} 不可摘除："
        f"仍有 {payload['unreleased_attempt_count']} 个未释放 attempt。"
    )
    for item in payload["unreleased_attempts"]:
        print(
            f"  - attempt#{item['id']} uid={item['attempt_uid']} "
            f"request={item['request_id']} epoch={item['worker_epoch']} status={item['status']}"
        )
    print("请等待租约收敛、取消在途 attempt，或接受超时后由协调器重试到其它 Worker。")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：0=可摘除，2=不可摘除，1=参数/运行错误。"""

    parser = argparse.ArgumentParser(
        description="摘除 Renderer Worker 前核对未释放 attempt（只读门禁）。",
    )
    parser.add_argument("--worker-id", required=True, help="目标 Renderer Worker ID")
    parser.add_argument(
        "--format",
        choices=("summary", "json"),
        default="summary",
        help="输出格式",
    )
    args = parser.parse_args(argv)
    load_backend_env_for_cli()
    try:
        payload = asyncio.run(check_worker_removal(args.worker_id))
    except Exception as exc:  # noqa: BLE001 - CLI 边界统一报错
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_summary(payload)
    return 0 if payload["safe_to_remove"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
