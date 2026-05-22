"""文件功能：提供平台测试数据重置 CLI。"""

from __future__ import annotations

import asyncio

from app.scripts.test_data import reset_all_test_data


async def async_main() -> None:
    """执行测试数据重置。"""

    await reset_all_test_data()


def main() -> None:
    """CLI 入口。"""

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
