"""文件功能：提供平台 smoke 测试数据注入 CLI。"""

from __future__ import annotations

import argparse
import asyncio

from app.scripts.test_data import ensure_smoke_data


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""

    parser = argparse.ArgumentParser(description="注入平台测试数据。")
    parser.add_argument("--scenario", default="smoke", choices=["smoke"], help="测试场景名称。")
    return parser


async def async_main() -> None:
    """按指定场景执行数据注入。"""

    parser = build_parser()
    args = parser.parse_args()
    if args.scenario == "smoke":
        await ensure_smoke_data()


def main() -> None:
    """CLI 入口。"""

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
