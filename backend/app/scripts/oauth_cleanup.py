"""文件功能：提供 OAuth 过期记录有界清理 CLI，默认只读预检，执行须明确 --apply。"""

import argparse
import asyncio
import json
import sys

from app.db.session import get_session_factory, reset_database_state
from app.services.oauth.cleanup_service import OAuthCleanupService


async def run_command(args: argparse.Namespace) -> dict[str, object]:
    """关闭 OAuth 后仍可清理遗留数据；只输出各类数量，不列出用户或凭证内容。"""
    try:
        service = OAuthCleanupService(get_session_factory(), batch_size=args.batch_size)
        counts = await service.sweep(dry_run=not args.apply)
        return {
            "dry_run": not args.apply,
            "batch_size": args.batch_size,
            "counts": counts,
        }
    finally:
        await reset_database_state()


def main(argv: list[str] | None = None) -> int:
    """默认返回当前可回收批次预检；执行错误不输出 SQL 参数或数据库连接串。"""
    parser = argparse.ArgumentParser(
        description="预检或执行一个 OAuth 过期记录清理批次。"
    )
    parser.add_argument("--apply", action="store_true", help="实际提交本轮删除")
    parser.add_argument(
        "--batch-size", type=int, default=200, help="每类记录上限，1～1000"
    )
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run_command(args))
    except Exception as error:  # noqa: BLE001 - 运维错误不能携带凭证参数
        print(
            f"OAuth 清理失败（{type(error).__name__}），请核对配置和数据库迁移。",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
